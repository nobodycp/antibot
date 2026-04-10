from django.contrib import messages
from django.shortcuts import redirect, get_object_or_404
import requests
import tempfile
from django.core.management import call_command
import os
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import TelegramBackupSettings, UserProfile
from decorators import superuser_required
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.utils import timezone
from datetime import timedelta
from tracker.models import (
    Visitor,
    RejectedVisitor,
    BlockedIP,
    BlockedISP,
    BlockedBrowser,
    BlockedOS,
    BlockedSubnet,
    BlockedHostname,
    AllowedCountry,
    IPLog,
)


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    UserProfile.objects.get_or_create(user=instance)
    instance.profile.save()


@login_required
def dashboard_home(request):
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    minute_ago = now - timedelta(minutes=1)

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

    top_countries = (
        Visitor.objects.exclude(country__isnull=True)
        .exclude(country__exact='')
        .values('country')
        .annotate(total=Count('id'))
        .order_by('-total')[:10]
    )

    top_isps = (
        Visitor.objects.exclude(isp__isnull=True)
        .exclude(isp__exact='')
        .values('isp')
        .annotate(total=Count('id'))
        .order_by('-total')[:10]
    )

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
    return render(request, 'home.html', context)

@login_required
def home_stats_partial(request):
    from django.utils import timezone
    from datetime import timedelta

    now = timezone.now()
    minute_ago = now - timedelta(minutes=1)

    total_visitors = Visitor.objects.count()
    total_denied = RejectedVisitor.objects.count()
    total_blocked_ips = BlockedIP.objects.count()
    live_last_minute = Visitor.objects.filter(timestamp__gte=minute_ago).count()

    return render(request, 'partials/home_stats_partial.html', {
        'total_visitors': total_visitors,
        'total_denied': total_denied,
        'total_blocked_ips': total_blocked_ips,
        'live_last_minute': live_last_minute,
    })


@login_required
def home_secondary_stats_partial(request):
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

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
    return render(request, 'partials/home_secondary_stats_partial.html', context)


@login_required
def home_alerts_partial(request):
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    total_blocked_browsers = BlockedBrowser.objects.count()
    total_blocked_os = BlockedOS.objects.count()
    total_blocked_hostnames = BlockedHostname.objects.count()
    total_allowed_countries = AllowedCountry.objects.count()

    visitors_today = Visitor.objects.filter(timestamp__gte=today_start).count()
    denied_today = RejectedVisitor.objects.filter(timestamp__gte=today_start).count()

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

    context = {
        'alerts': alerts,
        'total_blocked_browsers': total_blocked_browsers,
        'total_blocked_os': total_blocked_os,
        'total_blocked_hostnames': total_blocked_hostnames,
        'total_allowed_countries': total_allowed_countries,
        'last_update': now,
    }
    return render(request, 'partials/home_alerts_partial.html', context)


@login_required
def home_latest_logs_partial(request):
    latest_allowed = Visitor.objects.order_by('-timestamp')[:10]
    latest_denied = RejectedVisitor.objects.order_by('-timestamp')[:10]

    context = {
        'latest_allowed': latest_allowed,
        'latest_denied': latest_denied,
    }
    return render(request, 'partials/home_latest_logs_partial.html', context)


@login_required
def home_top_ips_partial(request):
    top_ips = IPLog.objects.order_by('-count', '-last_seen')[:10]

    top_countries = (
        Visitor.objects.exclude(country__isnull=True)
        .exclude(country__exact='')
        .values('country')
        .annotate(total=Count('id'))
        .order_by('-total')[:10]
    )

    top_isps = (
        Visitor.objects.exclude(isp__isnull=True)
        .exclude(isp__exact='')
        .values('isp')
        .annotate(total=Count('id'))
        .order_by('-total')[:10]
    )

    context = {
        'top_ips': top_ips,
        'top_countries': top_countries,
        'top_isps': top_isps,
    }
    return render(request, 'partials/home_top_ips_partial.html', context)



@superuser_required
def users_management(request):
    users = User.objects.all().order_by('-id')
    return render(request, 'users_management.html', {
        'users': users
    })

@superuser_required
def add_user(request):
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "").strip()
        is_superuser = bool(request.POST.get("is_superuser"))

        if not username or not password:
            messages.error(request, "Username and password are required.")
            return redirect("dashboard:users_management")

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
            return redirect("dashboard:users_management")

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password
        )
        user.is_staff = True

        if is_superuser:
            user.is_superuser = True

        user.save()

        messages.success(request, "User added successfully.")
        return redirect("dashboard:users_management")

    return redirect("dashboard:users_management")

@superuser_required
def delete_user(request, user_id):
    user = get_object_or_404(User, id=user_id)

    if user == request.user:
        messages.error(request, "You cannot delete yourself.")
        return redirect("dashboard:users_management")

    user.delete()
    messages.success(request, "User deleted successfully.")
    return redirect("dashboard:users_management")


