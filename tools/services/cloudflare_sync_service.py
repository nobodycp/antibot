"""
Push antibot WAF custom rules to Cloudflare zones (http_request_firewall_custom).

Fetches current antibot rules and IP list items first, compares with DB state,
and only writes to Cloudflare when something differs.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import requests
from django.utils import timezone

from dashboard.cloudflare_token_crypto import decrypt_cloudflare_token
from dashboard.helpers.cloudflare_zone import map_cf_api_error
from dashboard.models import UserCloudflareDomain
from tools.services.cloudflare_zone_settings import (
    ZoneSettingsSyncResult,
    sync_zone_settings,
)
from tracker.helpers.ownership import allowed_countries_queryset
from tracker.models import BlockedSubnet

logger = logging.getLogger(__name__)

CF_API_BASE = "https://api.cloudflare.com/client/v4"
ANTIBOT_DESC_PREFIX = "antibot:"
SUBNET_RULE_DESC = "antibot:subnet-block"
INLINE_SUBNET_LIMIT = 25
IP_LIST_NAME = "antibot_subnet_block"
IP_LIST_ITEMS_PER_PAGE = 100
IP_LIST_POST_BATCH_SIZE = 500
IP_LIST_DELETE_BATCH_SIZE = 500
CF_DEFAULT_REQUEST_TIMEOUT = 30
CF_BATCH_REQUEST_TIMEOUT = 60
CF_LARGE_REQUEST_TIMEOUT = 120
CF_BULK_POLL_INTERVAL = 1.0
CF_BULK_POLL_MAX_WAIT = 180

_account_id_cache: dict[tuple[str, str], str] = {}

# Inline IP lists: space-separated CIDRs without quotes (see CF rules language "Values").
_INLINE_SUBNET_RE = re.compile(r"^ip\.src in \{((?:\S+\s*)+)\}$")
# Legacy antibot expressions used quoted CIDRs inside braces (invalid on Cloudflare).
_LEGACY_QUOTED_SUBNET_RE = re.compile(r'^ip\.src in \{((?:"[^"]+"\s*)+)\}$')
_COUNTRY_EXPR_RE = re.compile(r'^not ip\.geoip\.country in \{((?:"[^"]+"\s*)+)\}$')


@dataclass
class DomainSyncResult:
    domain_id: int
    domain_name: str
    ok: bool
    status: str
    message: str
    warnings: list[str] = field(default_factory=list)
    skipped: bool = False


def country_rule_description(user_id: int) -> str:
    return f"antibot:country-allow-{user_id}"


def _cf_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token.strip()}",
        "Content-Type": "application/json",
    }


def _ip_list_max_items() -> Optional[int]:
    raw = os.environ.get("CF_IP_LIST_MAX_ITEMS", "").strip()
    if not raw:
        return None
    try:
        return max(1, int(raw))
    except ValueError:
        logger.warning("Invalid CF_IP_LIST_MAX_ITEMS=%r; ignoring cap", raw)
        return None


def _format_ip_list_sync_error(err: str, *, total_count: int, batch_size: int) -> str:
    lowered = (err or "").lower()
    if any(
        marker in lowered
        for marker in (
            "payload",
            "too large",
            "request body",
            "entity too large",
            "413",
            "exceeds",
            "maximum",
        )
    ):
        return (
            f"Too many subnets ({total_count}); Cloudflare list sync supports "
            f"batches up to {batch_size}"
        )
    return err


def _cf_request(
    method: str,
    path: str,
    token: str,
    *,
    json_body: Any = None,
    query_params: Optional[dict[str, Any]] = None,
    timeout: int = CF_DEFAULT_REQUEST_TIMEOUT,
) -> tuple[bool, Any, str]:
    url = f"{CF_API_BASE}{path}"
    try:
        resp = requests.request(
            method,
            url,
            headers=_cf_headers(token),
            json=json_body,
            params=query_params,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        return False, None, str(exc)

    try:
        payload = resp.json()
    except ValueError:
        return False, None, f"Invalid JSON (HTTP {resp.status_code})"

    if not payload.get("success"):
        errors = payload.get("errors") or []
        code: Optional[int] = None
        msg = f"HTTP {resp.status_code}"
        if errors:
            err = errors[0]
            raw_code = err.get("code")
            try:
                code = int(raw_code) if raw_code is not None else None
            except (TypeError, ValueError):
                code = None
            msg = (err.get("message") or str(err)).strip()
        return False, payload, map_cf_api_error(
            code=code,
            message=msg,
            http_status=resp.status_code,
        )

    return True, payload, ""


def _normalize_cidrs(cidrs: list[str]) -> list[str]:
    return sorted({c.strip() for c in cidrs if c and c.strip()})


def _normalize_country_codes(codes: list[str]) -> list[str]:
    return sorted({c.strip().upper() for c in codes if c and c.strip()})


def _get_blocked_cidrs() -> list[str]:
    return _normalize_cidrs(
        list(BlockedSubnet.objects.order_by("cidr").values_list("cidr", flat=True))
    )


def _get_allowed_country_codes(user) -> list[str]:
    return _normalize_country_codes(
        list(
            allowed_countries_queryset(user)
            .order_by("code")
            .values_list("code", flat=True)
        )
    )


def build_inline_subnet_expression(cidrs: list[str]) -> str:
    """Build WAF expression for <= INLINE_SUBNET_LIMIT CIDRs (unquoted inline list)."""
    normalized = _normalize_cidrs(cidrs)
    if not normalized:
        return ""
    parts = " ".join(normalized)
    return f"ip.src in {{{parts}}}"


def build_list_subnet_expression() -> str:
    return f"ip.src in ${IP_LIST_NAME}"


def build_subnet_expression(
    cidrs: list[str], token: str, zone_id: str
) -> Optional[str]:
    """
    Return the WAF expression for global subnet block (no Cloudflare writes).

  For large lists the expression references the IP list; list items must be
    synced separately via ``_sync_ip_list_items``.
    """
    normalized = _normalize_cidrs(cidrs)
    if not normalized:
        return None
    if len(normalized) <= INLINE_SUBNET_LIMIT:
        return build_inline_subnet_expression(normalized)
    return build_list_subnet_expression()


def build_country_expression(codes: list[str]) -> Optional[str]:
    """Block traffic from countries NOT in the user's allowlist."""
    normalized = _normalize_country_codes(codes)
    if not normalized:
        return None
    parts = " ".join(f'"{c}"' for c in normalized)
    return f"not ip.geoip.country in {{{parts}}}"


