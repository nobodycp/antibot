from django.contrib.auth.decorators import login_required, user_passes_test


def superuser_required(view_func):
    return login_required(user_passes_test(lambda u: u.is_superuser)(view_func))


def staff_member_required(view_func):
    """Active staff (is_staff); superusers are staff by default."""
    return login_required(user_passes_test(lambda u: u.is_active and u.is_staff)(view_func))
