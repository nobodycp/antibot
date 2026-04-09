from django.contrib.auth.decorators import login_required
from .models import TelegramBackupSettings
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
import requests
import tempfile
from django.core.management import call_command
import os
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import TelegramBackupSettings, UserProfile


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    UserProfile.objects.get_or_create(user=instance)
    instance.profile.save()


def superuser_required(view_func):
    return login_required(user_passes_test(lambda u: u.is_superuser)(view_func))


@login_required
def dashboard_home(request):
    return render(request, 'home.html')
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

@login_required
def change_password_view(request):
    if request.method == "POST":
        old_password = request.POST.get("old_password", "").strip()
        new_password = request.POST.get("new_password", "").strip()
        confirm_password = request.POST.get("confirm_password", "").strip()

        if not old_password or not new_password or not confirm_password:
            messages.error(request, "All password fields are required.")
            return redirect("dashboard:change_password")

        if not request.user.check_password(old_password):
            messages.error(request, "Old password is incorrect.")
            return redirect("dashboard:change_password")

        if new_password != confirm_password:
            messages.error(request, "New password and confirm password do not match.")
            return redirect("dashboard:change_password")

        if len(new_password) < 8:
            messages.error(request, "New password must be at least 8 characters.")
            return redirect("dashboard:change_password")

        request.user.set_password(new_password)
        request.user.save()
        update_session_auth_hash(request, request.user)

        messages.success(request, "Password changed successfully.")
        return redirect("dashboard:change_password")

    return render(request, "change_password.html")


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

    return render(request, "profile_settings.html", {
        "profile": profile
    })