def _quoted_tokens_from_brace_group(group: str) -> set[str]:
    return {m.group(1) for m in re.finditer(r'"([^"]+)"', group)}


def _parse_inline_subnet_cidrs(expression: str) -> Optional[set[str]]:
    expr = (expression or "").strip()
    match = _INLINE_SUBNET_RE.match(expr)
    if match:
        return set(match.group(1).split())
    legacy = _LEGACY_QUOTED_SUBNET_RE.match(expr)
    if legacy:
        return _quoted_tokens_from_brace_group(legacy.group(1))
    return None


def _parse_country_codes(expression: str) -> Optional[set[str]]:
    match = _COUNTRY_EXPR_RE.match((expression or "").strip())
    if not match:
        return None
    return _quoted_tokens_from_brace_group(match.group(1))


def _is_antibot_rule(rule: dict) -> bool:
    desc = (rule.get("description") or "").strip()
    return desc.startswith(ANTIBOT_DESC_PREFIX)


def _find_rule_by_description(rules: list[dict], description: str) -> Optional[dict]:
    for rule in rules:
        if (rule.get("description") or "").strip() == description:
            return rule
    return None


def _rule_payload_matches(existing: dict, desired: dict) -> bool:
    return (
        (existing.get("action") or "").strip() == (desired.get("action") or "").strip()
        and (existing.get("expression") or "").strip()
        == (desired.get("expression") or "").strip()
        and bool(existing.get("enabled", True)) == bool(desired.get("enabled", True))
    )


def _account_lists_base(token: str, zone_id: str) -> tuple[bool, str, str, str]:
    """
    Cloudflare Rules Lists are account-scoped (not /zones/{id}/rules/lists).

    Returns (ok, account_id, lists_base_path, error_message).
    """
    ok, account_id, err = _account_id_for_zone(token, zone_id)
    if not ok:
        return False, "", "", err
    return True, account_id, f"/accounts/{account_id}/rules/lists", ""


def _find_ip_list_id(token: str, zone_id: str) -> Optional[str]:
    ok, _account_id, lists_base, err = _account_lists_base(token, zone_id)
    if not ok:
        raise RuntimeError(f"Could not list IP lists: {err}")
    ok, payload, err = _cf_request(
        "GET",
        lists_base,
        token,
    )
    if not ok:
        raise RuntimeError(f"Could not list IP lists: {err}")

    for item in (payload or {}).get("result") or []:
        if item.get("name") == IP_LIST_NAME:
            return item.get("id")
    return None


def _fetch_ip_list_items_by_ip(
    token: str, zone_id: str, list_id: str
) -> dict[str, str]:
    """Return mapping of CIDR/IP string -> Cloudflare item id (paginated GET)."""
    ok, _account_id, lists_base, err = _account_lists_base(token, zone_id)
    if not ok:
        raise RuntimeError(f"Could not fetch IP list items: {err}")
    path = f"{lists_base}/{list_id}/items"
    items_by_ip: dict[str, str] = {}
    cursor: Optional[str] = None

    while True:
        params: dict[str, Any] = {"per_page": IP_LIST_ITEMS_PER_PAGE}
        if cursor:
            params["cursor"] = cursor
        ok, payload, err = _cf_request(
            "GET",
            path,
            token,
            query_params=params,
            timeout=CF_LARGE_REQUEST_TIMEOUT,
        )
        if not ok:
            raise RuntimeError(f"Could not fetch IP list items: {err}")

        for item in (payload or {}).get("result") or []:
            ip_val = (item.get("ip") or item.get("value") or "").strip()
            item_id = (item.get("id") or "").strip()
            if ip_val and item_id:
                items_by_ip[ip_val] = item_id

        result_info = (payload or {}).get("result_info") or {}
        cursors = result_info.get("cursors") or {}
        cursor = (cursors.get("after") or "").strip() or None
        if not cursor:
            break

    return items_by_ip


