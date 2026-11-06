"""Staging settings: production hardening with a few relaxed defaults."""

from .production import *  # noqa: F403
from .production import env

# Keep HSTS short-lived on staging so certificate or domain changes are cheap.
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=60)
