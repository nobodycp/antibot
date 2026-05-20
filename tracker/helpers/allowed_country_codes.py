"""Cached per-user list of allowed country codes for the tracker API decision path."""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser

from core.resilient_cache import safe_cache_delete, safe_cache_get, safe_cache_set

_CACHE_GEN_KEY = "tracker:allowed_country_codes_gen"
_CACHE_KEY_FMT = "tracker:allowed_country_codes_v2:{gen}:{user_id}"
_CACHE_TTL_SEC = 60
_LEGACY_CACHE_KEY = "tracker:allowed_country_codes_v1"


def _cache_generation() -> int:
    gen = safe_cache_get(_CACHE_GEN_KEY)
    if gen is None:
        return 0
    return int(gen)


def _cache_key(user_id: int) -> str:
    return _CACHE_KEY_FMT.format(gen=_cache_generation(), user_id=user_id)


def get_allowed_country_codes(user: AbstractBaseUser) -> list[str]:
    key = _cache_key(user.pk)
    cached = safe_cache_get(key)
    if cached is not None:
        return cached
    from ..models import AllowedCountry

    codes = list(
        AllowedCountry.objects.filter(owner_id=user.pk)
        .order_by("code")
        .values_list("code", flat=True)
    )
    safe_cache_set(key, codes, _CACHE_TTL_SEC)
    return codes


def invalidate_allowed_country_codes_cache() -> None:
    safe_cache_delete(_LEGACY_CACHE_KEY)
    try:
        gen = safe_cache_get(_CACHE_GEN_KEY)
        if gen is None:
            safe_cache_set(_CACHE_GEN_KEY, 1, None)
        else:
            safe_cache_set(_CACHE_GEN_KEY, int(gen) + 1, None)
    except (TypeError, ValueError):
        safe_cache_set(_CACHE_GEN_KEY, 1, None)
