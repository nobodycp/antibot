"""
Central invalidation for tracker rule caches (API decision path + dashboard totals).

Bulk QuerySet.delete() does not emit per-row post_delete signals; call
``invalidate_tracker_rule_caches()`` explicitly after mass deletes in views.
"""

from __future__ import annotations

from dashboard.helpers.cached_tracker_counts import invalidate_global_rule_counts_cache

from .helpers.allowed_country_codes import invalidate_allowed_country_codes_cache
from .helpers.blocked_hostname_rules import invalidate_blocked_hostname_rules_cache
from .helpers.blocked_subnet_rules import invalidate_blocked_subnet_cidr_cache


def invalidate_tracker_rule_caches() -> None:
    invalidate_allowed_country_codes_cache()
    invalidate_blocked_subnet_cidr_cache()
    invalidate_blocked_hostname_rules_cache()
    invalidate_global_rule_counts_cache()
