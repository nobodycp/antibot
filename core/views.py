from django.conf import settings
from django.shortcuts import redirect


def root_redirect(request):
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)
    return redirect(settings.LOGIN_URL)
