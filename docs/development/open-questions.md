# Open questions

The schema is implemented as described in [data-model.md](data-model.md).
The remaining questions are triaged by their impact on it.

- **Category 1** needs your input, but only for future features. None of
  them blocks the implemented schema.
- **Category 2** can be added later as columns or tables, without
  restructuring existing data.
- **Category 3** is decided in services and selectors during implementation,
  with no schema change.

## Category 1: needs your input (future features)

| # | Question | Blocks |
| --- | --- | --- |
| Q1 | **Fixed/task pay.** What is a task? Who sets its amount (the employee's rate, or a price on the task)? Can several employees share one? Who approves it? | Task-pay tables |
| Q2 | **Daily pay and rate history.** When should compensation types and effective-dated rates replace the single `Employee.hourly_rate`? | Adding `EmployeePayRate` |
| Q3 | **Client access.** Can a job have one client or several? What may a client see: hours, costs, worker names? | `Job.client`, client users (ADR 010) |

## Category 2: additive schema changes, when needed

| Topic | How it would be added | Assumption until then |
| --- | --- | --- |
| Punch corrections | A correcting batch or punch that references the original, plus a reason | No corrections. Payroll uses `adjustment_amount`. |
| Breaks and lunches | New `PunchType` values and session or payroll fields | Not tracked |
| Overtime and holiday pay | Payroll line fields or a line type | Not calculated |
| Mock-location and clock-skew flags | New `LocationStatus` values; skew is already computable from `captured_at` and `received_at` | Not flagged |
| Offline notes | A `client_uuid` on `JobNote` | Notes are online-only |
| Company-wide default geofence radius, or runtime timezone | Columns on `CompanySettings` | 100 m per job; timezone from deployment settings |
| Finer note permissions | Boolean columns on `CompanySettings` | Workers allowed to create notes can edit and delete their own |
| Multiple roles per user | Replace `User.role` with a many-to-many relation | One role. LeadHand includes worker capabilities. |
| Currency | A `CompanySettings` column | Single currency, CAD |

## Category 3: implementation rules, no schema change

| Topic | Current assumption |
| --- | --- |
| Do Admins use the mobile app? | No. They get a placeholder screen. |
| Account provisioning (invite, password reset) | The Admin creates the user; password reset is to follow |
| Clocked in to two jobs at once | **Implemented:** not allowed (`already_clocked_in`) |
| LeadHand clocking out employees who clocked themselves in | **Implemented:** allowed on jobs they lead |
| LeadHand's own punches | **Implemented:** need an active assignment; none is created automatically |
| Who reviews flagged sessions, and does pending review block payroll? | **Implemented:** only Admins decide; LeadHands view their jobs. Payroll is to exclude pending sessions (not built yet). |
| Events queued under user A, synced after user B signs in on the same device | Not allowed. They wait for user A. |
| Shift crossing midnight | **Implemented:** counts toward the clock-in's work date |
| Rounding of worked hours | None. `hours_paid` is the exact duration, to 4 dp. |
| Pay period lock rules | Sessions in an approved run are not changed; corrections are adjustments |
| A job without a geofence | Punches are not sent to review for that reason alone |
| Notes after `workers_can_create_notes` is turned off | Workers keep editing and deleting their own existing notes |

## Raised by timekeeping Phase 1

| # | Question | Current behaviour |
| --- | --- | --- |
| T1 | **Stuck open sessions.** A session can stay open: the employee forgot to clock out, a clock-out was lost, or one was rejected (`clock_out_rejected`). That blocks the employee's next clock-in. Should Admins be able to enter or correct a clock-out, and should sessions auto-close after N hours? | Open until a valid clock-out arrives. Needs the correction design (Category 2). |
| T2 | **Can LeadHands make review decisions** for the jobs they lead? | Admins only |
| T3 | **Clock-ins on non-active jobs.** Should `planned` or `on_hold` jobs accept clock-ins? | Only `active` jobs accept clock-ins; clock-outs work for any status |
| T4 | **Very old offline events.** Should events captured, say, more than 7 days before sync be flagged? | Not flagged |
| T5 | **Admin manual entry** (`source = admin_entry`) | Not implemented |

## Resolved

| Topic | Decision | Recorded in |
| --- | --- | --- |
| Worker logins | Every worker has an Employee record; the User link is optional | ADR 007 |
| Login identifier | Email and password | ADR 007 |
| Job geofence | Optional circle. 100 m default, customisable per job. | ADR 004 |
| GPS thresholds and bad data | 30 m accuracy threshold. Bad GPS data flags the punch, never rejects it. Invalid coordinates are discarded. | ADR 004 |
| Rates | Hourly only, `Employee.hourly_rate`, with snapshots on payroll lines | ADR 005 |
| Rounding | Final amount rounded to 2 dp with `ROUND_HALF_UP` | ADR 005 |
| Work-day timezone | Company timezone, `America/Toronto` | ADR 008 |
| Team notes and worker note creation | Notes are per job. Worker note creation is controlled by the company setting `workers_can_create_notes` (default off). | ADR 009 |
| How a LeadHand is linked to a job | `Job.lead_hand`: one optional LeadHand per job | data-model.md |
| Clients | A separate, standalone table, view-only; future payroll report access | ADR 010 |
