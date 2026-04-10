"""Production-oriented settings. Enable with DJANGO_ENV=production."""
import os

from .base import *

DEBUG = False

_raw_hosts = os.environ.get("ALLOWED_HOSTS", "")
if _raw_hosts.strip():
    ALLOWED_HOSTS = [h.strip() for h in _raw_hosts.split(",") if h.strip()]
else:
    ALLOWED_HOSTS = ["216.126.229.66", "localhost", "127.0.0.1"]
