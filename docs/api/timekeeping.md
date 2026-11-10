# Timekeeping API (Phase 1)

Base path: `/api/v1/`. All endpoints require `Authorization: Bearer <access token>`.
Errors use the standard envelope (`docs/api/README.md`).

| Method | Path | Who | Purpose |
| --- | --- | --- | --- |
| POST | `timekeeping/clock-in/` | Every role, with an employee record | Clock yourself in |
| POST | `timekeeping/clock-out/` | Every role, with an employee record | Clock yourself out |
| POST | `timekeeping/group-clock-in/` | LeadHand (jobs they manage), Manager, Admin | Clock several employees in |
| POST | `timekeeping/group-clock-out/` | LeadHand (jobs they manage), Manager, Admin | Clock several employees out |
| POST | `timekeeping/sync/` | As for the event types above | Upload the offline queue |
| GET | `timekeeping/status/` | Every role, with an employee record | Am I clocked in? |
| GET | `timekeeping/sessions/` | Every role, with an employee record | My attendance history (paginated; always personal) |
| GET | `timekeeping/sessions/{id}/` | Every role, with an employee record | One of my sessions (404 if not mine) |
| GET | `timekeeping/jobs/{job_id}/crew/` | LeadHand (jobs they manage), Manager, Admin | Assigned crew and who is clocked in |
| GET | `staff/attendance/` | LeadHand (jobs they manage), Manager, Admin | Attendance records |
| GET | `staff/attendance/exceptions/` | LeadHand (jobs they manage), Manager, Admin | Sessions pending review |
| GET | `staff/attendance/rejected-events/` | LeadHand (jobs they manage), Manager, Admin | Rejected punches (sync exceptions) |
| GET | `staff/attendance/{id}/` | LeadHand (jobs they manage), Manager, Admin | Session with review history |
| POST | `staff/attendance/{id}/review/` | Manager, Admin; **never your own timesheet** | Approve or reject a session |

**A LeadHand manages a job** when they are its `lead_hand` **and** hold an
active assignment on it (ADR 011). Managers and Admins work company-wide.
Records outside the caller's scope return 404.

## Concepts

- **Event.** One clock-in or clock-out action performed on a device, with a
  client-generated `event_id` (UUID). It is stored as an `AttendanceBatch`.
- **Result.** The outcome for one employee in an event, stored as an
  `AttendanceBatchItem`. A result is `accepted` or `rejected`, and has a
  stable `code`.
- **Session.** One employee's attendance on one job, from clock-in to
  clock-out (`WorkSession`). A group punch always creates separate sessions:
  one per employee.
- **Times.**
  - `captured_at` is the device time of the punch. It must include a UTC
    offset, and it is the time used for the session.
  - `received_at` is when the server received the punch. It is stored
    separately and never replaces the device time.
  - `work_date` is `captured_at` converted to the company timezone
    (`America/Toronto`). The phone's timezone never matters.
  - Responses render times in the company timezone.

## Request body

The same fields are used by every punch endpoint and by each sync event.

```json
{
  "event_id": "6f1c1d2e-4b0a-4f57-9d55-1d0f3a2b7c10",
  "job_id": 12,
  "captured_at": "2026-03-10T08:00:00-04:00",
  "location": {"latitude": 43.6431, "longitude": -79.3871, "accuracy_meters": 8.5}
}
```

| Field | Rules |
| --- | --- |
| `event_id` | Required UUID, generated once per event on the device. It is the idempotency key. |
| `job_id` | Required, and must be an existing job. For clock-out, it is the job of the open session. |
| `captured_at` | Required ISO 8601 datetime **with** a UTC offset. Naive times are rejected with a 400. |
| `location` | Optional. Omit it or send `null` when no fix is available. It is **never** validated strictly: bad values are discarded and flagged (see Location flags below). |
| `employee_ids` | Group and sync events only: 1–100 unique employee ids. Individual endpoints **ignore** it, because the employee always comes from the token. |
| `action_type` | Sync events only: `clock_in` or `clock_out`. |
| `reason` | Group and sync events only. Optional, at most 500 characters, and stored as `entry_reason`. It is mainly for administrative entries. |

