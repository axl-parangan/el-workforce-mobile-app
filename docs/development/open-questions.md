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
| **Lunch paid or unpaid (confirmed requirement)** | At clock-out the user says whether lunch was paid or unpaid. This needs a field, most likely on the clock-out batch or the session, plus payroll rules. | Not built; needs its own migration |
| Overtime and holiday pay | Payroll line fields or a line type | Not calculated |
| Mock-location and clock-skew flags | New `LocationStatus` values; skew is already computable from `captured_at` and `received_at` | Not flagged |
| **Offline notes (confirmed requirement)** | A `client_uuid` on `JobNote` (ADR 009 update) | Notes milestone |
| **Note categories (confirmed requirement)** | A `category` column on `JobNote` showing urgency | Notes milestone |
| Company-wide default geofence radius, or runtime timezone | Columns on `CompanySettings` | 100 m per job; timezone from deployment settings |
| Manager note permissions | Deferred (D21) | Everyone can create notes; authors cannot edit or delete them (ADR 009 update) |
| Runtime-editable permissions | Back `ROLE_CAPABILITIES` with Django Groups and Permissions | Fixed in code (D7) |
| Currency | A `CompanySettings` column | Single currency, CAD |

## Category 3: implementation rules, no schema change

| Topic | Current assumption |
| --- | --- |
| Do Admins and Managers use the mobile app? | **Resolved:** yes (D5). Placeholder sections exist. |
| Account provisioning | **Implemented (service only):** guarded `create_account` with an unusable password. Sending the password-set link waits for email delivery. |
| Clocked in to two jobs at once | **Implemented:** not allowed (`already_clocked_in`) |
| LeadHand clocking out employees who clocked themselves in, or were clocked in by others | **Implemented:** allowed on jobs they manage |
| LeadHand's own punches | **Implemented:** need an active assignment; none is created automatically |
| Who reviews sessions, and does pending review block payroll? | **Implemented:** Managers and Admins decide, never on their own timesheet. LeadHands view the jobs they manage. Payroll is to exclude pending sessions (not built yet). |
| Events queued under user A, synced after user B signs in on the same device | Not allowed. They wait for user A. |
| Shift crossing midnight | **Implemented:** counts toward the clock-in's work date |
| Rounding of worked hours | None. `hours_paid` is the exact duration, to 4 dp. |
| Pay period lock rules | Sessions in an approved run are not changed; corrections are adjustments |
| A job without a geofence | Punches are not sent to review for that reason alone |
| Automatic logout after 10 minutes of inactivity, only when not clocked in | **Confirmed requirement, deferred:** mobile only, no schema change |

## Raised by timekeeping Phase 1

| # | Question | Current behaviour |
| --- | --- | --- |
| T1 | **Stuck open sessions.** A session can stay open: the employee forgot to clock out, a clock-out was lost, or one was rejected (`clock_out_rejected`). That blocks the employee's next clock-in. Should Admins be able to enter or correct a clock-out, and should sessions auto-close after N hours? | Open until a valid clock-out arrives. Needs the correction design (Category 2). |
| T2 | ~~Can LeadHands make review decisions?~~ | **Resolved:** no. Managers and Admins review. |
| T3 | **Clock-ins on non-active jobs.** Should `planned` or `on_hold` jobs accept clock-ins? | Only `active` jobs accept clock-ins; clock-outs work for any status |
| T4 | **Very old offline events.** Should events captured, say, more than 7 days before sync be flagged? | Not flagged |
| T5 | ~~Admin manual entry~~ | **Implemented:** Admin and Manager entries for others are `admin_entry` and must be current (ADR 011) |

## Deferred by the role restructuring (2026-11-10)

All confirmed as future work; nothing implemented yet.

| Item | Notes |
| --- | --- |
| Attendance correction requests and correction audit | Employees request corrections from Managers and Admins (D20). LeadHands edit their crew's timesheets through the same workflow. **Recommended design:** append-only correction records that reference the original punch, store the requested and approved values, the requester, the approver and the reason, and recompute the session. Original batches and punches are never edited. Approval follows the same rule as reviews: never your own. |
| Backdated attendance | Only through the correction workflow. Administrative entries must currently be within 15 minutes of capture. |
| Job number generation | Format and timing undecided (D12) |
| Job-to-client relationship | Not added (D13) |
| Detailed GPS authorization | Locations are captured only at punch time; no background tracking (D14) |
| Payroll visibility, employee self-payroll setting, pay-rate restrictions | Deferred (D15). Pay is hourly only. |
| Report permissions | Deferred (D16) |
| Travel hours | A future client-specific billing and payroll feature (D17) |
| Invoicing | Deferred (D18) |
| Settings, permission-management and audit-log restrictions for Managers; a comprehensive audit log | Deferred (D19) |
| Runtime-editable permissions | Deferred (D7) |
| Manager team-note permissions | Deferred (D21) |
| Automatic mobile logout after 10 minutes of inactivity when not clocked in | Deferred |
| Role-change workflow | None. Roles are fixed at account creation (D9); only superusers can change them, in the Django admin. |

## Jobs and Assignments API decisions (approved 2026-11-10)

