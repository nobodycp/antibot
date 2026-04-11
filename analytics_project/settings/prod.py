"""Production-oriented settings. Enable with DJANGO_ENV=production.

Static: WhiteNoise serves ``/static/``. By default ``WHITENOISE_USE_FINDERS`` is **on**
so CSS/JS load even if ``collectstatic`` was skipped or failed (files come from each
app's ``static/`` tree). After ``collectstatic`` works reliably, set in ``.env``:
``DJANGO_WHITENOISE_FINDERS=0`` for slightly leaner serving from ``STATIC_ROOT`` only.
"""
import os

from django.core.exceptions import ImproperlyConfigured

from .base import *

DEBUG = False

# Default True when WhiteNoise is installed: serve from app static/ if STATIC_ROOT is empty.
_wf = os.environ.get("DJANGO_WHITENOISE_FINDERS", "1").strip().lower()
if WHITENOISE_AVAILABLE:
    WHITENOISE_USE_FINDERS = _wf not in ("0", "false", "no", "off")

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
