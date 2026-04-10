"""Cached, normalized blocked-hostname patterns for the visitor decision path."""

from __future__ import annotations

from collections.abc import Sequence

from core.resilient_cache import safe_cache_delete, safe_cache_get, safe_cache_set

from ..models import BlockedHostname

_CACHE_KEY = "tracker:blocked_hostname_rules_v1"
_CACHE_TTL_SEC = 300


def normalize_hostname_for_match(value: str) -> str:
    """Lowercase, strip, drop trailing dot (DNS FQDN style)."""
    return (value or "").strip().lower().rstrip(".")


def visitor_hostname_matches_blocked_list(host: str, rules_normalized: Sequence[str]) -> bool:
    """
    True if the visitor host matches any blocked pattern.

    Matching uses, in order:
    - exact normalized equality
    - suffix: host is ``*.rule`` (subdomain of rule)
    - reverse suffix: rule is ``*.host`` (legacy superdomain rules in DB)
    - single-label rules: rule has no ``.`` and equals one dot-separated label of host
    """
    h = normalize_hostname_for_match(host)
    if not h:
        return False
    for rn in rules_normalized:
        if not rn:
            continue
        if h == rn:
            return True
        if h.endswith("." + rn):
            return True
        if rn.endswith("." + h):
            return True
        if "." not in rn and rn in h.split("."):
            return True
    return False


def get_blocked_hostname_rules_normalized() -> tuple[str, ...]:
    cached = safe_cache_get(_CACHE_KEY)
    if isinstance(cached, list):
        return tuple(str(x) for x in cached)
    rules = tuple(
        normalize_hostname_for_match(h)
        for h in BlockedHostname.objects.order_by("id").values_list("hostname", flat=True)
        if normalize_hostname_for_match(h)
    )
    safe_cache_set(_CACHE_KEY, list(rules), _CACHE_TTL_SEC)
    return rules


def invalidate_blocked_hostname_rules_cache() -> None:
    safe_cache_delete(_CACHE_KEY)
