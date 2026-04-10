from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.shortcuts import get_object_or_404, redirect, render

from core.decorators import superuser_required

from ..forms import AddUserForm, EditUserForm
from ..models import UserProfile


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    UserProfile.objects.get_or_create(user=instance)
    instance.profile.save()


@superuser_required
def users_management(request):
    users = User.objects.all().order_by('-id')
    return render(request, 'dashboard/users_management.html', {
        'users': users
    })


@superuser_required
def add_user(request):
    if request.method == "POST":
        form = AddUserForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Username and password are required.")
            return redirect("dashboard:users_management")

        username = form.cleaned_data["username"]
        email = form.cleaned_data["email"]
        password = form.cleaned_data["password"]
        is_superuser = form.cleaned_data["is_superuser"]

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

    form = EditUserForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Username is required.")
        return redirect("dashboard:users_management")

    username = form.cleaned_data["username"]
    email = form.cleaned_data["email"]
    password = form.cleaned_data["password"]
    is_superuser = form.cleaned_data["is_superuser"]
    is_staff = form.cleaned_data["is_staff"]

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
