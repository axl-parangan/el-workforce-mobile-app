"""Settings shared by every environment.

Environment-specific modules import from here and override what they need.
Secrets and deployment-specific values are read from environment variables;
nothing sensitive is hard-coded in this file.
"""

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = BASE_DIR.parent

env = environ.Env()

# When running outside Docker, fall back to the repository-level .env file.
# Variables already present in the process environment always take precedence.
_env_file = REPO_ROOT / ".env"
if _env_file.is_file():
    env.read_env(str(_env_file), overwrite=False)

# SECRET_KEY, DEBUG and ALLOWED_HOSTS are defined per environment.

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------

DJANGO_APPS = [
    # Django admin, restricted to superusers.
    "config.admin_site.SuperuserAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
]

LOCAL_APPS = [
    "apps.accounts",
    "apps.company",
    "apps.clients",
    "apps.workforce",
    "apps.jobs",
    "apps.timekeeping",
    "apps.payroll",
    "apps.team_notes",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

ADMIN_URL = env("DJANGO_ADMIN_URL", default="admin/")

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST", default="localhost"),
        "PORT": env.int("POSTGRES_PORT", default=5432),
        "CONN_MAX_AGE": env.int("DJANGO_DB_CONN_MAX_AGE", default=60),
        "CONN_HEALTH_CHECKS": True,
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"
USE_I18N = True
# Timestamps are always stored in UTC (timestamptz).
USE_TZ = True

# The company timezone is the authority for work dates in attendance and
# payroll, never the device's timezone (ADR 008). Use common.timezones helpers
# rather than reading this directly.
COMPANY_TIME_ZONE = env("COMPANY_TIME_ZONE", default="America/Toronto")
# Django's display/admin timezone follows the company timezone.
TIME_ZONE = COMPANY_TIME_ZONE

# ---------------------------------------------------------------------------
# Location validation (ADR 004). Initial operational thresholds.
# ---------------------------------------------------------------------------

# The default job geofence radius (100 m) is a per-job field default, see
# apps/timekeeping/services/location_validation.py. A company-wide default may
# be introduced later.
# Fixes with a worse (larger) accuracy radius than this are flagged for review.
LOCATION_MAX_ACCURACY_METERS = Decimal(env("LOCATION_MAX_ACCURACY_METERS", default="30"))

# ---------------------------------------------------------------------------
# Attendance processing
# ---------------------------------------------------------------------------

# A punch whose device time is further ahead of the server's received time
# than this is accepted but flagged ``future_timestamp`` for review.
ATTENDANCE_FUTURE_TOLERANCE_SECONDS = env.int("ATTENDANCE_FUTURE_TOLERANCE_SECONDS", default=300)
# Admin/Manager entries for other employees must be this fresh. Backdated
# attendance is left to the future correction workflow.
ATTENDANCE_ADMIN_ENTRY_MAX_AGE_SECONDS = env.int(
    "ATTENDANCE_ADMIN_ENTRY_MAX_AGE_SECONDS", default=900
)
# Upper bounds for one request.
ATTENDANCE_MAX_GROUP_SIZE = 100
ATTENDANCE_MAX_SYNC_EVENTS = 100

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    # Secure by default: endpoints must opt out explicitly with AllowAny.
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "DEFAULT_PARSER_CLASSES": ("rest_framework.parsers.JSONParser",),
    "DEFAULT_PAGINATION_CLASS": "common.pagination.StandardPagination",
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.NamespaceVersioning",
    "DEFAULT_VERSION": "v1",
    "ALLOWED_VERSIONS": ("v1",),
    "EXCEPTION_HANDLER": "common.exceptions.api_exception_handler",
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
    # Decimals (money, hours, coordinates) are serialised as strings so that
    # clients never round-trip them through binary floating point.
    "COERCE_DECIMAL_TO_STRING": True,
}

# ---------------------------------------------------------------------------
# JWT (djangorestframework-simplejwt)
# ---------------------------------------------------------------------------
# The refresh-token lifetime must exceed the longest realistic period a device
# stays offline, otherwise queued punches cannot be synced without a re-login.
# Queued punches are never discarded because of an expired session.
# See docs/decisions/002-offline-first-timekeeping.md.

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=env.int("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", default=15)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=env.int("JWT_REFRESH_TOKEN_LIFETIME_DAYS", default=30)
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
# Native mobile clients are not subject to CORS. These origins only matter
# for browser clients such as Expo web or a future admin web app.

CORS_ALLOWED_ORIGINS = env.list("DJANGO_CORS_ALLOWED_ORIGINS", default=[])

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
# "console" is human-readable for development. "json" emits one JSON object
# per line for log aggregation in deployed environments.

LOG_LEVEL = env("DJANGO_LOG_LEVEL", default="INFO")
LOG_FORMAT = env("DJANGO_LOG_FORMAT", default="console")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "console": {
            "format": "{asctime} {levelname:<8} {name}: {message}",
            "style": "{",
        },
        "json": {"()": "common.logging.JsonFormatter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": LOG_FORMAT,
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "django.db.backends": {"level": "WARNING"},
    },
}
