from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from ..helpers.cached_tracker_counts import get_cached_global_rule_counts
from ..helpers.dashboard_views_helper import (
    build_dashboard_alerts,
    minute_ago_cutoff,
    start_of_today,
    top_countries_queryset,
    top_isps_queryset,
)
from tracker.helpers.ownership import (
    ip_log_queryset,
    rejected_logs_queryset,
    visitor_logs_queryset,
)


@login_required
def dashboard_home(request):
    now = timezone.now()
    today_start = start_of_today(now)
    minute_ago = minute_ago_cutoff(now)
    user = request.user

    vqs = visitor_logs_queryset(user)
    rqs = rejected_logs_queryset(user)

    total_visitors = vqs.count()
    total_denied = rqs.count()
    total_allowed = total_visitors
    global_counts = get_cached_global_rule_counts()

    visitors_today = vqs.filter(timestamp__gte=today_start).count()
    denied_today = rqs.filter(timestamp__gte=today_start).count()
    unique_ips_today = (
        vqs.filter(timestamp__gte=today_start).values("ip_address").distinct().count()
    )
    live_last_minute = vqs.filter(timestamp__gte=minute_ago).count()

    latest_allowed = vqs.order_by("-timestamp")[:10]
    latest_denied = rqs.order_by("-timestamp")[:10]

    top_ips = ip_log_queryset(user).order_by("-count", "-last_seen")[:10]

    top_countries = top_countries_queryset(user)
    top_isps = top_isps_queryset(user)

    alerts = build_dashboard_alerts(
        visitors_today=visitors_today,
        denied_today=denied_today,
        user=user,
    )

    context = {
        'total_visitors': total_visitors,
        'total_denied': total_denied,
        'total_allowed': total_allowed,
        **global_counts,
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
    user = request.user
    vqs = visitor_logs_queryset(user)
    rqs = rejected_logs_queryset(user)

    total_visitors = vqs.count()
    total_denied = rqs.count()
    total_blocked_ips = get_cached_global_rule_counts()["total_blocked_ips"]
    live_last_minute = vqs.filter(timestamp__gte=minute_ago).count()

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
    user = request.user
    vqs = visitor_logs_queryset(user)
    rqs = rejected_logs_queryset(user)

    visitors_today = vqs.filter(timestamp__gte=today_start).count()
    denied_today = rqs.filter(timestamp__gte=today_start).count()
    unique_ips_today = (
        vqs.filter(timestamp__gte=today_start).values("ip_address").distinct().count()
    )
    global_rule_counts = get_cached_global_rule_counts()

    context = {
        'visitors_today': visitors_today,
        'denied_today': denied_today,
        'unique_ips_today': unique_ips_today,
        'total_blocked_isps': global_rule_counts["total_blocked_isps"],
        'total_blocked_subnets': global_rule_counts["total_blocked_subnets"],
    }
    return render(request, 'dashboard/partials/home_secondary_stats_partial.html', context)


@login_required
def home_alerts_partial(request):
    now = timezone.now()
    today_start = start_of_today(now)
    user = request.user
    vqs = visitor_logs_queryset(user)
    rqs = rejected_logs_queryset(user)

    global_rule_counts = get_cached_global_rule_counts()

    visitors_today = vqs.filter(timestamp__gte=today_start).count()
    denied_today = rqs.filter(timestamp__gte=today_start).count()

    alerts = build_dashboard_alerts(
        visitors_today=visitors_today,
        denied_today=denied_today,
        user=user,
    )

    context = {
        'alerts': alerts,
        'total_blocked_browsers': global_rule_counts["total_blocked_browsers"],
        'total_blocked_os': global_rule_counts["total_blocked_os"],
        'total_blocked_hostnames': global_rule_counts["total_blocked_hostnames"],
        'total_allowed_countries': global_rule_counts["total_allowed_countries"],
        'last_update': now,
    }
    return render(request, 'dashboard/partials/home_alerts_partial.html', context)


@login_required
def home_latest_logs_partial(request):
    user = request.user
    latest_allowed = visitor_logs_queryset(user).order_by('-timestamp')[:10]
    latest_denied = rejected_logs_queryset(user).order_by('-timestamp')[:10]

    context = {
        'latest_allowed': latest_allowed,
        'latest_denied': latest_denied,
    }
    return render(request, 'dashboard/partials/home_latest_logs_partial.html', context)


@login_required
def home_top_ips_partial(request):
    user = request.user
    top_ips = ip_log_queryset(user).order_by('-count', '-last_seen')[:10]

    top_countries = top_countries_queryset(user)
    top_isps = top_isps_queryset(user)

    context = {
        'top_ips': top_ips,
        'top_countries': top_countries,
        'top_isps': top_isps,
    }
    return render(request, 'dashboard/partials/home_top_ips_partial.html', context)
