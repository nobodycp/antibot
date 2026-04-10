"""Cached blocked-subnet CIDR list + membership test (global blocklist)."""

from __future__ import annotations

import ipaddress
from functools import lru_cache

from core.resilient_cache import safe_cache_delete, safe_cache_get, safe_cache_set

from ..models import BlockedSubnet

_CACHE_KEY = "tracker:blocked_subnet_cidrs_v1"
_CACHE_TTL_SEC = 300


def get_blocked_subnet_cidr_list() -> list[str]:
    """Stable order by primary key; avoids a DB hit on every API request when warm."""
    cached = safe_cache_get(_CACHE_KEY)
    if isinstance(cached, list):
        return cached
    cidrs = list(
        BlockedSubnet.objects.order_by("id").values_list("cidr", flat=True)
    )
    safe_cache_set(_CACHE_KEY, cidrs, _CACHE_TTL_SEC)
    return cidrs


def invalidate_blocked_subnet_cidr_cache() -> None:
    safe_cache_delete(_CACHE_KEY)


@lru_cache(maxsize=64)
def _networks_for_cidr_tuple(cidr_tuple: tuple[str, ...]) -> tuple:
    nets = []
    for c in cidr_tuple:
        try:
            nets.append(ipaddress.ip_network(c, strict=False))
        except ValueError:
            continue
    return tuple(nets)


def ip_matches_global_blocked_subnet(ip: str) -> bool:
    """True if ip is contained in any stored CIDR (invalid ip string → False)."""
    try:
        ip_obj = ipaddress.ip_address(ip)
    except ValueError:
        return False
    cidrs = get_blocked_subnet_cidr_list()
    if not cidrs:
        return False
    for net in _networks_for_cidr_tuple(tuple(cidrs)):
        if ip_obj in net:
            return True
    return False
