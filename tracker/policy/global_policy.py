"""
Single entry points for globally-scoped policy inputs used in visitor decisions.

Callers should import from here (not ad hoc model queries) so a future tenant_id
parameter can be threaded through without rewriting every decision site.
"""

from __future__ import annotations

from typing import Optional

from ..helpers.allowed_country_codes import get_allowed_country_codes
from ..helpers.blocked_subnet_rules import ip_matches_global_blocked_subnet


def allowed_country_codes() -> list[str]:
    """ISO country codes allowed for the global allowlist."""
    return get_allowed_country_codes()


def subnet_deny_reason_if_blocked(ip: str) -> Optional[str]:
    """Return the internal reason code 'Subnet' when the global subnet blocklist matches."""
    if ip_matches_global_blocked_subnet(ip):
        return "Subnet"
    return None