| # | Decision |
| --- | --- |
| Q1 | A LeadHand creating a job becomes its LeadHand and gets an active assignment |
| Q2 | Job numbers are entered by hand |
| Q3 | LeadHands edit only name, address, start date and end date on jobs they manage |
| Q4 | Designation auto-assigns; replacing keeps the previous LeadHand on the crew; ending the LeadHand's assignment clears the designation |
| Q5 | An assignment can end while the employee is clocked in; clock-out still works |
| Q6 | Offline punches captured before an assignment ended, and dated on or before its end date, are accepted |
| Q7 | Cancel only without work sessions; otherwise end |
| Q8 | Planned, active and on-hold jobs accept assignments; completing or cancelling a job doesn't end assignments |
| Q9 | Employees see only their own assignment |
| Q10 | Bulk assignment with per-employee results |
| Q11 | **Deferred:** `ended_by` and `end_reason` columns, and the audit log |
| Q12 | Capabilities `jobs.edit_any`, `jobs.edit_managed` and `assignments.view_crew` |
| Q13 | Offline events with equal device times: clock-outs before clock-ins, then submission order |
| Q14 | No cross-job LeadHand takeover of open sessions |
| Q15 | **Deferred:** database-level one-open-session-per-employee rule; the service rule plus the lock is used instead |

### Raised by the Jobs API (unresolved)

| # | Question | Current behaviour |
| --- | --- | --- |
| J1 | **Offline clock-in on a job whose status changed before sync.** Q6 covers ended assignments, not job status. A punch captured while the job was active, but synced after it was put on hold or completed, is rejected `job_not_active`. | Rejected. It stays visible in rejected events for staff. |
| J2 | **Superuser Django admin bypasses the services.** It can, for example, designate a LeadHand without an assignment. | Superuser-only; route it through the services if needed |

## Mobile Jobs & Assignments integration decisions (approved 2026-11-10)

| # | Decision |
| --- | --- |
| M1 | Real email and password sign-in form |
| M2 | Role-prefixed paths inside the four role groups (`/worker`, `/leadhand`, `/manager`, `/admin`); each group contains only the screens that role may use |
| M3 | `/auth/me/` returns `capabilities`; the app reads them to decide which actions to offer, and the server enforces them |
| M4 | Read-only `GET workforce/employees/` for Managers and Admins (`employees.view_any`), with search, role and active filters, and no pay data |
| M5 | Punches are written to the outbox first, then submitted online; if the server can't be reached they stay queued under the same `event_id`. New punches queue behind older unsent ones. |
| M6 | Cached reference data older than 24 hours shows a warning; it never blocks clock-in |
| M7 | Manager and Admin group punches are online-only; a retry reuses the same `event_id` |
| M8 | If the clock-in at the new job is refused after the clock-out at the old one, the app shows the refusal and offers "Clock back in"; nothing is reversed automatically |
| M9 | jest-expo and React Native Testing Library |
| M10 | Signing out with unsent punches warns and asks for confirmation; punches are never deleted |
| M11 | Company timezone `America/Toronto` for display and work dates |
| M12 | Geofence entry with latitude and longitude fields and a "use my current location" button; no map library |
| Ownership | Every outbox event stores the user id of the account that recorded it. Events sync only while that account is signed in, never with another account's token. Sign-out never deletes them. Events queued before ownership existed have no owner and are never synced automatically. |

### Raised by the mobile integration (unresolved)

| # | Question | Current behaviour |
| --- | --- | --- |
| MB1 | **Ownerless legacy events.** Events queued before local migration 002 have no owner. No released app version queued punches, so none should exist. | Kept and shown as waiting for another account; never synced or deleted. A manual recovery path could be added if one is ever found. |
| MB2 | **Clock-back-in after a refused switch that was synced later.** M8's offer appears when the refusal arrives online. For a switch queued offline, the refusal appears later in History. | The employee clocks in again by hand from the Time screen. |
| MB3 | **Crew status after an offline group punch.** The LeadHand's cached roster does not reflect queued group punches until they sync. | The result message says so; the roster refreshes after sync. |
| MB4 | **Offline access to another account's cached data.** Cached reference data is cleared at sign-out, so a user who signs in must be online. | Sign-in always needs the server. |

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
| Team notes | Notes are per job, everyone can create them, authors can't edit or delete them, they have urgency categories and work offline. The `workers_can_create_notes` setting is superseded. | ADR 009 (2026-11-10 update) |
| How a LeadHand is linked to a job | They manage a job when they are its `lead_hand` **and** hold an active assignment on it | ADR 011 |
| Clients | A separate, standalone table, view-only; future payroll report access | ADR 010 |
| Roles | Four roles (Admin, Manager, LeadHand, Employee = stored `worker`), one per user; all are employees | ADR 011 |
| Manager scope | Company-wide (D2). Manages LeadHand and Employee accounts, not Managers (D8). | ADR 011 |
| Admin and Manager attendance for others | Administrative entries: location stored but not flagged, optional reason, must be current (D3) | ADR 011 |
| Self-approval | Nobody reviews their own timesheet (D4) | ADR 011 |
| Django admin | Superuser-only | ADR 011 |
