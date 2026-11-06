# syntax=docker/dockerfile:1

FROM python:3.12-slim-bookworm

# local.txt for development (adds pytest, ruff); production.txt for deployments.
ARG REQUIREMENTS_FILE=production.txt
# Match the host user's UID/GID in development so files created inside the
# container (e.g. new migrations) are owned by you on the host.
ARG APP_UID=1000
ARG APP_GID=1000

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --gid "${APP_GID}" app \
    && useradd --uid "${APP_UID}" --gid app --create-home --shell /bin/bash app

COPY requirements/ /tmp/requirements/
RUN pip install -r "/tmp/requirements/${REQUIREMENTS_FILE}" && rm -rf /tmp/requirements

COPY --chown=app:app . .

USER app

EXPOSE 8000

# Production default. docker-compose overrides this with runserver for local dev.
# collectstatic must run at build/release time in deployments (see README).
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
