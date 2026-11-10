# Jobs and Assignments API

Base path: `/api/v1/`. Every endpoint requires `Authorization: Bearer <access token>`.
Errors use the standard envelope (`docs/api/README.md`). Lists use the
standard pagination.

- **Records outside your scope return 404,** the same as records that don't
  exist.
- **Records you can see but aren't allowed to change return 403.**
- **Unknown request fields are rejected with 400,** not silently ignored.

## Endpoints and permissions

| Method | Path | Admin | Manager | LeadHand | Employee |
| --- | --- | --- | --- | --- | --- |
| GET | `jobs/` | all jobs | all jobs | jobs they are assigned to | jobs they are assigned to |
| POST | `jobs/` | ✓ all fields | ✓ all fields | ✓ limited fields; becomes the job's LeadHand | 403 |
| GET | `jobs/{id}/` | ✓ | ✓ | assigned jobs | assigned jobs |
| PATCH | `jobs/{id}/` | ✓ all fields | ✓ all fields | jobs they **manage**, limited fields | 403 |
| PUT | `jobs/{id}/lead-hand/` | ✓ | ✓ | 403 | 403 |
| GET | `jobs/{id}/assignments/` | ✓ | ✓ | jobs they manage | 403 |
| POST | `jobs/{id}/assignments/` | ✓ | ✓ | 403 | 403 |
| GET | `assignments/` | all | all | crew of jobs they manage, plus their own | their own |
| GET | `assignments/mine/` | own | own | own | own |
| GET | `assignments/{id}/` | ✓ | ✓ | as for the list | own only |
| PATCH | `assignments/{id}/` | ✓ | ✓ | 403 | 403 |
| POST | `assignments/{id}/end/` | ✓ | ✓ | 403 | 403 |
| POST | `assignments/{id}/cancel/` | ✓ | ✓ | 403 | 403 |

**Key terms.**

- **A LeadHand manages a job** when they are its `lead_hand` **and** hold an
  active assignment on it (ADR 011).
- **Assigned to** means holding an active assignment.
- **Employees** never see other crew members' assignments.

**How permissions are enforced.**

- Capabilities come from `apps/accounts/authorization.py`:
  - `jobs.view_assigned`, `jobs.view_any`
  - `jobs.create`, `jobs.edit_any`, `jobs.edit_managed`
  - `assignments.manage`, `assignments.view_crew`
- Which records a user may touch is decided in
  `apps/jobs/selectors/scope.py`.

## Jobs

### Job object

```json
{"id": 12, "job_number": "J-100", "name": "Warehouse fit-out", "address": "1 Main St",
 "status": "active", "start_date": "2026-11-01", "end_date": null,
 "geofence": {"configured": true, "latitude": "43.642600", "longitude": "-79.387100", "radius_meters": 100},
 "lead_hand": {"employee_id": 7, "name": "Lee Lead"},
 "viewer": {"manages_job": true, "is_lead_hand": true, "my_assignment_id": 31},
 "created_by": {"id": 3, "name": "Max Manager"}, "updated_by": {"id": 3, "name": "Max Manager"},
 "created_at": "…", "updated_at": "…"}
```

- `viewer` describes the caller's relationship to the job.
- People are shown by id and name only. Emails and pay rates are never
  included.
- `radius_meters: null` means the default 100 m applies when coordinates are
  set.

### List: `GET jobs/`

Filters:
- `status`: `planned`, `active`, `on_hold`, `completed` or `cancelled`
- `search`: job number or name, case-insensitive
- `managed_by_me=true`
- `assigned_to_me=true`

Results are ordered by job number.

### Create: `POST jobs/`

```json
{"job_number": "J-101", "name": "New site", "address": "2 Side St",
 "start_date": "2026-12-01", "end_date": null,
 "latitude": "43.642600", "longitude": "-79.387100", "geofence_radius_meters": 150,
 "status": "planned", "lead_hand_id": 7}
```

- **Required fields:** `job_number` and `name`. The job number is entered by
  hand for now (Q2), and must be unique.
- **Field limits by role:**

  | Caller | May set |
  | --- | --- |
  | Admin, Manager | Every field, including `lead_hand_id` |
  | LeadHand | Only `job_number`, `name`, `address`, `start_date` and `end_date` (Q3) |

  Any other field from a LeadHand gets **403** `field_not_editable`, listing
  the fields.
- **A LeadHand who creates a job** automatically becomes its `lead_hand` and
  gets an active assignment to it, so they manage it straight away (Q1).
- **`lead_hand_id`** designates a LeadHand and assigns them if needed (Q4).
  The job must accept assignments.
- **Validation errors (400):**
  - duplicate or blank `job_number`
  - latitude without longitude, or the reverse
  - latitude or longitude out of range
  - radius below 1
  - `end_date` before `start_date`
  - unknown fields
- **201** with the job object.

### Edit: `PATCH jobs/{id}/`

- Any subset of the create fields, except `lead_hand_id`, which has its own
  endpoint.
