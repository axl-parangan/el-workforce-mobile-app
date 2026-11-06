"""Settings are split per environment.

Select one with DJANGO_SETTINGS_MODULE:

- config.settings.local       local development (default for manage.py)
- config.settings.test        pytest (selected via pytest.ini)
- config.settings.staging     staging deployments
- config.settings.production  production deployments (default for wsgi/asgi)
"""
