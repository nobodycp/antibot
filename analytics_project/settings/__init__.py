"""
Django settings package.

Loads .env before choosing dev vs prod so DJANGO_ENV, DB_*, etc. are available.
Uses development settings by default. Set DJANGO_ENV=production for prod.py.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

if os.environ.get("DJANGO_ENV", "").lower() in ("production", "prod"):
    from .prod import *
else:
    from .dev import *
