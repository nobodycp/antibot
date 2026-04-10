"""
Django settings package.

Uses development settings by default. Set DJANGO_ENV=production for prod.py
(e.g. export DJANGO_ENV=production).
"""
import os

if os.environ.get("DJANGO_ENV", "").lower() in ("production", "prod"):
    from .prod import *
else:
    from .dev import *
