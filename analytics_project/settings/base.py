"""
Shared Django settings for analytics_project (loaded by dev.py / prod.py).
"""
import importlib.util
import os
import warnings
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

# analytics_project/settings/base.py -> project root
BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / ".env")

# Set via DJANGO_SECRET_KEY or SECRET_KEY in the environment (see dev.py / prod.py).
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or os.environ.get("SECRET_KEY") or ""

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'dashboard',
    'tracker.apps.TrackerConfig',
    'core',
    'tools',
    'django.contrib.humanize',
]

# WhiteNoise is listed in requirements.txt; if the venv was not upgraded, skip it so WSGI still loads.
_WHITENOISE_SPEC = importlib.util.find_spec("whitenoise")
WHITENOISE_AVAILABLE = _WHITENOISE_SPEC is not None

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
]

if WHITENOISE_AVAILABLE:
    MIDDLEWARE.append('whitenoise.middleware.WhiteNoiseMiddleware')
else:
    warnings.warn(
        "Package 'whitenoise' is not installed — /static/ is served only via urls.py + "
        "STATIC_ROOT after collectstatic. Run: pip install -r requirements.txt",
        stacklevel=1,
    )

MIDDLEWARE += [
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'analytics_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'dashboard', 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.inject_now',
                # 'django.template.context_processors.tz',
            ],
        },
    },
]

WSGI_APPLICATION = 'analytics_project.wsgi.application'

def _postgres_config():
    """Build PostgreSQL settings from DATABASE_URL, POSTGRES_*, or legacy DB_* env vars."""
    database_url = (os.environ.get("DATABASE_URL") or "").strip()
    if database_url:
        parsed = urlparse(database_url)
        if parsed.scheme not in ("postgres", "postgresql"):
            raise ValueError(
                f"DATABASE_URL scheme must be postgres or postgresql, got {parsed.scheme!r}"
            )
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": unquote(parsed.path.lstrip("/")),
            "USER": unquote(parsed.username or ""),
            "PASSWORD": unquote(parsed.password or ""),
            "HOST": parsed.hostname or "127.0.0.1",
            "PORT": str(parsed.port or 5432),
            "CONN_MAX_AGE": int(os.environ.get("DB_CONN_MAX_AGE", "0")),
        }

    name = (
        os.environ.get("POSTGRES_DB")
        or os.environ.get("DB_NAME")
        or ""
    ).strip()
    if not name:
        return None

    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": name,
        "USER": (
            os.environ.get("POSTGRES_USER")
            or os.environ.get("DB_USER")
            or "postgres"
        ),
        "PASSWORD": (
            os.environ.get("POSTGRES_PASSWORD")
            or os.environ.get("DB_PASSWORD")
            or ""
        ),
        "HOST": (
            os.environ.get("POSTGRES_HOST")
            or os.environ.get("DB_HOST")
            or "127.0.0.1"
        ),
        "PORT": (
            os.environ.get("POSTGRES_PORT")
            or os.environ.get("DB_PORT")
            or "5432"
        ),
        "CONN_MAX_AGE": int(os.environ.get("DB_CONN_MAX_AGE", "0")),
    }


# Database: PostgreSQL when DATABASE_URL / POSTGRES_* / DB_* is set; else SQLite (local dev).
_pg = _postgres_config()
if _pg:
    DATABASES = {"default": _pg}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# Shared default cache: IP enrichment (visitor_context_service), API rate limits, etc.
# Requires Redis. Set REDIS_URL or use default redis://127.0.0.1:6379/1 (django-redis).
_redis_url = os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379/1')
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': _redis_url,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
    }
}

# TTL in seconds for cached external IP API enrichment (default 6 hours).
TRACKER_IP_CONTEXT_CACHE_TIMEOUT = int(
    os.environ.get('TRACKER_IP_CONTEXT_CACHE_TIMEOUT', '21600')
)

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "static")
]
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# When DEBUG is False, Django does not attach /media/ routes unless this is True.
# Set DJANGO_SERVE_MEDIA=1 in .env if you have no reverse-proxy block for /media/ yet.
# Prefer serving MEDIA_ROOT with Nginx (see README); use this only for small/simple deploys.
SERVE_MEDIA = os.environ.get("DJANGO_SERVE_MEDIA", "").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# WhatsApp number validator (Node / Baileys under project whatsapp/)
WHATSAPP_ROOT = BASE_DIR / "whatsapp"
WHATSAPP_NODE_BIN = os.environ.get("NODE_BIN", "node")
WHATSAPP_DEFAULT_SPEED = os.environ.get("WHATSAPP_SPEED", "normal")
WHATSAPP_LOCAL_TRUNK_COUNTRY = os.environ.get("LOCAL_TRUNK_COUNTRY", "").strip()

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/accounts/login/'
