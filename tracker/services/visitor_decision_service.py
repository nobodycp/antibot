import ipaddress
from dataclasses import dataclass
from typing import Optional

from django.db.models import Q

from ..models import (
    BlockedBrowser,
    BlockedHostname,
    BlockedIP,
    BlockedISP,
    BlockedOS,
    BlockedSubnet,
)
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


def evaluate_visitor_decision(ip: str, ctx: VisitorContext, allowed_codes) -> VisitorDecision:
    try:
        ip_obj = ipaddress.ip_address(ip)
        for cidr in BlockedSubnet.objects.values_list('cidr', flat=True):
            try:
                if ip_obj in ipaddress.ip_network(cidr, strict=False):
                    return VisitorDecision(allowed=False, reason="Subnet")
            except ValueError:
                continue
    except ValueError:
        pass

    if BlockedIP.objects.filter(ip_address=ip).exists():
        return VisitorDecision(allowed=False, reason="IP")

    if BlockedISP.objects.filter(isp__iexact=ctx.isp).exists():
        return VisitorDecision(allowed=False, reason="ISP")

    if BlockedOS.objects.filter(os__iexact=ctx.os.strip()).exists():
        return VisitorDecision(allowed=False, reason="OS")

    if BlockedBrowser.objects.filter(browser__iexact=ctx.browser.strip()).exists():
        return VisitorDecision(allowed=False, reason="Browser")

    if ctx.country_code not in allowed_codes:
        return VisitorDecision(allowed=False, reason="Country")

    if ctx.hostname and BlockedHostname.objects.filter(
            Q(hostname__icontains=ctx.hostname) | Q(hostname__in=ctx.hostname.split('.'))
    ).exists():
        return VisitorDecision(allowed=False, reason="Hostname")

    return VisitorDecision(allowed=True, reason=None)