- **Field limits by role:**
  - **LeadHand:** only on jobs they manage, and only `name`, `address`,
    `start_date` and `end_date`. Other fields get **403**
    `field_not_editable`.
  - **A job the LeadHand works on but doesn't manage:** **403**
    `job_not_editable`.
  - **Admin, Manager:** every field, including the job number, status and
    geofence.
- Changing the geofence affects only new punches. Stored location
  assessments are never recomputed.
- Changing the status to a non-active value blocks new clock-ins
  (`job_not_active`). Clock-outs still work.
- Completing or cancelling a job does **not** end its assignments (Q8).

### Designate the LeadHand: `PUT jobs/{id}/lead-hand/`

Body: `{"employee_id": 7}`, or `{"employee_id": null}` to clear.

- **The designee must be** an active employee with an active user account
  that has the LeadHand role. Otherwise the response is **400**
  `not_eligible_lead_hand`.
- **The job must accept assignments.** Otherwise the response is **409**
  `job_not_assignable`.
- **The designee is assigned automatically** if they don't already have an
  active assignment on the job, with the caller recorded as the assigner
  (Q4).
- **The previous LeadHand keeps their assignment** and stays on the crew.
- **Effect on timekeeping is immediate:** group punches, crew status and
  staff attendance follow the new designation.

## Assignments

### Assignment object

```json
{"id": 31, "job": {"id": 12, "job_number": "J-100", "name": "Warehouse fit-out"},
 "employee": {"id": 5, "name": "Ana", "employee_number": "E-5", "has_account": true},
 "status": "active", "start_date": null, "end_date": null, "is_lead_hand": false,
 "assigned_at": "…", "assigned_by": {"id": 3, "name": "Max Manager"}, "updated_at": "…"}
```

### Assign: `POST jobs/{id}/assignments/` (Admin, Manager)

```json
{"employee_ids": [5, 6, 9], "start_date": "2026-12-01", "end_date": null}
```

- The job must be `planned`, `active` or `on_hold`. Otherwise the response
  is **409** `job_not_assignable` and nothing is created.
- `employee_ids` holds 1 to 100 unique, existing ids; anything else is a 400.
- Employees without app accounts can be assigned. Their LeadHand clocks
  them in and out.
- **201**, with one result per employee (Q10):

```json
{"job": {"id": 12, "job_number": "J-100"},
 "results": [
   {"employee_id": 5, "status": "assigned", "code": "assigned", "message": "…", "assignment": {…}},
   {"employee_id": 6, "status": "rejected", "code": "already_assigned", "message": "…", "assignment": {…existing…}},
   {"employee_id": 9, "status": "rejected", "code": "employee_inactive", "message": "…", "assignment": null}
 ]}
```

Two requests assigning the same employee at the same moment create one
assignment; the other request reports `already_assigned`.

### List: `GET assignments/`, `GET jobs/{id}/assignments/`, `GET assignments/mine/`

- Filters: `status` (`active` by default, or `ended`, `cancelled`, or `all`
  for full history), `job_id` and `employee_id`.
- `assignments/mine/` returns only the caller's own assignments, even for
  Managers and LeadHands. It is the list the mobile app caches for offline
  use.

### Change dates: `PATCH assignments/{id}/` (Admin, Manager)

- Body: `start_date` and/or `end_date`. Send `null` to clear a date.
- Only active assignments can be changed (**409** `assignment_not_active`).
- The employee and job never change; send them and you get a 400.
- Timekeeping refuses clock-ins outside the dates
  (`assignment_not_in_effect`).
- A future end date schedules the end of an assignment.

### End: `POST assignments/{id}/end/` (Admin, Manager)

- Body: optional `{"end_date": "YYYY-MM-DD"}`, defaulting to today in the
  company timezone.
- **Errors:**
  - **400** `end_date_in_future`: use PATCH to schedule an end instead
  - **400** for an end date before the start date
  - **409** `assignment_not_active`
- **Sets** `status` to `ended`. The row and all attendance linked to it are
  kept.
- **If the employee is the job's designated LeadHand, the designation is
  cleared** (Q4).
- **An employee who is clocked in can still clock out** (Q5).
- **Offline punches** captured before the end, and dated on or before the
  end date, are still accepted when they sync later (Q6). Live clock-ins
  after the end are refused.

### Cancel: `POST assignments/{id}/cancel/` (Admin, Manager)

- No body. For assignments made in error.
- **Allowed only when the assignment has no work sessions** (Q7).
  Otherwise the response is **409** `assignment_has_sessions`; end it
  instead.
- Clears the LeadHand designation in the same way as ending.

### Lifecycle summary

| From | To | How |
| --- | --- | --- |
| *(none)* | active | assign, or LeadHand designation, or a LeadHand creating a job |
| active | ended | `end/` |
| active | cancelled | `cancel/`, only without sessions |
| ended or cancelled | anything | never; assign again to create a new row |

There is no DELETE for jobs or assignments. History is always kept.
**Moving between job sites never changes an assignment** (see
`docs/api/timekeeping.md`).
