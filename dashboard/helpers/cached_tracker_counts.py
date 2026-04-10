"""Short-TTL cache for global tracker rule totals (same for all dashboard users)."""

from __future__ import annotations

from core.resilient_cache import safe_cache_delete, safe_cache_get, safe_cache_set

_CACHE_KEY = "dashboard:global_tracker_counts_v1"
_CACHE_TTL_SEC = 30


def get_cached_global_rule_counts() -> dict[str, int]:
    cached = safe_cache_get(_CACHE_KEY)
    if cached is not None:
        return cached
    from tracker.models import (
        AllowedCountry,
        BlockedBrowser,
        BlockedHostname,
        BlockedIP,
        BlockedISP,
        BlockedOS,
        BlockedSubnet,
    )

    data = {
        "total_blocked_ips": BlockedIP.objects.count(),
        "total_blocked_isps": BlockedISP.objects.count(),
        "total_blocked_browsers": BlockedBrowser.objects.count(),
        "total_blocked_os": BlockedOS.objects.count(),
        "total_blocked_subnets": BlockedSubnet.objects.count(),
        "total_blocked_hostnames": BlockedHostname.objects.count(),
        "total_allowed_countries": AllowedCountry.objects.count(),
    }
    safe_cache_set(_CACHE_KEY, data, _CACHE_TTL_SEC)
    return data


def invalidate_global_rule_counts_cache() -> None:
    safe_cache_delete(_CACHE_KEY)
