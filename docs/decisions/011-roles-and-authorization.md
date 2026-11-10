# ADR 011: Roles and centralised authorization

- Status: Accepted (role foundation implemented 2026-11-10)
- Date: 2026-11-10
- Supersedes: the role parts of ADR 006, ADR 007 and the timekeeping
  reviewer assumption

## Context

A Manager role was introduced and the LeadHand role was redefined.
Before this change, role names were compared in six places: services,
selectors, a view, model validation, permission classes and the mobile app.
Each new role would have meant editing all of them.

## Decision

### Four roles, one per user

| Role | Stored value | Summary |
| --- | --- | --- |
| Admin | `admin` | Full company-wide access. Uses the mobile app. |
| Manager | `manager` | Company-wide operations. Uses the mobile app. Manages Employee and LeadHand accounts, but not Managers. |
| LeadHand | `leadhand` | An ordinary employee with crew responsibilities on the jobs they manage. **Not** a junior Manager. |
| Employee | `worker` | Personal access only. |

- **The Employee role keeps the stored value `worker`**; only its display
  label changed. There was no data migration and no API change. The
  `workforce.Employee` model, which is the employment record, is unrelated
  and unchanged.
- **Admins, Managers and LeadHands are also employees.** Accounts created
  through the account service always get an Employee record. They clock in
  and out for themselves through the normal flow, with an active
  assignment.

### Capabilities, not role names

`apps/accounts/authorization.py` is the **only** place that maps roles to
abilities:

- `Capability` is an enum of named abilities, such as
  `attendance.record_any`.
- `ROLE_CAPABILITIES` is the fixed role-to-ability map.
- `has_capability(user, ability)` is the check everyone else calls.
- `common.permissions.requires(...)` is the DRF permission class built on
  the same check.
- `manageable_roles(actor)` and `can_manage_role(actor, role)` say which
  accounts an actor may create or manage.

The map:

| Capability | Employee | LeadHand | Manager | Admin |
| --- | :-: | :-: | :-: | :-: |
| `attendance.record_self` | ✓ | ✓ | ✓ | ✓ |
| `attendance.view_own` | ✓ | ✓ | ✓ | ✓ |
| `attendance.request_correction` (future workflow) | ✓ | ✓ | ✓ | ✓ |
| `jobs.view_assigned` | ✓ | ✓ | ✓ | ✓ |
| `attendance.record_crew` | | ✓ | | |
| `attendance.view_crew` | | ✓ | | |
| `jobs.lead` (may be a job's `lead_hand`) | | ✓ | | |
| `jobs.create`, `jobs.edit` | | ✓ | ✓ | ✓ |
| `attendance.record_any` | | | ✓ | ✓ |
| `attendance.view_any` | | | ✓ | ✓ |
| `attendance.review` | | | ✓ | ✓ |
| `jobs.view_any` | | | ✓ | ✓ |
| `assignments.manage` | | | ✓ | ✓ |
| `accounts.manage_staff` (LeadHand and Employee accounts) | | | ✓ | ✓ |
| `accounts.manage_managers` | | | | ✓ |

- The map is **fixed in code**. Runtime-editable permissions are deferred.
  The map could later be backed by Django's Group and Permission tables
  without changing any caller.
- **Inactive users, anonymous users and unknown roles have no
  capabilities.**
- A test (`tests/test_authorization_centralized.py`) fails if role names
  are compared anywhere else in application code.

### Object-level scope

`apps/jobs/selectors/scope.py` is the single definition of which jobs and
crews a user may act on. Capabilities say *whether* someone may do
something; scope says *which records*.

- **A LeadHand manages a job only when both of these hold:**
  - the job's `lead_hand` is their employee record, **and**
  - they have an **active `JobAssignment`** on that job.

  Being named, or being assigned, is not enough on its own. No ownership
  table was added.
- **A LeadHand's crew** is everyone actively assigned to the jobs they
  manage.
- **Managers and Admins** act company-wide (decision D2).
- **Employees** only see their own records.
- **Out-of-scope records return 404**, so changing an id reveals nothing.

### Attendance rules by role

| Operation | Employee | LeadHand | Manager | Admin |
| --- | --- | --- | --- | --- |
| Clock self in or out (needs an active assignment) | ✓ | ✓ | ✓ | ✓ |
| Group clock-in or out | ✗ | Crew of jobs they manage | Anyone, any job | Anyone, any job |
| Own status and history | ✓ | ✓ | ✓ | ✓ |
| Staff attendance, exceptions and rejected events | ✗ | Jobs they manage | All | All |
| Crew status | ✗ | Jobs they manage | Any job | Any job |
| Review timesheets | ✗ | ✗ | ✓ except their own | ✓ except their own |

**Administrative entries.** These are Admin or Manager punches for anyone
other than themselves:

- They are stored with `source = admin_entry`. The actor is
  `performed_by`; each employee has their own result, punch and session.
- An optional `reason` is stored in `AttendanceBatch.entry_reason`.
- The location is **stored for reference but never flags the session**,
  because these punches are often made from an office. The API shows
  `requires_review: false`.
- Each employee's active assignment is still validated.
- **They must be current.** A `captured_at` more than
  `ATTENDANCE_ADMIN_ENTRY_MAX_AGE_SECONDS` (15 minutes) before receipt is
  refused (`admin_entry_not_current`), online or through sync. The new
  company-wide access therefore can't be used to backdate attendance;
  backdating belongs to the correction workflow.
- A Manager or Admin punching only themselves is a normal self punch, and
  the normal location rules apply.

**Reviews.** Nobody can review their own timesheet
(`cannot_review_own_timesheet`). This blocks both approving and rejecting.

### Account management and privilege protection

These rules are enforced in `apps/accounts/services/accounts.py`:

| Actor | Can create and manage |
| --- | --- |
| Superuser | Every role, including Admin (normally through the Django admin) |
| Admin | Manager, LeadHand and Employee accounts |
| Manager | LeadHand and Employee accounts |
| LeadHand, Employee | None |

- No one manages their own account through the service.
- Only superusers can touch superuser accounts.
- The service never sets `is_staff` or `is_superuser`.
- Roles are fixed when an account is created (decision D9). There is no
  role-change operation.
- New accounts get an unusable password until the password-set link is
  sent; email delivery is deferred.
- **The Django admin is superuser-only** (`config/admin_site.py`). Neither
  the application role nor `is_staff` grants access.

### Mobile

- The app recognises all four roles and routes them to `(admin)`,
  `(manager)`, `(leadhand)` and `(worker)`. The last shows "Employee".
- A role the app doesn't know becomes `unknown` and shows an
  "update the app" screen instead of failing sign-in.

## Consequences

- Adding a role, or changing what a role may do, is a change to one file
  plus its matrix test.
- Database changes:
  - `accounts.0002` changes the role choices only; it runs no SQL.
  - `timekeeping.0003` adds the empty-by-default `entry_reason` column.

  No existing rows were changed.
- If a user without the `jobs.lead` capability is named as a job's
  `lead_hand`, the job fails validation.
- Deferred: runtime permission editing, the correction workflow,
  payroll and pay-rate visibility, reports, GPS authorization details,
  settings restrictions and an audit log. See
  `docs/development/open-questions.md`.
