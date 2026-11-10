# Construction Workforce

A mobile application for a construction company to manage workers, jobs,
attendance, timekeeping and payroll. It includes LeadHand group clock-in,
GPS-verified punches, and offline-first timekeeping.

> **Status:** foundation and data model. In place:
>
> - email-based authentication, the API, and offline infrastructure
> - the full domain schema: models, migrations and admin (see
>   [data model](docs/development/data-model.md))
> - location validation rules
> - the company-timezone work-date helper
> - money rounding and the hourly pay formula
> - **timekeeping (Phase 1):** individual and group clock-in/out, offline
>   sync with idempotency, location flags, history, and staff review (see
>   the [timekeeping API](docs/api/timekeeping.md))
> - **roles and authorization:** Admin, Manager, LeadHand and Employee roles,
>   with a central capability map, shared job and crew scope, guarded
>   account provisioning, and a superuser-only Django admin (see
>   [ADR 011](docs/decisions/011-roles-and-authorization.md))
> - **jobs and assignments:** jobs, LeadHand designation, bulk assignment and
>   the assignment lifecycle, integrated with timekeeping, including moving
>   between job sites (see the [jobs API](docs/api/jobs.md))
>
> Payroll and team notes endpoints are next. See the
> [open questions](docs/development/open-questions.md).

## Technology stack

| Area    | Stack |
| ------- | ----- |
| Backend | Python 3.12, Django 5.2 LTS, Django REST Framework, SimpleJWT, PostgreSQL 17, pytest |
| Mobile  | Expo SDK 58, React Native 0.88, TypeScript (strict), Expo Router, TanStack Query, Zod |
| Device  | expo-sqlite (offline store), expo-location (GPS), expo-network (connectivity), expo-secure-store (tokens), expo-crypto (UUIDs) |
| Tooling | Docker Compose, Ruff, ESLint and Prettier, pre-commit, GitHub Actions |

## Repository structure

```text
.
├── backend/                  Django modular monolith
│   ├── config/               settings (base/local/test/staging/production), urls, wsgi/asgi
│   ├── apps/                 one Django app per domain
│   │   ├── accounts/         User (email login, role), JWT auth endpoints
│   │   ├── company/          CompanySettings (single row, Admin-editable)
│   │   ├── clients/          Client (standalone, view-only)
│   │   ├── workforce/        Employee
│   │   ├── jobs/             Job, JobAssignment
│   │   ├── timekeeping/      AttendanceBatch/Item, WorkSession, TimePunch, location validation
│   │   ├── payroll/          PayrollRun, PayrollLine, money/hourly calculations
│   │   └── team_notes/       JobNote
│   ├── common/               error envelope, pagination, role permissions, JSON logging, health
│   ├── requirements/         base / local / production
│   └── tests/                cross-cutting tests
├── mobile/                   Expo app
│   ├── app/                  Expo Router routes only: (auth), (worker), (leadhand)
│   └── src/
│       ├── api/              HTTP client, errors, token storage, query client
│       ├── features/         feature modules (auth, dashboard, jobs, timekeeping, …)
│       ├── offline/          SQLite init, migrations, outbox queue, repositories, sync
│       ├── components/ hooks/ lib/ constants/ types/
├── docs/
│   ├── api/                  API conventions and endpoint list
│   ├── decisions/            architecture decision records (ADRs)
│   └── development/          conventions, auth, open questions
├── scripts/
├── .github/workflows/ci.yml
├── docker-compose.yml
└── Makefile
```

## Prerequisites

