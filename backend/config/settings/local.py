"""Local development settings."""

from .base import *  # noqa: F403
from .base import REST_FRAMEWORK, env

DEBUG = True

SECRET_KEY = env("DJANGO_SECRET_KEY", default="django-insecure-local-development-only")

# Physical devices reach the dev server over the LAN, so allow any host locally.
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["*"])

CORS_ALLOWED_ORIGINS = env.list(
    "DJANGO_CORS_ALLOWED_ORIGINS",
    default=["http://localhost:8081", "http://127.0.0.1:8081"],
)

# Browsable API + session login make manual exploration easier in development.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_AUTHENTICATION_CLASSES": (
        *REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"],
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_RENDERER_CLASSES": (
        *REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"],
        "rest_framework.renderers.BrowsableAPIRenderer",
    ),
}