def _get_ip_list_cidrs(token: str, zone_id: str, list_id: str) -> set[str]:
    return set(_fetch_ip_list_items_by_ip(token, zone_id, list_id).keys())


def _account_id_for_zone(token: str, zone_id: str) -> tuple[bool, str, str]:
    """Resolve account id for zone-scoped list bulk-operation status polling."""
    cache_key = (token, zone_id)
    cached = _account_id_cache.get(cache_key)
    if cached:
        return True, cached, ""

    ok, payload, err = _cf_request("GET", f"/zones/{zone_id}", token)
    if not ok:
        return False, "", err

    account = (payload.get("result") or {}).get("account") or {}
    account_id = (account.get("id") or "").strip()
    if not account_id:
        return False, "", "Could not resolve Cloudflare account id for zone"

    _account_id_cache[cache_key] = account_id
    return True, account_id, ""


def _wait_list_bulk_operation(
    token: str,
    account_id: str,
    operation_id: str,
) -> tuple[bool, str]:
    """Poll until an async list POST/DELETE batch finishes (1 pending op per account)."""
    path = f"/accounts/{account_id}/rules/lists/bulk_operations/{operation_id}"
    deadline = time.monotonic() + CF_BULK_POLL_MAX_WAIT

    while time.monotonic() < deadline:
        ok, payload, err = _cf_request("GET", path, token)
        if not ok:
            return False, err

        result = (payload or {}).get("result") or {}
        status = (result.get("status") or "").strip().lower()
        if status == "completed":
            return True, ""
        if status == "failed":
            error = (
                result.get("error") or "Cloudflare list bulk operation failed"
            ).strip()
            return False, error
        if status in ("pending", "running"):
            time.sleep(CF_BULK_POLL_INTERVAL)
            continue
        if not status:
            time.sleep(CF_BULK_POLL_INTERVAL)
            continue
        return False, f"Unknown Cloudflare list bulk operation status: {status}"

    return False, "Timed out waiting for Cloudflare list bulk operation"


def _cf_list_batch_and_wait(
    token: str,
    zone_id: str,
    account_id: str,
    method: str,
    path: str,
    json_body: Any,
) -> tuple[bool, str]:
    ok, payload, err = _cf_request(
        method,
        path,
        token,
        json_body=json_body,
        timeout=CF_BATCH_REQUEST_TIMEOUT,
    )
    if not ok:
        return False, err

    operation_id = ((payload or {}).get("result") or {}).get("operation_id") or ""
    operation_id = operation_id.strip()
    if operation_id:
        return _wait_list_bulk_operation(token, account_id, operation_id)
    return True, ""


def _apply_ip_list_cap(desired_cidrs: list[str]) -> tuple[list[str], Optional[str]]:
    max_items = _ip_list_max_items()
    normalized = _normalize_cidrs(desired_cidrs)
    if max_items is None or len(normalized) <= max_items:
        return normalized, None
    warning = (
        f"Blocked subnets capped at {max_items} for Cloudflare sync "
        f"(CF_IP_LIST_MAX_ITEMS); database has {len(normalized)}."
    )
    logger.warning("%s", warning)
    return normalized[:max_items], warning


def _post_ip_list_items_batches(
    token: str,
    zone_id: str,
    list_id: str,
    cidrs: list[str],
) -> tuple[bool, str]:
    ok, account_id, lists_base, err = _account_lists_base(token, zone_id)
    if not ok:
        return False, err

    path = f"{lists_base}/{list_id}/items"
    items = [{"ip": c} for c in sorted(cidrs)]
    total = len(items)

    for offset in range(0, total, IP_LIST_POST_BATCH_SIZE):
        batch = items[offset : offset + IP_LIST_POST_BATCH_SIZE]
        ok, err = _cf_list_batch_and_wait(
            token, zone_id, account_id, "POST", path, batch
        )
        if not ok:
            return False, _format_ip_list_sync_error(
                err, total_count=total, batch_size=IP_LIST_POST_BATCH_SIZE
            )
    return True, ""


