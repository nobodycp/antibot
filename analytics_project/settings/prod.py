"""Production-oriented settings. Enable with DJANGO_ENV=production."""
import os

from django.core.exceptions import ImproperlyConfigured

from .base import *

DEBUG = False

if not str(SECRET_KEY or "").strip():
    raise ImproperlyConfigured(
        "Set DJANGO_SECRET_KEY or SECRET_KEY in the environment for production "
        "(DJANGO_ENV=production)."
    )

_raw_hosts = os.environ.get("ALLOWED_HOSTS", "")
if _raw_hosts.strip():
    ALLOWED_HOSTS = [h.strip() for h in _raw_hosts.split(",") if h.strip()]
else:
    # Safe default: loopback only. Set ALLOWED_HOSTS to your real hostnames/IPs in production.
    ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
