from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from ..helpers.dashboard_views_helper import (
    build_dashboard_alerts,
    minute_ago_cutoff,
    start_of_today,
    top_countries_queryset,
    top_isps_queryset,
)
from tracker.models import (
    AllowedCountry,
    BlockedBrowser,
    BlockedHostname,
    BlockedIP,
    BlockedISP,
    BlockedOS,
    BlockedSubnet,
    IPLog,
    RejectedVisitor,
    Visitor,
)


@login_required
def dashboard_home(request):
    now = timezone.now()
    today_start = start_of_today(now)
    minute_ago = minute_ago_cutoff(now)

    total_visitors = Visitor.objects.count()
    total_denied = RejectedVisitor.objects.count()
    total_allowed = total_visitors
    total_blocked_ips = BlockedIP.objects.count()
    total_blocked_isps = BlockedISP.objects.count()
    total_blocked_browsers = BlockedBrowser.objects.count()
    total_blocked_os = BlockedOS.objects.count()
    total_blocked_subnets = BlockedSubnet.objects.count()
    total_blocked_hostnames = BlockedHostname.objects.count()
    total_allowed_countries = AllowedCountry.objects.count()

    visitors_today = Visitor.objects.filter(timestamp__gte=today_start).count()
    denied_today = RejectedVisitor.objects.filter(timestamp__gte=today_start).count()
    unique_ips_today = Visitor.objects.filter(timestamp__gte=today_start).values('ip_address').distinct().count()
    live_last_minute = Visitor.objects.filter(timestamp__gte=minute_ago).count()

    latest_allowed = Visitor.objects.order_by('-timestamp')[:10]
    latest_denied = RejectedVisitor.objects.order_by('-timestamp')[:10]

    top_ips = (
        IPLog.objects.order_by('-count', '-last_seen')[:10]
    )

    top_countries = top_countries_queryset()
    top_isps = top_isps_queryset()

    alerts = build_dashboard_alerts(
        visitors_today=visitors_today,
        denied_today=denied_today,
    )

    context = {
        'total_visitors': total_visitors,
        'total_denied': total_denied,
        'total_allowed': total_allowed,
        'total_blocked_ips': total_blocked_ips,
        'total_blocked_isps': total_blocked_isps,
        'total_blocked_browsers': total_blocked_browsers,
        'total_blocked_os': total_blocked_os,
        'total_blocked_subnets': total_blocked_subnets,
        'total_blocked_hostnames': total_blocked_hostnames,
        'total_allowed_countries': total_allowed_countries,
        'visitors_today': visitors_today,
        'denied_today': denied_today,
        'unique_ips_today': unique_ips_today,
        'live_last_minute': live_last_minute,
        'latest_allowed': latest_allowed,
        'latest_denied': latest_denied,
        'top_ips': top_ips,
        'top_countries': top_countries,
        'top_isps': top_isps,
        'alerts': alerts,
        'last_update': now,
    }
    return render(request, 'dashboard/home.html', context)


@login_required
def home_stats_partial(request):
    now = timezone.now()
    minute_ago = minute_ago_cutoff(now)

    total_visitors = Visitor.objects.count()
    total_denied = RejectedVisitor.objects.count()
    total_blocked_ips = BlockedIP.objects.count()
    live_last_minute = Visitor.objects.filter(timestamp__gte=minute_ago).count()

    return render(request, 'dashboard/partials/home_stats_partial.html', {
        'total_visitors': total_visitors,
        'total_denied': total_denied,
        'total_blocked_ips': total_blocked_ips,
        'live_last_minute': live_last_minute,
    })


@login_required
def home_secondary_stats_partial(request):
    now = timezone.now()
    today_start = start_of_today(now)

    visitors_today = Visitor.objects.filter(timestamp__gte=today_start).count()
    denied_today = RejectedVisitor.objects.filter(timestamp__gte=today_start).count()
    unique_ips_today = Visitor.objects.filter(timestamp__gte=today_start).values('ip_address').distinct().count()
    total_blocked_isps = BlockedISP.objects.count()
    total_blocked_subnets = BlockedSubnet.objects.count()

    context = {
        'visitors_today': visitors_today,
        'denied_today': denied_today,
        'unique_ips_today': unique_ips_today,
        'total_blocked_isps': total_blocked_isps,
        'total_blocked_subnets': total_blocked_subnets,
    }
    return render(request, 'dashboard/partials/home_secondary_stats_partial.html', context)


@login_required
def home_alerts_partial(request):
    now = timezone.now()
    today_start = start_of_today(now)

    total_blocked_browsers = BlockedBrowser.objects.count()
    total_blocked_os = BlockedOS.objects.count()
    total_blocked_hostnames = BlockedHostname.objects.count()
    total_allowed_countries = AllowedCountry.objects.count()

    visitors_today = Visitor.objects.filter(timestamp__gte=today_start).count()
    denied_today = RejectedVisitor.objects.filter(timestamp__gte=today_start).count()

    alerts = build_dashboard_alerts(
        visitors_today=visitors_today,
        denied_today=denied_today,
    )

    context = {
        'alerts': alerts,
        'total_blocked_browsers': total_blocked_browsers,
        'total_blocked_os': total_blocked_os,
        'total_blocked_hostnames': total_blocked_hostnames,
        'total_allowed_countries': total_allowed_countries,
        'last_update': now,
    }
    return render(request, 'dashboard/partials/home_alerts_partial.html', context)


@login_required
def home_latest_logs_partial(request):
    latest_allowed = Visitor.objects.order_by('-timestamp')[:10]
    latest_denied = RejectedVisitor.objects.order_by('-timestamp')[:10]

    context = {
        'latest_allowed': latest_allowed,
        'latest_denied': latest_denied,
    }
    return render(request, 'dashboard/partials/home_latest_logs_partial.html', context)


@login_required
def home_top_ips_partial(request):
    top_ips = IPLog.objects.order_by('-count', '-last_seen')[:10]

    top_countries = top_countries_queryset()
    top_isps = top_isps_queryset()

    context = {
        'top_ips': top_ips,
        'top_countries': top_countries,
        'top_isps': top_isps,
    }
    return render(request, 'dashboard/partials/home_top_ips_partial.html', context)
