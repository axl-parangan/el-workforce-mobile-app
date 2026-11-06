"""Production settings. Every security-relevant value must come from the environment."""

from .base import *  # noqa: F403
from .base import LOGGING, MIDDLEWARE, env

DEBUG = False

SECRET_KEY = env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# ---------------------------------------------------------------------------
# HTTPS / security headers
# ---------------------------------------------------------------------------
# Assumes TLS terminates at a reverse proxy or load balancer that sets
# X-Forwarded-Proto.

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
# Load balancer health checks often probe over plain HTTP.
SECURE_REDIRECT_EXEMPT = [r"^api/v1/health/$"]

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Start conservatively; raise to 31536000 once HTTPS is confirmed stable.
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=3600)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False)
SECURE_HSTS_PRELOAD = env.bool("DJANGO_SECURE_HSTS_PRELOAD", default=False)

# ---------------------------------------------------------------------------
# Static files (served by WhiteNoise, mainly for the Django admin)
# ---------------------------------------------------------------------------

_security_index = MIDDLEWARE.index("django.middleware.security.SecurityMiddleware")
MIDDLEWARE = [
    *MIDDLEWARE[: _security_index + 1],
    "whitenoise.middleware.WhiteNoiseMiddleware",
    *MIDDLEWARE[_security_index + 1 :],
]

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# ---------------------------------------------------------------------------
# Logging: structured JSON by default
# ---------------------------------------------------------------------------

LOGGING["handlers"]["console"]["formatter"] = env("DJANGO_LOG_FORMAT", default="json")
