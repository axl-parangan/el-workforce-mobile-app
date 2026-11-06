"""Settings used by pytest. Selected through pytest.ini."""

from .base import *  # noqa: F403

DEBUG = False

SECRET_KEY = "django-insecure-test-only-key-long-enough-for-hs256-signing"

ALLOWED_HOSTS = ["testserver", "localhost"]

# Fast hashing keeps auth-heavy tests quick. Never use outside tests.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