@superuser_required
def edit_user(request, user_id):
    user = get_object_or_404(User, id=user_id)

    if request.method != "POST":
        return redirect("dashboard:users_management")

    username = request.POST.get("username", "").strip()
    email = request.POST.get("email", "").strip()
    password = request.POST.get("password", "").strip()
    is_superuser = bool(request.POST.get("is_superuser"))
    is_staff = bool(request.POST.get("is_staff"))

    if not username:
        messages.error(request, "Username is required.")
        return redirect("dashboard:users_management")

    if User.objects.exclude(id=user.id).filter(username=username).exists():
        messages.error(request, "Username already exists.")
        return redirect("dashboard:users_management")

    if user == request.user:
        is_superuser = True
        is_staff = True

    user.username = username
    user.email = email
    user.is_superuser = is_superuser
    user.is_staff = is_staff

    if password:
        user.set_password(password)

    user.save()

    if user == request.user and password:
        update_session_auth_hash(request, user)

    messages.success(request, "User updated successfully.")
    return redirect("dashboard:users_management")


@superuser_required
def telegram_backup_settings_view(request):
    settings_obj, _ = TelegramBackupSettings.objects.get_or_create(id=1)

    if request.method == "POST":
        settings_obj.bot_token = request.POST.get("bot_token", "").strip()
        settings_obj.chat_id = request.POST.get("chat_id", "").strip()
        settings_obj.is_enabled = bool(request.POST.get("is_enabled"))
        settings_obj.backup_database = bool(request.POST.get("backup_database"))
        settings_obj.backup_media = bool(request.POST.get("backup_media"))

        interval = request.POST.get("interval_days", "1").strip()
        try:
            settings_obj.interval_days = max(1, int(interval))
        except ValueError:
            settings_obj.interval_days = 1

        settings_obj.save()
        messages.success(request, "✅ Settings saved successfully.")
        return redirect("dashboard:telegram_backup_settings")

    return render(request, "backup.html", {
        "settings_obj": settings_obj
    })

@superuser_required
def telegram_test_backup(request):
    settings_obj = TelegramBackupSettings.objects.first()

    if not settings_obj or not settings_obj.bot_token or not settings_obj.chat_id:
        messages.error(request, "Telegram settings not configured")
        return redirect("dashboard:telegram_backup_settings")

    url = f"https://api.telegram.org/bot{settings_obj.bot_token}/sendMessage"

    try:
        res = requests.post(url, data={
            "chat_id": settings_obj.chat_id,
            "text": "✅ Test backup message from antibot"
        }, timeout=20)

        data = res.json()

        if res.ok and data.get("ok"):
            messages.success(request, "✅ Test message sent successfully")
        else:
            messages.error(request, f"❌ Telegram error: {data}")

    except Exception as e:
        messages.error(request, f"❌ Request failed: {str(e)}")

    return redirect("dashboard:telegram_backup_settings")
@superuser_required
def telegram_send_db_backup(request):
    settings_obj = TelegramBackupSettings.objects.first()

    if not settings_obj or not settings_obj.bot_token or not settings_obj.chat_id:
        messages.error(request, "Telegram settings not configured")
        return redirect("dashboard:telegram_backup_settings")

    backup_path = None

    try:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            backup_path = tmp.name

        call_command("dumpdata", output=backup_path, indent=2)

        url = f"https://api.telegram.org/bot{settings_obj.bot_token}/sendDocument"

        with open(backup_path, "rb") as f:
            res = requests.post(
                url,
                data={
                    "chat_id": settings_obj.chat_id,
                    "caption": "✅ Antibot database backup"
                },
                files={"document": f},
                timeout=60
            )

        data = res.json()

        if res.ok and data.get("ok"):
            messages.success(request, "✅ Backup sent successfully")
        else:
            messages.error(request, f"❌ Telegram error: {data}")

    except Exception as e:
        messages.error(request, f"❌ Backup failed: {str(e)}")

    finally:
        if backup_path and os.path.exists(backup_path):
            os.remove(backup_path)

    return redirect("dashboard:telegram_backup_settings")

@login_required
def profile_settings_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        action = request.POST.get("action")

        # تحديث البروفايل
        if action == "profile":
            username = request.POST.get("username", "").strip()
            email = request.POST.get("email", "").strip()
            avatar = request.FILES.get("avatar")

            if not username:
                messages.error(request, "Username is required.")
                return redirect("dashboard:profile_settings")

            if User.objects.exclude(id=request.user.id).filter(username=username).exists():
                messages.error(request, "Username already exists.")
                return redirect("dashboard:profile_settings")

            request.user.username = username
            request.user.email = email
            request.user.save()

            if avatar:
                profile.avatar = avatar
                profile.save()

            messages.success(request, "Profile updated successfully.")
            return redirect("dashboard:profile_settings")

        # تغيير الباسورد
        if action == "password":
            old_password = request.POST.get("old_password", "").strip()
            new_password = request.POST.get("new_password", "").strip()
            confirm_password = request.POST.get("confirm_password", "").strip()

            if not request.user.check_password(old_password):
                messages.error(request, "Old password is incorrect.")
                return redirect("dashboard:profile_settings")

            if new_password != confirm_password:
                messages.error(request, "Passwords do not match.")
                return redirect("dashboard:profile_settings")

            request.user.set_password(new_password)
            request.user.save()
            update_session_auth_hash(request, request.user)

            messages.success(request, "Password changed successfully.")
            return redirect("dashboard:profile_settings")

    return render(request, "profile_settings.html", {
        "profile": profile
    })