"""Per-user short-TTL cache for expensive dashboard log count() queries."""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser

from core.resilient_cache import safe_cache_get, safe_cache_set

from .dashboard_views_helper import minute_ago_cutoff, start_of_today
from tracker.helpers.ownership import rejected_logs_queryset, visitor_logs_queryset

_CACHE_KEY_FMT = "dashboard:user_log_counts_v1:{user_id}"
_CACHE_TTL_SEC = 25


def _cache_key(user_id: int) -> str:
    return _CACHE_KEY_FMT.format(user_id=user_id)


def get_cached_user_log_counts(user: AbstractBaseUser, now) -> dict[str, int]:
    """
    Aggregate counts for the dashboard home and HTMX partials.

    Cached briefly per user; if cache fails, runs the same DB queries as before.
    """
    key = _cache_key(user.pk)
    cached = safe_cache_get(key)
    if isinstance(cached, dict):
        required = (
            "total_visitors",
            "total_denied",
            "visitors_today",
            "denied_today",
            "unique_ips_today",
            "live_last_minute",
        )
        if all(k in cached for k in required):
            return cached  # type: ignore[return-value]

    vqs = visitor_logs_queryset(user)
    rqs = rejected_logs_queryset(user)
    today_start = start_of_today(now)
    minute_ago = minute_ago_cutoff(now)

    data = {
        "total_visitors": vqs.count(),
        "total_denied": rqs.count(),
        "visitors_today": vqs.filter(timestamp__gte=today_start).count(),
        "denied_today": rqs.filter(timestamp__gte=today_start).count(),
        "unique_ips_today": (
            vqs.filter(timestamp__gte=today_start)
            .values("ip_address")
            .distinct()
            .count()
        ),
        "live_last_minute": vqs.filter(timestamp__gte=minute_ago).count(),
    }
    safe_cache_set(key, data, _CACHE_TTL_SEC)
    return data
