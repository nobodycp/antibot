"""
Sync per-domain Cloudflare zone settings and Bot Management config.

Zone settings: PATCH /zones/{zone_id}/settings/{setting_id}
Bot features: PUT /zones/{zone_id}/bot_management (plan-dependent)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from dashboard.models import UserCloudflareDomain

logger = logging.getLogger(__name__)


@dataclass
class ZoneSettingsSyncResult:
    ok: bool
    changed: bool = False
    skipped: bool = False
    warnings: list[str] = field(default_factory=list)
    error: str = ""
    details: list[str] = field(default_factory=list)


def _cf_request(method: str, path: str, token: str, **kwargs):
    from tools.services.cloudflare_sync_service import _cf_request as req

    return req(method, path, token, **kwargs)


def _get_zone_setting_value(token: str, zone_id: str, setting_id: str) -> tuple[bool, Any, str]:
    ok, payload, err = _cf_request(
        "GET",
        f"/zones/{zone_id}/settings/{setting_id}",
        token,
    )
    if not ok:
        return False, None, err
    result = (payload or {}).get("result") or {}
    return True, result.get("value"), ""


def _patch_zone_setting(
    token: str, zone_id: str, setting_id: str, value: Any
) -> tuple[bool, str]:
    ok, _, err = _cf_request(
        "PATCH",
        f"/zones/{zone_id}/settings/{setting_id}",
        token,
        json_body={"value": value},
    )
    return ok, err


def _on_off(enabled: bool) -> str:
    return "on" if enabled else "off"


def _bool_from_on_off(value: Any) -> bool:
    return str(value or "").lower() in ("on", "true", "1")


_ON_OFF_ZONE_SETTING_IDS = frozenset(
    {
        "always_use_https",
        "browser_check",
        "http3",
        "0rtt",
        "automatic_https_rewrites",
    }
)


def effective_security_level(domain: UserCloudflareDomain) -> str:
    if domain.under_attack_mode:
        return UserCloudflareDomain.SECURITY_UNDER_ATTACK
    return UserCloudflareDomain.normalize_security_level(domain.security_level)


def _migrate_legacy_security_level(domain: UserCloudflareDomain) -> list[str]:
    """Persist fix for Enterprise-only security_level=off stored in DB."""
    if domain.security_level != UserCloudflareDomain.SECURITY_OFF:
        return []
    domain.security_level = UserCloudflareDomain.SECURITY_ESSENTIALLY_OFF
    domain.save(update_fields=["security_level", "updated_at"])
    msg = (
        "security_level 'off' is Enterprise-only; "
        "migrated stored value to essentially_off"
    )
    logger.warning("%s: %s", domain.domain_name, msg)
    return [msg]


def _get_bot_management(token: str, zone_id: str) -> tuple[bool, dict, str]:
    ok, payload, err = _cf_request(
        "GET",
        f"/zones/{zone_id}/bot_management",
        token,
    )
    if not ok:
        return False, {}, err
    return True, (payload or {}).get("result") or {}, ""


def _put_bot_management(
    token: str, zone_id: str, body: dict
) -> tuple[bool, str]:
    ok, _, err = _cf_request(
        "PUT",
        f"/zones/{zone_id}/bot_management",
        token,
        json_body=body,
    )
    return ok, err


def _desired_bot_management(domain: UserCloudflareDomain) -> dict:
    return {
        "fight_mode": bool(domain.bot_fight_mode),
        "ai_bots_protection": "block" if domain.block_ai_bots else "disabled",
        "crawler_protection": "enabled" if domain.ai_labyrinth else "disabled",
        "content_bots_protection": "block" if domain.ai_crawl_control else "disabled",
    }


def _bot_field_matches(current: dict, key: str, desired_value: Any) -> bool:
    return current.get(key) == desired_value


def _sync_single_zone_setting(
    domain: UserCloudflareDomain,
    token: str,
    setting_id: str,
    desired: Any,
    *,
    normalize_current: Optional[Callable[[Any], Any]] = None,
    normalize_desired: Optional[Callable[[Any], Any]] = None,
) -> tuple[bool, bool, str]:
    """Returns (ok, changed, error)."""
    ok, current, err = _get_zone_setting_value(token, domain.zone_id, setting_id)
    if not ok:
        return False, False, err

    norm_cur = normalize_current(current) if normalize_current else current
    norm_des = normalize_desired(desired) if normalize_desired else desired

    if norm_cur == norm_des:
        logger.debug(
            "%s: zone setting %s already %r",
            domain.domain_name,
            setting_id,
            norm_des,
        )
        return True, False, ""

    ok, err = _patch_zone_setting(token, domain.zone_id, setting_id, desired)
    return ok, ok, err


def sync_zone_settings(
    domain: UserCloudflareDomain,
    token: str,
) -> ZoneSettingsSyncResult:
    """
    Push DB zone settings to Cloudflare. GET-before-PATCH per setting.
    """
    warnings: list[str] = []
    details: list[str] = []
    any_changed = False

    warnings.extend(_migrate_legacy_security_level(domain))

    zone_specs: list[tuple[str, Any]] = [
        ("always_use_https", _on_off(domain.always_use_https)),
        ("browser_check", _on_off(domain.browser_integrity_check)),
        ("http3", _on_off(domain.http3_enabled)),
        ("0rtt", _on_off(domain.zero_rtt_enabled)),
        ("automatic_https_rewrites", _on_off(domain.automatic_https_rewrites)),
        ("ssl", domain.ssl_mode),
        ("min_tls_version", domain.min_tls_version),
        ("security_level", effective_security_level(domain)),
        ("challenge_ttl", int(domain.challenge_ttl)),
    ]

    for setting_id, desired in zone_specs:
        normalize = _bool_from_on_off if setting_id in _ON_OFF_ZONE_SETTING_IDS else None
        ok, changed, err = _sync_single_zone_setting(
            domain,
            token,
            setting_id,
            desired,
            normalize_current=normalize,
            normalize_desired=normalize,
        )
        if not ok:
            return ZoneSettingsSyncResult(
                ok=False,
                changed=any_changed,
                error=f"{setting_id}: {err}",
                warnings=warnings,
                details=details,
            )
        if changed:
            any_changed = True
            details.append(f"{setting_id} updated")

    desired_bot = _desired_bot_management(domain)
    ok, current_bot, err = _get_bot_management(token, domain.zone_id)
    if not ok:
        warnings.append(
            f"Bot Management API unavailable ({err}); "
            "bot/AI toggles stored locally only (may require Bot Fight Mode plan)."
        )
        logger.warning(
            "%s: bot_management GET failed: %s",
            domain.domain_name,
            err,
        )
        return ZoneSettingsSyncResult(
            ok=True,
            changed=any_changed,
            skipped=not any_changed,
            warnings=warnings,
            details=details,
        )

    patch_body: dict = {}
    for key, desired_val in desired_bot.items():
        if not _bot_field_matches(current_bot, key, desired_val):
            patch_body[key] = desired_val

    if patch_body:
        ok, err = _put_bot_management(token, domain.zone_id, patch_body)
        if not ok:
            warnings.append(
                f"Bot Management update failed ({err}); "
                "check plan supports Bot Fight Mode / AI bot rules."
            )
            return ZoneSettingsSyncResult(
                ok=True,
                changed=any_changed,
                warnings=warnings,
                details=details,
            )
        any_changed = True
        details.append("bot_management updated")

    return ZoneSettingsSyncResult(
        ok=True,
        changed=any_changed,
        skipped=not any_changed,
        warnings=warnings,
        details=details,
    )