def _delete_ip_list_items_batches(
    token: str,
    zone_id: str,
    list_id: str,
    item_ids: list[str],
) -> tuple[bool, str]:
    if not item_ids:
        return True, ""
    ok, account_id, lists_base, err = _account_lists_base(token, zone_id)
    if not ok:
        return False, err

    path = f"{lists_base}/{list_id}/items"
    total = len(item_ids)

    for offset in range(0, total, IP_LIST_DELETE_BATCH_SIZE):
        batch_ids = item_ids[offset : offset + IP_LIST_DELETE_BATCH_SIZE]
        ok, err = _cf_list_batch_and_wait(
            token,
            zone_id,
            account_id,
            "DELETE",
            path,
            {"items": [{"id": item_id} for item_id in batch_ids]},
        )
        if not ok:
            return False, _format_ip_list_sync_error(
                err, total_count=total, batch_size=IP_LIST_DELETE_BATCH_SIZE
            )
    return True, ""


def _ensure_ip_list_id(token: str, zone_id: str) -> str:
    list_id = _find_ip_list_id(token, zone_id)
    if list_id:
        return list_id

    ok, _account_id, lists_base, err = _account_lists_base(token, zone_id)
    if not ok:
        raise RuntimeError(f"Could not create IP list: {err}")
    ok, payload, err = _cf_request(
        "POST",
        lists_base,
        token,
        json_body={
            "name": IP_LIST_NAME,
            "kind": "ip",
            "description": "Antibot global blocked subnets",
        },
    )
    if not ok:
        raise RuntimeError(f"Could not create IP list: {err}")
    list_id = (payload.get("result") or {}).get("id")
    if not list_id:
        raise RuntimeError("Cloudflare did not return IP list id")
    return list_id


def _sync_ip_list_items(
    token: str,
    zone_id: str,
    desired_cidrs: list[str],
) -> tuple[bool, bool, str, Optional[str]]:
    """
    Ensure the antibot IP list matches ``desired_cidrs``.

    Uses paginated GET and batched POST/DELETE (not one giant PUT).

    Returns (success, changed, error_message, cap_warning).
    """
    capped, cap_warning = _apply_ip_list_cap(desired_cidrs)
    desired_set = set(capped)
    list_id = _find_ip_list_id(token, zone_id)

    if not desired_set:
        if not list_id:
            return True, False, "", cap_warning
        try:
            current_items = _fetch_ip_list_items_by_ip(token, zone_id, list_id)
        except RuntimeError as exc:
            return False, False, str(exc), cap_warning
        if not current_items:
            return True, False, "", cap_warning
        ok, err = _delete_ip_list_items_batches(
            token, zone_id, list_id, list(current_items.values())
        )
        return ok, ok, err, cap_warning

    if not list_id:
        list_id = _ensure_ip_list_id(token, zone_id)
        current_items: dict[str, str] = {}
    else:
        try:
            current_items = _fetch_ip_list_items_by_ip(token, zone_id, list_id)
        except RuntimeError as exc:
            return False, False, str(exc), cap_warning

    current_set = set(current_items.keys())
    if current_set == desired_set:
        logger.debug(
            "IP list %s already matches DB (%d items)", IP_LIST_NAME, len(desired_set)
        )
        return True, False, "", cap_warning

    to_remove = current_set - desired_set
    to_add = sorted(desired_set - current_set)

    if to_remove:
        remove_ids = [current_items[cidr] for cidr in sorted(to_remove)]
        ok, err = _delete_ip_list_items_batches(
            token, zone_id, list_id, remove_ids
        )
        if not ok:
            return False, False, err, cap_warning

    if to_add:
        ok, err = _post_ip_list_items_batches(token, zone_id, list_id, to_add)
        if not ok:
            return False, False, err, cap_warning

    return True, True, "", cap_warning


def _subnet_state_matches(
    desired_cidrs: list[str],
    existing_rule: Optional[dict],
    token: str,
    zone_id: str,
) -> bool:
    desired = _normalize_cidrs(desired_cidrs)
    if not desired:
        if existing_rule is not None:
            return False
        list_id = _find_ip_list_id(token, zone_id)
        if not list_id:
            return True
        try:
            return not _get_ip_list_cidrs(token, zone_id, list_id)
        except RuntimeError:
            return False

    use_list = len(desired) > INLINE_SUBNET_LIMIT
    if use_list:
        list_id = _find_ip_list_id(token, zone_id)
        if not list_id:
            return False
        try:
            if set(desired) != _get_ip_list_cidrs(token, zone_id, list_id):
                return False
        except RuntimeError:
            return False
        desired_expr = build_list_subnet_expression()
    else:
        desired_expr = build_inline_subnet_expression(desired)

    if existing_rule is None:
        return False

    existing_expr = (existing_rule.get("expression") or "").strip()
    if existing_expr == desired_expr:
        return True

    if not use_list:
        existing_cidrs = _parse_inline_subnet_cidrs(existing_expr)
        if existing_cidrs is not None and existing_cidrs == set(desired):
            return True

    return False


def _country_state_matches(
    desired_codes: list[str],
    existing_rule: Optional[dict],
) -> bool:
    desired = _normalize_country_codes(desired_codes)
    if not desired:
        return existing_rule is None

    if existing_rule is None:
        return False

    desired_expr = build_country_expression(desired)
    existing_expr = (existing_rule.get("expression") or "").strip()
    if existing_expr == desired_expr:
        return True

    existing_codes = _parse_country_codes(existing_expr)
    if existing_codes is not None and existing_codes == set(desired):
        return True

    return False


