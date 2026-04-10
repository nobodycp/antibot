"""
Evaluate whether a visitor should be allowed based on IP, enriched context, and blocklists.

Decision order is fixed; changing the order would change API behavior.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from django.db.models import Q

from ..models import (
    BlockedBrowser,
    BlockedHostname,
    BlockedIP,
    BlockedISP,
    BlockedOS,
)
from ..policy.global_policy import subnet_deny_reason_if_blocked
from .visitor_context_service import VisitorContext

_API_REASONS = {
    "Subnet": "Blocked Subnet",
    "IP": "Blocked IP",
    "ISP": "Blocked ISP",
    "OS": "Blocked OS",
    "Browser": "Blocked Browser",
    "Hostname": "Blocked Hostname",
}


@dataclass(frozen=True)
class VisitorDecision:
    allowed: bool
    reason: Optional[str]

    def response_reason(self, country_code: str) -> str:
        if self.allowed or self.reason is None:
            raise ValueError("VisitorDecision has no denial reason")
        if self.reason == "Country":
            return f'Country code "{country_code}" is not allowed'
        return _API_REASONS[self.reason]


def _deny_reason_subnet(ip: str) -> Optional[str]:
    return subnet_deny_reason_if_blocked(ip)


def _deny_reason_ip(ip: str) -> Optional[str]:
    if BlockedIP.objects.filter(ip_address=ip).exists():
        return "IP"
    return None


def _deny_reason_isp(ctx: VisitorContext) -> Optional[str]:
    if BlockedISP.objects.filter(isp__iexact=ctx.isp).exists():
        return "ISP"
    return None


def _deny_reason_os(ctx: VisitorContext) -> Optional[str]:
    if BlockedOS.objects.filter(os__iexact=ctx.os.strip()).exists():
        return "OS"
    return None


def _deny_reason_browser(ctx: VisitorContext) -> Optional[str]:
    if BlockedBrowser.objects.filter(browser__iexact=ctx.browser.strip()).exists():
        return "Browser"
    return None


def _deny_reason_country(ctx: VisitorContext, allowed_codes: Iterable[str]) -> Optional[str]:
    if ctx.country_code not in allowed_codes:
        return "Country"
    return None


def _deny_reason_hostname(ctx: VisitorContext) -> Optional[str]:
    if not ctx.hostname:
        return None
    if BlockedHostname.objects.filter(
        Q(hostname__icontains=ctx.hostname) | Q(hostname__in=ctx.hostname.split("."))
    ).exists():
        return "Hostname"
    return None


def evaluate_visitor_decision(ip: str, ctx: VisitorContext, allowed_codes) -> VisitorDecision:
    """Return allowed/denied; denial reasons follow fixed precedence (subnet → … → hostname)."""
    reason = _deny_reason_subnet(ip)
    if reason is not None:
        return VisitorDecision(allowed=False, reason=reason)
    reason = _deny_reason_ip(ip)
    if reason is not None:
        return VisitorDecision(allowed=False, reason=reason)
    reason = _deny_reason_isp(ctx)
    if reason is not None:
        return VisitorDecision(allowed=False, reason=reason)
    reason = _deny_reason_os(ctx)
    if reason is not None:
        return VisitorDecision(allowed=False, reason=reason)
    reason = _deny_reason_browser(ctx)
    if reason is not None:
        return VisitorDecision(allowed=False, reason=reason)
    reason = _deny_reason_country(ctx, allowed_codes)
    if reason is not None:
        return VisitorDecision(allowed=False, reason=reason)
    reason = _deny_reason_hostname(ctx)
    if reason is not None:
        return VisitorDecision(allowed=False, reason=reason)
    return VisitorDecision(allowed=True, reason=None)
