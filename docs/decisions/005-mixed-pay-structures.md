# ADR 005: Pay structures and payroll arithmetic

- Status: Accepted. The **MVP is hourly only**, following the ERD.
  Daily and fixed/task pay and rate history are deferred.
- Date: 2026-11-06 (revised: ERD adopted as designed)

## Context

The business eventually needs hourly, daily and fixed/task pay, with
employee-specific rates that don't depend on the job. Payroll errors are
costly and must be explainable. The ERD of 2026-11-06 deliberately starts
with hourly pay only. That was confirmed when choosing between the ERD and a
rate-history table.

## Decision

### Rates (MVP)

- **`Employee.hourly_rate`** is the employee's current rate. Editing it
  overwrites the current value.
- **Approved payroll is protected by snapshots.** Each `PayrollLine` stores
  `hours_paid` and `hourly_rate_applied`. A later rate change never alters a
  calculated or approved line.
- Rates do not depend on the job.

### Arithmetic and rounding

- Use `decimal.Decimal` in Python and `DecimalField` in PostgreSQL. Never use
  floats.
- Calculate at full precision, then round the **final payable amount** to
  **2 decimal places** with **`ROUND_HALF_UP`**
  (`apps/payroll/services/money.py: round_money`).
- `gross_pay = round_money(hours_paid × hourly_rate_applied)`
  (`calculate_hourly_pay`).
- `final_amount = gross_pay + adjustment_amount`. The database enforces this.
- Calculations are plain functions, isolated from views and database access.

### Payroll structure

- A `PayrollRun` covers a period, with status draft, approved, paid or
  cancelled.
- It has one `PayrollLine` per work session, and a session can be paid only
  once.
- Approved runs are never recalculated in place. Corrections go through
  `adjustment_amount`.

## Deferred (requires schema additions when needed)

- **Rate history** (effective-dated) and **compensation types** (daily,
  fixed/task). The likely shape is an `EmployeePayRate` table, plus a
  compensation type on payroll lines.
- **Fixed/task pay.** It is based on approved tasks or deliverables, not
  attendance. It needs task tables, and the open question in
  `docs/development/open-questions.md`.
- **Business rules:**
  - daily qualifying day
  - overtime
  - breaks
  - shifts that cross midnight
  - time rounding