def _subnet_rule_payload(subnet_expr: str) -> dict:
    return {
        "action": "block",
        "expression": subnet_expr,
        "description": SUBNET_RULE_DESC,
        "enabled": True,
    }


def _country_rule_payload(domain: UserCloudflareDomain, country_expr: str) -> dict:
    return {
        "action": "block",
        "expression": country_expr,
        "description": country_rule_description(domain.user_id),
        "enabled": True,
    }


def _merge_waf_rules(
    existing_rules: list[dict],
    *,
    domain: UserCloudflareDomain,
    desired_subnet: Optional[dict],
    desired_country: Optional[dict],
    include_subnet: bool,
    include_country: bool,
) -> list[dict]:
    """Merge antibot WAF rules without dropping unrelated antibot rules on the zone."""
    kept = [r for r in existing_rules if not _is_antibot_rule(r)]
    preserved: list[dict] = []
    country_desc = country_rule_description(domain.user_id)

    for rule in existing_rules:
        if not _is_antibot_rule(rule):
            continue
        desc = (rule.get("description") or "").strip()
        if desc == SUBNET_RULE_DESC and not include_subnet:
            preserved.append(rule)
        elif desc.startswith("antibot:country-allow-") and (
            not include_country or desc != country_desc
        ):
            preserved.append(rule)

    desired: list[dict] = []
    if include_subnet and desired_subnet:
        desired.append(desired_subnet)
    if include_country and desired_country:
        desired.append(desired_country)

    return kept + preserved + desired


def _put_entrypoint_rules(
    zone_id: str,
    token: str,
    merged_rules: list[dict],
    ruleset_id: str,
) -> tuple[bool, str]:
    ok, _, err = _cf_request(
        "PUT",
        f"/zones/{zone_id}/rulesets/{ruleset_id}",
        token,
        json_body={"rules": merged_rules},
    )
    return ok, err


def _merged_rules_match_existing(
    existing_rules: list[dict],
    merged_rules: list[dict],
) -> bool:
    if len(existing_rules) != len(merged_rules):
        return False

    for existing, desired in zip(existing_rules, merged_rules):
        keys = ("description", "action", "expression", "enabled")
        for key in keys:
            if key == "enabled":
                if bool(existing.get(key, True)) != bool(desired.get(key, True)):
                    return False
            elif (existing.get(key) or "").strip() != (desired.get(key) or "").strip():
                return False
    return True


def _fetch_waf_entrypoint(
    domain: UserCloudflareDomain,
    token: str,
) -> tuple[bool, list[dict], str, str]:
    """Return (ok, existing_rules, ruleset_id, error_message)."""
    ok, payload, err = _cf_request(
        "GET",
        f"/zones/{domain.zone_id}/rulesets/phases/http_request_firewall_custom/entrypoint",
        token,
    )
    if not ok:
        return False, [], "", err

    result = payload.get("result") or {}
    ruleset_id = result.get("id") or ""
    existing_rules = list(result.get("rules") or [])
    if not ruleset_id:
        return False, existing_rules, "", "Missing ruleset id from Cloudflare"
    return True, existing_rules, ruleset_id, ""


def _sync_subnet_ip_lists(
    token: str,
    zone_id: str,
    cidrs: list[str],
) -> tuple[bool, bool, str, Optional[str]]:
    """Sync global subnet IP list items when needed. Returns (ok, changed, error, cap_warning)."""
    if len(cidrs) > INLINE_SUBNET_LIMIT:
        return _sync_ip_list_items(token, zone_id, cidrs)
    if not cidrs:
        return _sync_ip_list_items(token, zone_id, [])
    return True, False, "", None


def _waf_subnet_needs_update(
    cidrs: list[str],
    existing_subnet_rule: Optional[dict],
    desired_subnet: Optional[dict],
    token: str,
    zone_id: str,
) -> bool:
    if not _subnet_state_matches(cidrs, existing_subnet_rule, token, zone_id):
        return True
    if desired_subnet is None:
        return existing_subnet_rule is not None
    if existing_subnet_rule is None:
        return True
    return not _rule_payload_matches(existing_subnet_rule, desired_subnet)


def _waf_country_needs_update(
    codes: list[str],
    existing_country_rule: Optional[dict],
    desired_country: Optional[dict],
    country_desc: str,
    existing_rules: list[dict],
) -> bool:
    if not _country_state_matches(codes, existing_country_rule):
        return True
    if desired_country is None:
        return existing_country_rule is not None
    if existing_country_rule is None:
        return True
    if not _rule_payload_matches(existing_country_rule, desired_country):
        return True
    for rule in existing_rules:
        if not _is_antibot_rule(rule):
            continue
        desc = (rule.get("description") or "").strip()
        if desc == country_desc and desired_country is None:
            return True
    return False