- Docker with Docker Compose v2
- GNU Make
- Node.js 22 LTS (`^22.13`) or 24, with npm, for the mobile app
- For running the app: the Expo Go app, an Android emulator or iOS
  simulator, or a [development build](https://docs.expo.dev/develop/development-builds/introduction/)
- Optional: Python 3.12, to run backend tooling outside Docker
- Optional: `pipx install pre-commit`

## Initial setup

```bash
make env            # creates .env from .env.example
# edit .env: set DJANGO_SECRET_KEY and POSTGRES_PASSWORD
make build
make up
make migrate
make createsuperuser   # prompts for email + password
```

To generate a secret key:
`python3 -c "import secrets; print(secrets.token_urlsafe(50))"`

Mobile:

```bash
cd mobile
cp .env.example .env.local   # set EXPO_PUBLIC_API_URL (see below)
npm ci
```

Git hooks (optional): `pre-commit install`

## Environment configuration

| File                | Used by                       | Notes |
| ------------------- | ----------------------------- | ----- |
| `.env`              | Docker Compose and Django     | From `.env.example`. Never commit it. |
| `mobile/.env.local` | Expo (`EXPO_PUBLIC_*` only)   | Inlined into the JS bundle, so never put secrets here. |

`EXPO_PUBLIC_API_URL` must include `/api/v1`:

- iOS simulator or web: `http://localhost:8000/api/v1`
- Android emulator: `http://10.0.2.2:8000/api/v1`
- Physical device: `http://<your-LAN-IP>:8000/api/v1`. The phone must be on
  the same network.

Business configuration, set in `.env`:

| Variable | Default | Meaning |
| --- | --- | --- |
| `COMPANY_TIME_ZONE` | `America/Toronto` | Defines work dates for attendance and payroll |
| `LOCATION_MAX_ACCURACY_METERS` | `30` | GPS fixes worse than this are flagged for review |

Django settings are selected with `DJANGO_SETTINGS_MODULE`:

| Module                         | Used for |
| ------------------------------ | -------- |
| `config.settings.local`        | Default for `manage.py` |
| `config.settings.test`         | pytest |
| `config.settings.staging`      | Staging deployments |
| `config.settings.production`   | Production; default for wsgi and asgi |

Production requires `DJANGO_SECRET_KEY` and `DJANGO_ALLOWED_HOSTS`.

## Starting the backend

```bash
make up        # db + backend on http://localhost:8000
make logs
curl http://localhost:8000/api/v1/health/   # {"status":"ok","database":"ok"}
```

- The Django admin is at <http://localhost:8000/admin/>. It is
  **superuser-only** (create one with `make createsuperuser`). Admins and
  Managers use the mobile app.
- `make down` stops the containers. The database volume is kept.

## Starting the mobile app

```bash
cd mobile
npx expo start          # or: make mobile-start
```

Then press `a` (Android), `i` (iOS), or scan the QR code with Expo Go.

All native modules used are included in Expo Go. Once custom native code or
config plugins outside Expo Go are added, use a development build:
`npx expo run:android` or `eas build --profile development`.

## Migrations

```bash
make makemigrations
make migrate
make check            # system checks + fails if migrations are missing
```

Local SQLite migrations for the mobile app live in
`mobile/src/offline/migrations/` and run automatically at app start.

## Tests and quality checks

```bash
make test                     # pytest against PostgreSQL in Docker
make test ARGS="-k health"
make lint                     # ruff check + ruff format --check
make format
make mobile-check             # tsc --noEmit, expo lint, prettier --check
make mobile-test              # Jest: unit, screen and SQLite outbox tests
```

Mobile tests that talk to a running backend are skipped unless
`LIVE_API_URL` is set, e.g. `LIVE_API_URL=http://localhost:8000/api/v1 npx
jest live` from `mobile/`. They use the demo accounts listed in
`docs/development/mobile-qa-checklist.md`.

CI (`.github/workflows/ci.yml`) runs the same checks on every push and pull
request.

## Deployment notes

No deployment target has been chosen yet. The backend image is
production-ready:

- Build with the default `REQUIREMENTS_FILE=production.txt`. It runs
  gunicorn on port 8000 as a non-root user.
- At release time, run `python manage.py migrate` and
  `python manage.py collectstatic --noinput`. WhiteNoise serves the admin's
  static files.
- Set `DJANGO_SETTINGS_MODULE=config.settings.production` (or `staging`),
  `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` and the `POSTGRES_*`
  variables. TLS is expected to terminate at a proxy that sends
  `X-Forwarded-Proto`.

## Further reading

- [ADR 001: Modular monolith](docs/decisions/001-modular-monolith.md)
- [ADR 002: Offline-first timekeeping](docs/decisions/002-offline-first-timekeeping.md)
- [ADR 003: Punch events and work sessions](docs/decisions/003-punch-events-and-work-sessions.md)
- [ADR 004: Location validation](docs/decisions/004-location-validation.md)
- [ADR 005: Mixed pay structures](docs/decisions/005-mixed-pay-structures.md)
- [ADR 006: LeadHand group clock](docs/decisions/006-leadhand-group-clock.md)
- [ADR 007: Employees, user accounts, and email login](docs/decisions/007-employee-and-user-identity.md)
- [ADR 008: Company timezone defines work dates](docs/decisions/008-company-timezone-and-work-dates.md)
- [ADR 009: Job-based team notes](docs/decisions/009-job-team-notes.md)
- [Backend conventions](docs/development/backend-conventions.md)
- [Authentication and roles](docs/development/authentication.md)
- [API conventions](docs/api/README.md)
- [Open questions (triaged)](docs/development/open-questions.md)
- [Data model](docs/development/data-model.md)
- [ADR 010: Clients](docs/decisions/010-clients.md)
- [ADR 011: Roles and centralised authorization](docs/decisions/011-roles-and-authorization.md)
