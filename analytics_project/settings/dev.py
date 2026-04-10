"""Development settings (default when DJANGO_ENV is not production)."""
from .base import *

DEBUG = True

ALLOWED_HOSTS = ["*"]
# ALLOWED_HOSTS = ['216.126.229.66', 'localhost', '127.0.0.1']
