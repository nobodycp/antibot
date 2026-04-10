"""
Persist allowed visitors (Visitor, IPInfo, IPLog) and rejected visitors (RejectedVisitor).

Views call these after a decision; no decision logic lives here.
"""
from __future__ import annotations

from ..models import (
    IPInfo,
    IPLog,
    RejectedVisitor,
    Visitor,
)
from .visitor_context_service import VisitorContext


def _ipinfo_defaults(ctx: VisitorContext) -> dict:
    return {
        "isp": ctx.isp,
        "subnet": ctx.b_subnet,
        "as_type": ctx.as_type,
        "is_anonymous": ctx.is_anonymous,
        "is_proxy": ctx.is_proxy,
        "is_hosting": ctx.is_hosting,
        "is_tor": ctx.is_tor,
        "is_vpn": ctx.is_vpn,
        "is_satellite": ctx.is_satellite,
    }


def persist_rejected_visitor(ip: str, ctx: VisitorContext, reason: str) -> None:
    """Record a denied visit with the raw block reason code (e.g. \"IP\", \"Country\")."""
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
    """Insert Visitor row, upsert IPInfo from context, bump IPLog counter."""
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
        defaults=_ipinfo_defaults(ctx),
    )

    ip_log, created = IPLog.objects.get_or_create(ip_address=ip)
    if not created:
        ip_log.count += 1
        ip_log.save()
