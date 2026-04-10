from ..models import (
    IPInfo,
    IPLog,
    RejectedVisitor,
    Visitor,
)
from .visitor_context_service import VisitorContext


def persist_rejected_visitor(ip: str, ctx: VisitorContext, reason: str) -> None:
    RejectedVisitor.objects.create(
        ip_address=ip,
        b_subnet=ctx.b_subnet,
        hostname=ctx.hostname,
        isp=ctx.isp,
        os=ctx.os,
        browser=ctx.browser,
        country=ctx.country_code,
        reason=reason,
    )


def persist_allowed_visitor(ip: str, user_agent_str: str, ctx: VisitorContext) -> None:
    Visitor.objects.create(
        ip_address=ip,
        b_subnet=ctx.b_subnet,
        # hostname=ctx.hostname,
        isp=ctx.isp,
        os=ctx.os,
        browser=ctx.browser,
        user_agent=user_agent_str,
        country=ctx.country_code,
    )

    IPInfo.objects.update_or_create(
        ip_address=ip,
        defaults={
            'isp': ctx.isp,
            'subnet': ctx.b_subnet,
            'as_type': ctx.as_type,
            'is_anonymous': ctx.is_anonymous,
            'is_proxy': ctx.is_proxy,
            'is_hosting': ctx.is_hosting,
            'is_tor': ctx.is_tor,
            'is_vpn': ctx.is_vpn,
            'is_satellite': ctx.is_satellite,
        },
    )

    ip_log, created = IPLog.objects.get_or_create(ip_address=ip)
    if not created:
        ip_log.count += 1
        ip_log.save()