def sync_subnet_for_domain(domain: UserCloudflareDomain) -> DomainSyncResult:
    """Sync global blocked subnets to one zone (WAF + IP list only). Does not update last_sync_*."""
    name = domain.domain_name

    if not domain.is_active:
        return DomainSyncResult(
            domain_id=domain.pk,
            domain_name=name,
            ok=True,
            status=UserCloudflareDomain.SYNC_OK,
            message="Skipped (inactive).",
            skipped=True,
        )

    try:
        token = decrypt_cloudflare_token(domain.user_id, domain.api_token_ciphertext)
    except ValueError as exc:
        return DomainSyncResult(
            domain_id=domain.pk,
            domain_name=name,
            ok=False,
            status=UserCloudflareDomain.SYNC_ERROR,
            message=str(exc),
        )

    ok, existing_rules, ruleset_id, err = _fetch_waf_entrypoint(domain, token)
    if not ok:
        return DomainSyncResult(
            domain_id=domain.pk,
            domain_name=name,
            ok=False,
            status=UserCloudflareDomain.SYNC_ERROR,
            message=err,
        )

    cidrs = _get_blocked_cidrs()
    existing_subnet_rule = _find_rule_by_description(existing_rules, SUBNET_RULE_DESC)

    ip_warnings: list[str] = []
    try:
        ok, ip_list_changed, err, cap_warning = _sync_subnet_ip_lists(
            token, domain.zone_id, cidrs
        )
        if cap_warning:
            ip_warnings.append(cap_warning)
        if not ok:
            raise RuntimeError(f"Subnet IP list: {err}")
    except RuntimeError as exc:
        return DomainSyncResult(
            domain_id=domain.pk,
            domain_name=name,
            ok=False,
            status=UserCloudflareDomain.SYNC_ERROR,
            message=str(exc),
            warnings=ip_warnings,
        )

    subnet_expr = build_subnet_expression(cidrs, token, domain.zone_id)
    desired_subnet = (
        _subnet_rule_payload(subnet_expr) if subnet_expr else None
    )
    rules_need_update = _waf_subnet_needs_update(
        cidrs, existing_subnet_rule, desired_subnet, token, domain.zone_id
    )

    if not rules_need_update and not ip_list_changed:
        return DomainSyncResult(
            domain_id=domain.pk,
            domain_name=name,
            ok=True,
            status=UserCloudflareDomain.SYNC_OK,
            message="Already synced (no subnet changes).",
            skipped=True,
            warnings=ip_warnings,
        )

    merged = _merge_waf_rules(
        existing_rules,
        domain=domain,
        desired_subnet=desired_subnet,
        desired_country=None,
        include_subnet=True,
        include_country=False,
    )

    if _merged_rules_match_existing(existing_rules, merged):
        parts = ["IP list updated"] if ip_list_changed else []
        msg = (
            "Subnet synced. (" + ", ".join(parts) + ")"
            if parts
            else "Already synced (no WAF rule changes)."
        )
        status = (
            UserCloudflareDomain.SYNC_WARNING
            if ip_warnings
            else UserCloudflareDomain.SYNC_OK
        )
        return DomainSyncResult(
            domain_id=domain.pk,
            domain_name=name,
            ok=True,
            status=status,
            message=msg,
            warnings=ip_warnings,
            skipped=not ip_list_changed,
        )

    ok, err = _put_entrypoint_rules(domain.zone_id, token, merged, ruleset_id)
    if not ok:
        return DomainSyncResult(
            domain_id=domain.pk,
            domain_name=name,
            ok=False,
            status=UserCloudflareDomain.SYNC_ERROR,
            message=err,
            warnings=ip_warnings,
        )

    parts = []
    if ip_list_changed:
        parts.append("IP list updated")
    if rules_need_update:
        parts.append("subnet WAF rule updated")
    msg = "Subnet synced." + (" (" + ", ".join(parts) + ")" if parts else "")
    status = (
        UserCloudflareDomain.SYNC_WARNING
        if ip_warnings
        else UserCloudflareDomain.SYNC_OK
    )
    return DomainSyncResult(
        domain_id=domain.pk,
        domain_name=name,
        ok=True,
        status=status,
        message=msg,
        warnings=ip_warnings,
    )