A request is rejected with **400** only when it is structurally invalid:
- a missing or malformed `event_id`
- an unknown job
- a missing or naive `captured_at`
- bad `employee_ids`
- an unknown `action_type`

Nothing is stored for a 400.

## Response: the event result

All punch endpoints return the same shape, also used inside sync results.
It is built from stored data only, so a retry returns an identical body,
apart from `replayed`.

```json
{
  "event_id": "6f1c1d2e-4b0a-4f57-9d55-1d0f3a2b7c10",
  "batch_id": 431,
  "action_type": "clock_in",
  "source": "mobile_online",
  "job": {"id": 12, "job_number": "J-100", "name": "Warehouse fit-out"},
  "performed_by": {"id": 7, "email": "lee@example.com"},
  "captured_at": "2026-03-10T08:00:00-04:00",
  "received_at": "2026-03-10T08:00:02-04:00",
  "entry_reason": "",
  "location": {
    "status": "verified",
    "flags": [],
    "requires_review": false,
    "latitude": "43.643100",
    "longitude": "-79.387100",
    "accuracy_meters": "8.50",
    "distance_meters": "55.60"
  },
  "results": [
    {
      "employee": {"id": 3, "name": "Wendy Worker"},
      "status": "accepted",
      "code": "clocked_in",
      "message": "Clocked in at 2026-03-10 08:00 EDT.",
      "session_id": 88,
      "punch_id": 140,
      "processed_at": "2026-03-10T08:00:02-04:00"
    }
  ],
  "replayed": false
}
```

### Result codes

| Code | Status | Meaning |
| --- | --- | --- |
| `clocked_in` | accepted | A new session was opened |
| `clocked_out` | accepted | The open session was closed |
| `employee_inactive` | rejected | The employee is inactive (clock-in only) |
| `job_not_active` | rejected | The job's status is not active (clock-in only) |
| `no_active_assignment` | rejected | The employee has no active assignment to the job |
| `assignment_not_in_effect` | rejected | The work date is outside the assignment's start and end dates |
| `already_clocked_in` | rejected | The employee has an open session, on this job or another one |
| `no_open_session` | rejected | There is nothing to clock out of |
| `open_session_on_other_job` | rejected | The open session is on a different job |
| `clock_out_before_clock_in` | rejected | The clock-out time is before the session's clock-in time. The session is flagged `clock_out_rejected`. |
| `overlaps_existing_session` | rejected | The punch would overlap one of the employee's other sessions. On a clock-out, the session is flagged `clock_out_rejected`. |

## Individual clock-in and clock-out

`POST timekeeping/clock-in/` and `POST timekeeping/clock-out/`

- The employee is always the authenticated user's employee record. A user
  without one gets **403** `no_employee_profile`.
- **201**: the event result, with one accepted result.
- A **rejected** punch is still stored, so retries are idempotent. It is
  returned as an error, with the full stored result in `details.result`:
  - **403** for `no_active_assignment`, `assignment_not_in_effect` and
    `employee_inactive`
  - **409** for every other rejection code

  ```json
  {"error": {"code": "already_clocked_in",
             "message": "Already clocked in to job J-100 since 2026-03-10 08:00 EDT.",
             "details": {"result": {"event_id": "...", "results": [{"status": "rejected", "...": "..."}]}}}}
  ```

## Group clock-in and clock-out

`POST timekeeping/group-clock-in/` and `POST timekeeping/group-clock-out/`,
with an `employee_ids` list in the body.

**Who may call it.**
- A **LeadHand**, for a job they manage. They must be the job's `lead_hand`
  and hold an active assignment on it. Otherwise the response is **403**
  `not_job_lead_hand` and nothing is stored.
- An **Admin or Manager**, for any employee on any job.
- **Employees** get **403** `permission_denied`. Through sync, they get
  `group_attendance_not_allowed`.

**How it works.**
- Each employee is validated independently against their own active
  assignment and attendance state. One failure never affects the others.
- Each accepted employee gets their own punch and session, and the batch
  records the caller as `performed_by`.
- The location is the caller's device fix, assessed once for the whole
  batch.
- To clock themselves in, a caller includes their own employee id, or uses
  the individual endpoint. They need an active assignment to the job either
  way; none is created automatically.
