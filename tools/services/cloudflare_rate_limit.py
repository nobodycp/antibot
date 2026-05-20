"""
Push antibot rate limiting rules to Cloudflare (http_ratelimit phase entrypoint).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from dashboard.models import UserCloudflareDomain

logger = logging.getLogger(__name__)


def _cf_request(method: str, path: str, token: str, **kwargs):
    """Delegate to shared Cloudflare HTTP helper (lazy import avoids cycles)."""
    from tools.services.cloudflare_sync_service import _cf_request as cf_request

    return cf_request(method, path, token, **kwargs)

RATE_LIMIT_PHASE = "http_ratelimit"
RATE_LIMIT_RULE_DESC = "antibot:rate-limit"
DEFAULT_RATE_LIMIT_EXPRESSION = "true"
# cf.colo.id is mandatory: rate limiting counters are per colocation.
DEFAULT_CHARACTERISTICS = ["ip.src", "cf.colo.id"]


@dataclass
class RateLimitSyncResult:
    ok: bool
    skipped: bool = True
    changed: bool = False
    error: str = ""
    warnings: list[str] = field(default_factory=list)


def _effective_requests(domain: UserCloudflareDomain) -> int:
    return domain.rate_limit_requests if domain.rate_limit_requests is not None else 30


def build_rate_limit_rule(domain: UserCloudflareDomain) -> dict:
    """Build a Cloudflare rate limit rule payload from domain DB fields."""
    return {
        "description": RATE_LIMIT_RULE_DESC,
        "expression": DEFAULT_RATE_LIMIT_EXPRESSION,
        "action": domain.rate_limit_action,
        "enabled": True,
        "ratelimit": {
            "characteristics": list(DEFAULT_CHARACTERISTICS),
            "period": int(domain.rate_limit_period_seconds),
            "requests_per_period": _effective_requests(domain),
            "mitigation_timeout": int(domain.rate_limit_duration_seconds),
        },
    }


def _rule_ratelimit(rule: dict) -> dict:
    """Rate limit config may be top-level or under action_parameters."""
    rl = rule.get("ratelimit")
    if rl:
        return rl
    ap = rule.get("action_parameters") or {}
    return ap.get("ratelimit") or {}


def _ratelimit_matches(existing: dict, desired: dict) -> bool:
    existing_rl = _rule_ratelimit(existing)
    desired_rl = _rule_ratelimit(desired)
    if sorted(existing_rl.get("characteristics") or []) != sorted(
        desired_rl.get("characteristics") or []
    ):
        return False
    keys = ("period", "requests_per_period", "mitigation_timeout")
    for key in keys:
        if existing_rl.get(key) != desired_rl.get(key):
            return False
    return True


def rate_limit_config_matches(existing: dict, desired: dict) -> bool:
    """Match action, expression, enabled, and ratelimit (ignore description)."""
    return (
        (existing.get("action") or "").strip()
        == (desired.get("action") or "").strip()
        and (existing.get("expression") or "").strip()
        == (desired.get("expression") or "").strip()
        and bool(existing.get("enabled", True)) == bool(desired.get("enabled", True))
        and _ratelimit_matches(existing, desired)
    )


def rate_limit_rule_matches(existing: dict, desired: dict) -> bool:
    return (
        (existing.get("description") or "").strip()
        == (desired.get("description") or "").strip()
        and rate_limit_config_matches(existing, desired)
    )


def _find_rate_limit_rule(rules: list[dict]) -> Optional[dict]:
    for rule in rules:
        if (rule.get("description") or "").strip() == RATE_LIMIT_RULE_DESC:
            return rule
    return None


def _is_antibot_rate_limit_rule(rule: dict) -> bool:
    return (rule.get("description") or "").strip() == RATE_LIMIT_RULE_DESC


def _find_adoptable_rate_limit_rule(
    rules: list[dict], desired: dict
) -> Optional[dict]:
    """
    When the zone has a single non-antibot rule matching our config, adopt it.

    Avoids exceeding plan limits (e.g. one http_ratelimit rule) by updating in place.
    """
    if _find_rate_limit_rule(rules) is not None or len(rules) != 1:
        return None
    candidate = rules[0]
    return candidate if rate_limit_config_matches(candidate, desired) else None


def _resolve_existing_rate_limit_rule(
    rules: list[dict], desired: dict
) -> Optional[dict]:
    return _find_rate_limit_rule(rules) or _find_adoptable_rate_limit_rule(
        rules, desired
    )


def _merge_rules_for_put(
    existing_rules: list[dict],
    existing_rule: Optional[dict],
    desired_rule: dict,
) -> list[dict]:
    if existing_rule is None:
        kept = [r for r in existing_rules if not _is_antibot_rate_limit_rule(r)]
        return kept + [desired_rule]

    updated = dict(desired_rule)
    target_id = existing_rule.get("id")
    if target_id:
        updated["id"] = target_id
    kept = [
        r
        for r in existing_rules
        if not _is_antibot_rate_limit_rule(r)
        and (not target_id or r.get("id") != target_id)
    ]
    return kept + [updated]


def _get_entrypoint(token: str, zone_id: str) -> tuple[bool, list[dict], str, str]:
    ok, payload, err = _cf_request(
        "GET",
        f"/zones/{zone_id}/rulesets/phases/{RATE_LIMIT_PHASE}/entrypoint",
        token,
    )
    if not ok:
        return False, [], "", err

    result = payload.get("result") or {}
    ruleset_id = result.get("id") or ""
    rules = list(result.get("rules") or [])
    return True, rules, ruleset_id, ""


def _put_entrypoint_rules(
    zone_id: str, token: str, ruleset_id: str, rules: list[dict]
) -> tuple[bool, str]:
    ok, _, err = _cf_request(
        "PUT",
        f"/zones/{zone_id}/rulesets/{ruleset_id}",
        token,
        json_body={"rules": rules},
    )
    return ok, err


def sync_rate_limit(domain: UserCloudflareDomain, token: str) -> RateLimitSyncResult:
    """
    Ensure the antibot rate limit rule on Cloudflare matches the domain row.

    When disabled in DB, removes the antibot rate limit rule if present.
    """
    ok, existing_rules, ruleset_id, err = _get_entrypoint(token, domain.zone_id)
    if not ok:
        return RateLimitSyncResult(ok=False, skipped=False, error=err)

    if not ruleset_id:
        return RateLimitSyncResult(
            ok=False,
            skipped=False,
            error="Missing http_ratelimit ruleset id from Cloudflare",
        )

    desired_rule = build_rate_limit_rule(domain) if domain.rate_limit_enabled else None
    existing_rule = (
        _resolve_existing_rate_limit_rule(existing_rules, desired_rule)
        if desired_rule
        else _find_rate_limit_rule(existing_rules)
    )

    if desired_rule is None:
        if existing_rule is None:
            logger.debug("%s: rate limit disabled, no CF rule", domain.domain_name)
            return RateLimitSyncResult(ok=True, skipped=True, changed=False)
        merged = [r for r in existing_rules if not _is_antibot_rate_limit_rule(r)]
        ok, err = _put_entrypoint_rules(
            domain.zone_id, token, ruleset_id, merged
        )
        if not ok:
            return RateLimitSyncResult(ok=False, skipped=False, error=err)
        return RateLimitSyncResult(ok=True, skipped=False, changed=True)

    if existing_rule is not None and rate_limit_rule_matches(existing_rule, desired_rule):
        logger.debug("%s: rate limit already matches DB", domain.domain_name)
        return RateLimitSyncResult(ok=True, skipped=True, changed=False)

    merged = _merge_rules_for_put(existing_rules, existing_rule, desired_rule)

    ok, err = _put_entrypoint_rules(domain.zone_id, token, ruleset_id, merged)
    if not ok:
        return RateLimitSyncResult(ok=False, skipped=False, error=err)
    return RateLimitSyncResult(ok=True, skipped=False, changed=True)