def sync_domain(
    domain: UserCloudflareDomain,
    *,
    include_subnet: bool = False,
) -> DomainSyncResult:
    """
    Sync one active domain. Updates last_sync_* on the model row.

    Default (user sync): allowed countries + zone settings + rate limit only.
    include_subnet=True: also push global BlockedSubnet WAF/IP list (admin use).
    """
    name = domain.domain_name
    warnings: list[str] = []

    if not domain.is_active:
        return DomainSyncResult(
            domain_id=domain.pk,
            domain_name=name,
            ok=True,
            status=UserCloudflareDomain.SYNC_OK,
            message="Skipped (inactive).",
            skipped=True,
        )

    try:
        token = decrypt_cloudflare_token(domain.user_id, domain.api_token_ciphertext)
    except ValueError as exc:
        _update_domain_sync(domain, UserCloudflareDomain.SYNC_ERROR, str(exc))
        return DomainSyncResult(
            domain_id=domain.pk,
            domain_name=name,
            ok=False,
            status=UserCloudflareDomain.SYNC_ERROR,
            message=str(exc),
        )

    ok, existing_rules, ruleset_id, err = _fetch_waf_entrypoint(domain, token)
    if not ok:
        _update_domain_sync(domain, UserCloudflareDomain.SYNC_ERROR, err)
        return DomainSyncResult(
            domain_id=domain.pk,
            domain_name=name,
            ok=False,
            status=UserCloudflareDomain.SYNC_ERROR,
            message=err,
        )

    codes = _get_allowed_country_codes(domain.user)
    country_desc = country_rule_description(domain.user_id)
    existing_subnet_rule = _find_rule_by_description(existing_rules, SUBNET_RULE_DESC)
    existing_country_rule = _find_rule_by_description(existing_rules, country_desc)

    if not codes:
        warnings.append(
            f"No allowed countries for user {domain.user.username}; "
            "country allow rule removed (all countries allowed at edge)."
        )

    ip_list_changed = False
    cidrs: list[str] = []
    try:
        if include_subnet:
            cidrs = _get_blocked_cidrs()
            ok, ip_list_changed, err, cap_warning = _sync_subnet_ip_lists(
                token, domain.zone_id, cidrs
            )
            if cap_warning:
                warnings.append(cap_warning)
            if not ok:
                raise RuntimeError(f"Subnet IP list: {err}")
    except RuntimeError as exc:
        _update_domain_sync(domain, UserCloudflareDomain.SYNC_ERROR, str(exc))
        return DomainSyncResult(
            domain_id=domain.pk,
            domain_name=name,
            ok=False,
            status=UserCloudflareDomain.SYNC_ERROR,
            message=str(exc),
            warnings=warnings,
        )

    subnet_expr = (
        build_subnet_expression(cidrs, token, domain.zone_id) if include_subnet else None
    )
    country_expr = build_country_expression(codes)
    desired_subnet = (
        _subnet_rule_payload(subnet_expr) if subnet_expr else None
    )
    desired_country = (
        _country_rule_payload(domain, country_expr) if country_expr else None
    )

    subnet_matches = True
    if include_subnet:
        subnet_matches = _subnet_state_matches(
            cidrs, existing_subnet_rule, token, domain.zone_id
        )
    country_matches = _country_state_matches(codes, existing_country_rule)

    rules_need_update = not country_matches
    if include_subnet:
        rules_need_update = rules_need_update or not subnet_matches

    if not rules_need_update:
        if include_subnet and desired_subnet:
            existing = _find_rule_by_description(existing_rules, SUBNET_RULE_DESC)
            if existing is None or not _rule_payload_matches(existing, desired_subnet):
                rules_need_update = True
        if desired_country:
            existing = _find_rule_by_description(existing_rules, country_desc)
            if existing is None or not _rule_payload_matches(existing, desired_country):
                rules_need_update = True
        elif existing_country_rule is not None:
            rules_need_update = True
        if include_subnet and desired_subnet is None and existing_subnet_rule is not None:
            rules_need_update = True

    if not rules_need_update and not ip_list_changed:
        msg = "Already synced (no changes)."
        logger.info("%s: %s", name, msg)
        return _merge_zone_settings_result(
            domain,
            token,
            waf_message=msg,
            waf_skipped=True,
            waf_warnings=warnings,
        )

    merged = _merge_waf_rules(
        existing_rules,
        domain=domain,
        desired_subnet=desired_subnet,
        desired_country=desired_country,
        include_subnet=include_subnet,
        include_country=True,
    )

    if _merged_rules_match_existing(existing_rules, merged):
        parts = []
        if ip_list_changed:
            parts.append("IP list updated")
        msg = (
            "Synced successfully. (" + ", ".join(parts) + ")"
            if parts
            else "Already synced (no WAF rule changes)."
        )
        logger.info("%s: %s", name, msg)
        return _merge_zone_settings_result(
            domain,
            token,
            waf_message=msg,
            waf_skipped=not ip_list_changed,
            waf_warnings=warnings,
        )

    ok, err = _put_entrypoint_rules(domain.zone_id, token, merged, ruleset_id)
    if not ok:
        _update_domain_sync(domain, UserCloudflareDomain.SYNC_ERROR, err)
        return DomainSyncResult(
            domain_id=domain.pk,
            domain_name=name,
            ok=False,
            status=UserCloudflareDomain.SYNC_ERROR,
            message=err,
            warnings=warnings,
        )

    parts = []
    if ip_list_changed:
        parts.append("IP list updated")
    if rules_need_update:
        parts.append("WAF rules updated")
    msg = "Synced successfully." + (" (" + ", ".join(parts) + ")" if parts else "")

    return _merge_zone_settings_result(
        domain,
        token,
        waf_message=msg,
        waf_skipped=False,
        waf_warnings=warnings,
    )


