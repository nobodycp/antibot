import secrets

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from ..forms import ProfilePasswordForm, ProfileUpdateForm
from ..models import UserAPIKey, UserProfile


@login_required
def profile_settings_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    user_api_key, _ = UserAPIKey.objects.get_or_create(
        user=request.user,
        defaults={"api_key": secrets.token_urlsafe(32)},
    )

    if request.method == "POST":
        action = request.POST.get("action")

        # تحديث البروفايل
        if action == "profile":
            form = ProfileUpdateForm(request.POST, request.FILES)
            if not form.is_valid():
                messages.error(request, "Username is required.")
                return redirect("dashboard:profile_settings")

            username = form.cleaned_data["username"]
            email = form.cleaned_data["email"]
            avatar = form.cleaned_data.get("avatar")

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
            form = ProfilePasswordForm(request.POST)
            if form.is_valid():
                old_password = form.cleaned_data["old_password"]
                new_password = form.cleaned_data["new_password"]
                confirm_password = form.cleaned_data["confirm_password"]
            else:
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

    return render(request, "dashboard/profile_settings.html", {
        "profile": profile,
        "user_api_key": user_api_key,
    })


@login_required
@require_POST
def regenerate_api_key_view(request):
    """Rotate the logged-in user's tracker API key only (POST)."""
    row, created = UserAPIKey.objects.get_or_create(
        user=request.user,
        defaults={"api_key": secrets.token_urlsafe(32)},
    )
    if not created:
        row.regenerate()
    if created:
        messages.success(
            request,
            "Your tracker API key is ready. Copy it from the field below and use it as the X-API-Key header.",
        )
    else:
        messages.success(
            request,
            "Your tracker API key has been regenerated. Update any clients; the previous key no longer works.",
        )
    return redirect("dashboard:profile_settings")