- **201** with one result per employee, including partial rejections.
  Repeating the request with the same `event_id` returns the same body,
  with `replayed: true`.

### Administrative entries (Admin and Manager)

When an Admin or Manager records attendance for **anyone other than
themselves**:

- The batch's `source` is `admin_entry`. This applies online and through
  sync, where it replaces `mobile_offline_sync`.
- An optional `reason` is stored and returned as `entry_reason`.
- The location is stored for reference, but **never flags the session**,
  because the entry may be made from an office. `location.requires_review`
  is `false`.
- Each employee's active assignment is still required.
- **The entry must be current.** If `captured_at` is more than 15 minutes
  (`ATTENDANCE_ADMIN_ENTRY_MAX_AGE_SECONDS`) before the server receives it,
  the response is **400** `admin_entry_not_current` and nothing is stored.
  Through sync, that event's result is an `error` with the same code. Past
  times will be handled by the future correction workflow.

An Admin or Manager punching only themselves is a normal self punch:
its source is `mobile_online` or `mobile_offline_sync`, and the normal
location flags apply.

## Offline synchronisation

`POST timekeeping/sync/` with a body of up to 100 events:

```json
{"events": [
  {"event_id": "…", "action_type": "clock_in",  "job_id": 12, "captured_at": "2026-03-10T08:00:00-04:00", "location": null},
  {"event_id": "…", "action_type": "clock_out", "job_id": 12, "captured_at": "2026-03-10T12:00:00-04:00", "location": {"latitude": 43.6431, "longitude": -79.3871, "accuracy_meters": 12}},
  {"event_id": "…", "action_type": "clock_in",  "job_id": 12, "captured_at": "2026-03-10T08:05:00-04:00", "employee_ids": [4, 5, 9]}
]}
```

- **Ordering.** Events are processed in **device-time order**
  (`captured_at`, then submission order), whatever order they were queued or
  received in. An 08:00 clock-in and a 12:00 clock-out uploaded together at
  15:00 produce an 08:00–12:00 session.
- **Isolation.** Each event is processed in its own database transaction.
  An invalid or failing event never affects the others.
- **Response.** Always **200** for a well-formed envelope. The results come
  back in **submission order**, one per event:

| `status` | Meaning | What the device should do |
| --- | --- | --- |
| `processed` | Stored. `batch` holds the event result, with per-employee `accepted` or `rejected` results. | Mark it synced. Show rejected employees to the user, because they won't succeed on retry. |
| `invalid` | Structurally invalid; `error.details` has field errors. Nothing was stored. | Stop retrying; this is a bug or data problem. |
| `error` | The event is not allowed (`not_job_lead_hand`, `group_attendance_not_allowed`, `attendance_not_allowed`, `no_employee_profile`, `admin_entry_not_current`) or its `event_id` conflicts (`idempotency_key_conflict`). Nothing was stored. | Stop retrying. |

- An envelope that isn't an object with a non-empty `events` list of at most
  100 items gets a **400**.
- A network error or 5xx means nothing was stored for any event that hadn't
  finished processing. Retry the whole upload: events that were already
  stored replay their results, and the rest are processed.

### Idempotency

- `event_id` is unique across all attendance. Sending the same event again,
  online or through sync, by the same user and with the same job, action,
  time and employees, returns the stored result with `replayed: true`. It
  never creates anything new. The original `source` is preserved.
- Re-using an `event_id` for a **different** event, or from a different user,
  returns **409** `idempotency_key_conflict`. Another user's event is never
  revealed.
- **Concurrent duplicates are safe.** The unique index makes the second
  request wait for the first to commit, and it then replays the first
  request's result.
- **One employee at a time.** All writes for an employee are serialised with
  a row lock, so two devices punching the same employee at once produce
  exactly one accepted result.

### Reconciliation rules

| Situation | Result |
| --- | --- |
| A clock-in while a session is open (any job) | `already_clocked_in` |
| A clock-in whose time falls inside one of the employee's closed sessions | `overlaps_existing_session` |
| A late-arriving earlier session that does not overlap anything | Accepted normally |
| A clock-out earlier than the open session's clock-in | Rejected `clock_out_before_clock_in`; the session stays open and is flagged `clock_out_rejected` |
| A clock-out that would make the session overlap another session | Rejected `overlaps_existing_session`; the session stays open and is flagged `clock_out_rejected` |
| A device time more than 5 minutes ahead of server time (`ATTENDANCE_FUTURE_TOLERANCE_SECONDS`) | Accepted; flagged `future_timestamp` |

