"""Development settings (default when DJANGO_ENV is not production)."""
from .base import *

DEBUG = True

# Local dev only: not used when DJANGO_ENV=production (see prod.py).
if not str(SECRET_KEY or "").strip():
    SECRET_KEY = "django-insecure-dev-only-not-for-production"

ALLOWED_HOSTS = ["*"]
# ALLOWED_HOSTS = ['216.126.229.66', 'localhost', '127.0.0.1']
