from datetime import timedelta

from django.contrib import messages
from django.db.models import Count
from django.shortcuts import redirect

from tracker.models import IPLog, RejectedVisitor, Visitor


def start_of_today(now):
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def minute_ago_cutoff(now, minutes=1):
    return now - timedelta(minutes=minutes)


def build_dashboard_alerts(*, visitors_today, denied_today):
    alerts = []

    repeated_ips = IPLog.objects.filter(count__gte=10).order_by('-count')[:5]
    for item in repeated_ips:
        alerts.append({
            'type': 'danger',
            'text': f"IP {item.ip_address} repeated {item.count} times."
        })

    repeated_denied = (
        RejectedVisitor.objects.values('ip_address')
        .annotate(total=Count('id'))
        .order_by('-total')[:5]
    )
    for item in repeated_denied:
        if item['total'] >= 5:
            alerts.append({
                'type': 'warning',
                'text': f"Denied IP {item['ip_address']} triggered {item['total']} denied logs."
            })

    if denied_today > visitors_today and denied_today > 0:
        alerts.append({
            'type': 'danger',
            'text': "Denied logs today are higher than allowed visitors."
        })

    if not alerts:
        alerts.append({
            'type': 'success',
            'text': "No major alerts right now."
        })

    return alerts


def top_countries_queryset():
    return (
        Visitor.objects.exclude(country__isnull=True)
        .exclude(country__exact='')
        .values('country')
        .annotate(total=Count('id'))
        .order_by('-total')[:10]
    )


def top_isps_queryset():
    return (
        Visitor.objects.exclude(isp__isnull=True)
        .exclude(isp__exact='')
        .values('isp')
        .annotate(total=Count('id'))
        .order_by('-total')[:10]
    )


def redirect_if_telegram_unconfigured(request, settings_obj):
    if settings_obj and settings_obj.bot_token and settings_obj.chat_id:
        return None
    messages.error(request, "Telegram settings not configured")
    return redirect("dashboard:telegram_backup_settings")