Rejected events stay visible to staff in `staff/attendance/rejected-events/`.

## Location flags

The location is assessed once per event against the job's geofence (ADR 004).
The geofence is a circle around the job's coordinates, 100 m by default.

| Location status / flag | When | Coordinates | Review |
| --- | --- | --- | --- |
| `verified` | Inside the geofence, accuracy ≤ 30 m | kept | no |
| `outside_geofence` | Outside the geofence | kept | yes |
| `low_accuracy` | Accuracy worse than 30 m | kept | yes |
| `accuracy_unknown` | Accuracy missing or invalid | kept | yes |
| `location_unavailable` | No coordinates sent | none | yes |
| `invalid_coordinates` | Malformed, partial or out-of-range coordinates | **discarded** | yes |
| `geofence_not_configured` | The job has no coordinates | kept | no |

- A location problem **never** rejects a punch.
- If any flag requires review, it is added to each affected session's
  `exception_flags`, without duplicates, and the session's `review_status`
  becomes `pending`.

## Status, history and crew

- `GET timekeeping/status/` returns
  `{"employee": {...}, "clocked_in": true, "open_session": <session>|null}`.
- `GET timekeeping/sessions/` lists your sessions, newest first. Filters:
  `work_date_from`, `work_date_to` (YYYY-MM-DD) and `job_id`. It returns the
  standard paginated shape.
- A session looks like this:

```json
{
  "id": 88, "employee": {"id": 3, "name": "Wendy Worker"},
  "job": {"id": 12, "job_number": "J-100", "name": "Warehouse fit-out"},
  "work_date": "2026-03-10", "session_status": "closed", "review_status": "pending",
  "exception_flags": ["outside_geofence"],
  "clock_in":  {"punch_id": 140, "at": "2026-03-10T08:00:00-04:00", "received_at": "…", "event_id": "…",
                "source": "mobile_offline_sync", "performed_by": {"id": 7, "email": "…"}, "location": {"…": "…"}},
  "clock_out": {"…": "…"},
  "duration_seconds": 14400, "reviewed_by": null, "reviewed_at": null
}
```

- `GET timekeeping/jobs/{job_id}/crew/` lists employees with an active
  assignment to the job: `has_account`, `clocked_in`, and the open session's
  job and `clock_in_at`. It is for the LeadHand group-clock screen. A
  LeadHand who doesn't lead the job gets a 404.

## Staff attendance and review

- The staff lists add the filters `employee_id`, `review_status` and
  `session_status`. Each session also includes `reviews`, newest first.
- `exceptions/` lists sessions with `review_status = pending`.
- `rejected-events/` lists rejected results with their event's device time,
  source, performer and code. Filters: `job_id`, `employee_id`.
- `POST staff/attendance/{id}/review/` (Manager or Admin) takes
  `{"decision": "approved"|"rejected", "reason": "…"}`.
  - **No one may review their own timesheet:** **403**
    `cannot_review_own_timesheet`, for approving and for rejecting.
    A Manager's or Admin's own attendance is reviewed by someone else.
  - `reason` is required and must not be blank.
  - Only **closed** sessions can be reviewed; an open one gets **409**
    `session_open`.
  - Each decision appends a `WorkSessionReview`. These rows can't be edited
    or deleted.
  - The session's `review_status`, `reviewed_by` and `reviewed_at` show the
    latest decision.
  - Punches, batches, GPS data and exception flags are never changed.
  - **201** with the session and its full review history.

### Permissions

Permissions are defined centrally (ADR 011, `apps/accounts/authorization.py`)
and applied in `apps/timekeeping/api/permissions.py` and the scope selectors:

- **LeadHands** can view attendance, exceptions and rejected events only for
  jobs they manage. They cannot review.
- **Managers and Admins** have company-wide access and can review anyone's
  timesheet except their own.
- **Employees** have no staff access.
