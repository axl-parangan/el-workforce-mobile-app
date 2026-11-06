# ADR 008: Company timezone defines work dates

- Status: Accepted
- Date: 2026-11-06

## Context

Daily pay, attendance reports and pay periods depend on which calendar date
a punch belongs to. A late-evening shift in Toronto already falls on the next
day in UTC. Phones can be set to any timezone, or simply be wrong.

## Decision

- **Storage:** all event timestamps are timezone-aware and stored in
  PostgreSQL as `timestamptz`, normalised to UTC (`USE_TZ = True`).
- **Audit:** the timestamp captured on the device is kept on each event, but
  it is never the authority for payroll dates.
- **Work date:** the calendar date of an event is determined in the
  **company timezone**. It is configured by `COMPANY_TIME_ZONE` and defaults
  to `America/Toronto`.
- Use `common/timezones.py` for this conversion:
  - `company_timezone()`
  - `to_company_time(instant)`
  - `work_date_for(instant)`

  These helpers reject naive datetimes.
- Django's `TIME_ZONE`, which controls admin display, follows the company
  timezone.
- A **per-job timezone override** may be added later. The MVP doesn't need
  it. When added, `work_date_for` gains an optional zone argument, so callers
  don't change.

## Consequences

- Daylight-saving transitions are handled by the IANA timezone database
  (`zoneinfo`).
- A shift that crosses midnight in the company timezone spans two work dates.
  How such a shift is attributed for daily pay is a pending business rule.
- The timezone is a deployment setting for now. If the company ever needs to
  change it at runtime, it can move to a database-backed company settings
  model.
