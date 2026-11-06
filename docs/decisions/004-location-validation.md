# ADR 004: Location validation

- Status: Accepted; rules confirmed
- Date: 2026-11-06 (revised: bad GPS data never rejects a punch; jobs
  without a geofence)

## Context

Punches should come from the job site, but GPS is imprecise, permissions can
be denied, and some jobs have no defined site. **Attendance recording and
location validation are separate concerns.** Invalid GPS data must never
stop a worker from recording attendance.

## Decision

### Job site geometry

- A job **may** have a circular geofence: a centre latitude and longitude,
  plus a radius in metres.
- Coordinates are **optional**. A job without them is valid and can be
  punched against.
- The radius defaults to **100 m** (the database default on the job field)
  and can be customised per job. If a job has coordinates but no radius, the
  100 m default applies. A company-wide default may come later.
- Polygon geofences are not part of the initial version. The logic is
  isolated so they can be added later.

### Captured per punch

- From the device: latitude, longitude, GPS accuracy in metres, and the
  device timestamp.
- From the server: the received timestamp.
- Computed: the distance from the geofence centre, the primary location
  status, the full list of flags, and whether the punch requires review.

### Rules

| Condition | Coordinates | Status / flag | Review |
| --- | --- | --- | --- |
| Inside the radius, accuracy ≤ 30 m | kept | `verified` | no |
| Outside the radius | kept | `outside_geofence` | yes |
| Accuracy > 30 m (`LOCATION_MAX_ACCURACY_METERS`) | kept | `low_accuracy` | yes |
| Accuracy missing or invalid | kept | `accuracy_unknown` | yes |
| No coordinates sent | none | `location_unavailable` | yes |
| Malformed, partial or out-of-range coordinates | **discarded** | `invalid_coordinates` | yes |
| Job has no geofence | kept | `geofence_not_configured` | **no**\* |

- Boundaries are inclusive: exactly at the radius, or exactly 30 m accuracy,
  counts as `verified`.
- Several flags can apply at once. The **primary status** is the first flag
  in the table's order, with review-requiring flags ahead of
  `geofence_not_configured`. All flags are stored.
- **No location condition rejects a punch.** The punch is always stored and
  synced to PostgreSQL. The device and server timestamps are preserved.
- Only **structurally invalid punch events** are rejected through normal
  request validation:
  - missing or malformed event UUID
  - invalid event type
  - unknown job or employee reference
  - unauthorised actor

  The location fields are therefore accepted as raw values by the API
  serializer and passed to the assessor untouched.

\* **Assumption:** a missing geofence is a configuration gap, not a worker
issue, so on its own it does not put the punch in the review queue. GPS
problems on such a job (for example `low_accuracy`) are still flagged. This
can be changed in one place (`_INFORMATIONAL`) with no schema change.

### Implementation

The rules are pure functions in
`backend/apps/timekeeping/services/location_validation.py`. They have no
database access, never raise for bad GPS data, and are fully unit-tested.

- `build_job_geofence(latitude, longitude, radius_meters)` returns a
  `CircularGeofence`, or `None` when the job has no coordinates.
- `assess_punch_location(latitude, longitude, accuracy_meters, geofence)`
  returns a `LocationAssessment` with:
  - `status`, `flags` and `requires_review`
  - sanitised `coordinates` and `accuracy_meters`
  - `distance_meters`

Storage precision:

- Coordinates use `DecimalField(max_digits=9, decimal_places=6)`.
  Incoming values are quantised to fit.
- Accuracy and distance use `DecimalField(max_digits=10, decimal_places=2)`.

No PostGIS.

## Consequences

- The job table needs nullable `latitude` and `longitude`, a check constraint
  that requires both or neither, and a radius with a 100 m default.
- The assessment is stored once per `AttendanceBatch`:
  - sanitised coordinates and accuracy
  - `distance_meters`
  - `location_status`
  - `location_flags`

  When it requires review, the affected `WorkSession`s get
  `review_status = pending`.
- Android mock locations and device clock skew are captured but not yet
  flags. Adding them requires a new `LocationStatus` value, not a schema
  change.
