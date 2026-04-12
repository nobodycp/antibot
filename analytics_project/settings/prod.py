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

# --- HTTPS behind a trusted reverse proxy (Nginx, Caddy, etc.) ---
# Never set USE_X_FORWARDED_PROTO if clients can reach Gunicorn directly (spoofed header).
_use_xfp = os.environ.get("USE_X_FORWARDED_PROTO", "").strip().lower()
if _use_xfp in ("1", "true", "yes", "on"):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

_csrf_origins = os.environ.get("CSRF_TRUSTED_ORIGINS", "").strip()
if _csrf_origins:
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_origins.split(",") if o.strip()]

_secure_cookies = os.environ.get("DJANGO_SECURE_COOKIES", "").strip().lower()
if _secure_cookies in ("1", "true", "yes", "on"):
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
