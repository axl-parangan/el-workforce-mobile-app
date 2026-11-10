# Backend conventions

See [ADR 001](../decisions/001-modular-monolith.md) for the reasoning.

## Layout of a domain app

```text
apps/timekeeping/
├── apps.py
├── admin.py
├── models/__init__.py     # import model classes here so Django discovers them
├── migrations/
├── services/              # e.g. punches.py: record_punch(*, worker, job, ...)
├── selectors/             # e.g. sessions.py: sessions_for_worker(*, worker, ...)
├── api/
│   ├── serializers.py
│   ├── views.py
│   └── urls.py            # mounted under /api/v1/<domain>/
└── tests/
```

Create `serializers.py` and `views.py` when the first endpoint is added.
Don't create empty files in advance.

## Services

- Use plain functions with keyword-only arguments:
  `def record_attendance_batch(*, actor: User, job: Job, ...) -> AttendanceBatch`.
- Wrap multi-step writes in `transaction.atomic()`.
- Raise `ApplicationError` (or a subclass with a specific `status_code` and
  `default_code`) for rule violations. The API renders it in the standard
  error envelope automatically.
- Never accept a `request` object. Pass the acting user explicitly.

## Views

```python
class ClockInView(APIView):
    class InputSerializer(serializers.Serializer):
        ...

    def post(self, request):
        data = self.InputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        event = record_punch(actor=request.user, **data.validated_data)
        return Response(OutputSerializer(event).data, status=201)
```

## Money, time, coordinates

- Money, rates and hours use `DecimalField` and `Decimal`. Never use float.
- Coordinates use `DecimalField(max_digits=9, decimal_places=6)`.
- Datetimes are timezone-aware and stored in UTC (`USE_TZ = True`).
- Derive work dates with `common.timezones.work_date_for(instant)`, which
  uses the company timezone. Never use `instant.date()` or the device's
  offset (ADR 008).
- Round money only with `apps.payroll.services.money.round_money`
  (2 dp, `ROUND_HALF_UP`), and only on final amounts (ADR 005).
- Validate punch locations only with
  `apps.timekeeping.services.location_validation` (ADR 004).

## Tests

- Run `make test`, or `pytest` from `backend/` with a local virtualenv.
- Put tests for app code in `apps/<domain>/tests/`. Put cross-cutting tests
  (settings, error envelope, health) in `backend/tests/`.
- Service functions get the most test coverage. View tests check wiring,
  permissions and status codes.

## Authorization (ADR 011)

- **Never compare role names** outside `apps/accounts/authorization.py`.
  `tests/test_authorization_centralized.py` fails if you do.
- In views, use `common.permissions.requires(Capability.X, ...)`.
- In services, call `has_capability(user, Capability.X)`.
- For which records a user may touch, use `apps/jobs/selectors/scope.py`
  (`managed_jobs`, `crew_assignments`, `jobs_visible_to`,
  `attendance_jobs_for`, `can_record_attendance_for_others`). Return 404 for
  out-of-scope ids.
- Create or manage accounts only through
  `apps/accounts/services/accounts.py`. It decides which roles an actor may
  assign and never sets staff or superuser flags.