def _merge_zone_settings_result(
    domain: UserCloudflareDomain,
    token: str,
    *,
    waf_message: str,
    waf_skipped: bool,
    waf_warnings: list[str],
    waf_ok: bool = True,
) -> DomainSyncResult:
    """Run zone settings sync and merge with WAF outcome."""
    name = domain.domain_name
    warnings = list(waf_warnings)

    if not waf_ok:
        return DomainSyncResult(
            domain_id=domain.pk,
            domain_name=name,
            ok=False,
            status=UserCloudflareDomain.SYNC_ERROR,
            message=waf_message,
            warnings=warnings,
        )

    zone_result: ZoneSettingsSyncResult = sync_zone_settings(domain, token)
    warnings.extend(zone_result.warnings)

    if not zone_result.ok:
        _update_domain_sync(domain, UserCloudflareDomain.SYNC_ERROR, zone_result.error)
        return DomainSyncResult(
            domain_id=domain.pk,
            domain_name=name,
            ok=False,
            status=UserCloudflareDomain.SYNC_ERROR,
            message=zone_result.error,
            warnings=warnings,
        )

    from tools.services.cloudflare_rate_limit import sync_rate_limit

    rate_result = sync_rate_limit(domain, token)
    warnings.extend(rate_result.warnings)

    if not rate_result.ok:
        _update_domain_sync(domain, UserCloudflareDomain.SYNC_ERROR, rate_result.error)
        return DomainSyncResult(
            domain_id=domain.pk,
            domain_name=name,
            ok=False,
            status=UserCloudflareDomain.SYNC_ERROR,
            message=rate_result.error,
            warnings=warnings,
        )

    skipped = waf_skipped and zone_result.skipped and rate_result.skipped
    parts: list[str] = []
    if not waf_skipped and waf_message and "Already synced" not in waf_message:
        parts.append(waf_message.rstrip("."))
    elif waf_skipped and not zone_result.changed:
        pass
    elif not waf_skipped:
        parts.append(waf_message.rstrip("."))

    if zone_result.changed and zone_result.details:
        parts.append("zone settings: " + ", ".join(zone_result.details))
    elif zone_result.changed:
        parts.append("zone settings updated")

    if rate_result.changed:
        parts.append("rate limit updated")

    if skipped:
        msg = "Already synced (no changes)."
    elif parts:
        msg = "Synced successfully." + (
            " (" + "; ".join(p for p in parts if p) + ")" if parts else ""
        )
    else:
        msg = waf_message or "Synced successfully."

    if warnings and not skipped:
        msg += " " + "; ".join(warnings)

    status = (
        UserCloudflareDomain.SYNC_WARNING
        if warnings
        else UserCloudflareDomain.SYNC_OK
    )
    _update_domain_sync(
        domain,
        status,
        msg if status == UserCloudflareDomain.SYNC_WARNING else "",
    )
    return DomainSyncResult(
        domain_id=domain.pk,
        domain_name=name,
        ok=True,
        status=status,
        message=msg,
        warnings=warnings,
        skipped=skipped,
    )


def _update_domain_sync(
    domain: UserCloudflareDomain,
    status: str,
    error: str,
) -> None:
    domain.last_synced_at = timezone.now()
    domain.last_sync_status = status
    domain.last_sync_error = error or ""
    domain.save(
        update_fields=[
            "last_synced_at",
            "last_sync_status",
            "last_sync_error",
            "updated_at",
        ]
    )


def sync_global_subnets_for_zones(
    domains: list[UserCloudflareDomain],
) -> list[DomainSyncResult]:
    """Push global blocked subnets once per zone_id (admin batch step)."""
    by_zone: dict[str, UserCloudflareDomain] = {}
    for domain in domains:
        if not domain.is_active:
            continue
        current = by_zone.get(domain.zone_id)
        if current is None or domain.pk < current.pk:
            by_zone[domain.zone_id] = domain

    results: list[DomainSyncResult] = []
    for domain in sorted(by_zone.values(), key=lambda d: d.domain_name):
        subnet_result = sync_subnet_for_domain(domain)
        results.append(
            DomainSyncResult(
                domain_id=subnet_result.domain_id,
                domain_name=subnet_result.domain_name,
                ok=subnet_result.ok,
                status=subnet_result.status,
                message=f"[SUBNET] {subnet_result.message}",
                warnings=subnet_result.warnings,
                skipped=subnet_result.skipped,
            )
        )
    return results


def sync_all_domains() -> list[DomainSyncResult]:
    """Admin sync: global subnets once per zone, then per-domain user settings."""
    domains = list(
        UserCloudflareDomain.objects.filter(is_active=True).select_related("user")
    )
    results: list[DomainSyncResult] = []
    results.extend(sync_global_subnets_for_zones(domains))
    for domain in domains:
        results.append(sync_domain(domain, include_subnet=False))
    return results
