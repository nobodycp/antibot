"""Cached list of allowed country codes for the tracker API decision path."""

from __future__ import annotations

from django.core.cache import cache

_CACHE_KEY = "tracker:allowed_country_codes_v1"
_CACHE_TTL_SEC = 60


def get_allowed_country_codes() -> list[str]:
    cached = cache.get(_CACHE_KEY)
    if cached is not None:
        return cached
    from ..models import AllowedCountry

    codes = list(
        AllowedCountry.objects.order_by("code").values_list("code", flat=True)
    )
    cache.set(_CACHE_KEY, codes, _CACHE_TTL_SEC)
    return codes


def invalidate_allowed_country_codes_cache() -> None:
    cache.delete(_CACHE_KEY)
