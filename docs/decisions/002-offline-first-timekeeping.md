# ADR 002: Offline-first timekeeping

- Status: Accepted (design); sync engine not yet implemented
- Date: 2026-11-06

## Context

Construction sites often have weak or no connectivity. A worker or LeadHand
must be able to clock in and out at any time. A failed network request must
never lose a punch or prevent one.

## Decision

Writes that must work offline, starting with punches, follow an **outbox**
pattern on the device:

1. **Write locally first.** The punch is recorded in SQLite (`expo-sqlite`).
   In the same transaction, an entry is added to the `pending_events`
   outbox table (`mobile/src/offline/`). The UI reads local state, so it
   updates immediately.
2. **Client-generated identity.** Each event gets a UUID on the device
   (`expo-crypto`). The server stores it under a unique constraint and uses
   it as an **idempotency key**. Re-sending an event that was already
   received returns the original result without creating a duplicate.
   - For punches, one outbox event is one `AttendanceBatch`, whether
     individual or group. Its UUID is `AttendanceBatch.idempotency_key`.
   - Per-employee outcomes come back as the batch's items (ADR 003, 006).
3. **Sync later.** A sync runner sends pending events oldest-first when it is
   triggered by any of these:
   - the device regains connectivity (`expo-network`)
   - the app returns to the foreground
   - the user asks for a manual sync
   - a new event is queued while online
4. **Per-event results** (implemented in Phase 1: `POST /api/v1/timekeeping/sync/`,
   see `docs/api/timekeeping.md`). The server processes the events in
   device-time order, each in its own transaction, and returns one result per
   event in submission order:
   - `processed`: the event is stored. Its per-employee results are
     `accepted` or `rejected`, each with a stable `code`. Location problems
     never cause a rejection; they flag the session for review (ADR 004).
     Retries replay the stored result with `replayed: true`. The device marks
     the event `synced` and shows any rejected employees.
   - `invalid` or `error`: the event is structurally invalid (bad UUID, event
     type, job or employees), unauthorised, or reuses an `event_id`. Nothing
     is stored. The device marks it `rejected`, keeps it, and shows it to the
     user. It is never silently dropped.
   - A transport failure, timeout or 5xx keeps the event `pending` and
     increments `attempts`. A retry is always safe.
   - Punches that can't be reconciled, such as a clock-out earlier than the
     clock-in or one that would overlap another session, are rejected rather
     than producing wrong attendance. The open session is flagged
     `clock_out_rejected` for review.
5. **Reference data is cached** so punches can be composed offline: the
   user's profile, assigned jobs, and a LeadHand's crew roster. Cached
   repositories live in `mobile/src/offline/repositories/`.
6. **The server is authoritative.** It re-validates every event when it
   arrives: assignment, permissions, duplicate punch state, and location
   (ADR 004). The device's view is provisional until synced.

### Sessions and tokens

- JWT access tokens are short-lived. Refresh tokens rotate, and their
  lifetime (`JWT_REFRESH_TOKEN_LIFETIME_DAYS`) must exceed the longest
  realistic offline period.
- Punches can be recorded offline even when the access token has expired.
  Authentication is only needed at sync time.
- Neither an expired session nor sign-out deletes the outbox. Queued events
  wait until a user signs in again.
- The server authorises each event against the authenticated user. For
  example, an event recorded by user A cannot be submitted under user B's
  session. That rule is an open question; see
  `docs/development/open-questions.md`.

## Consequences

- Duplicate prevention needs two layers: idempotency keys (same event sent
  twice) and server-side business rules (two different events conflict, such
  as two clock-ins with no clock-out between them). Conflicting events are
  flagged for review rather than silently discarded.
- Ordering uses the device timestamp, but device clocks can be wrong. The
  server stores the device time and its own received-at time, and flags large
  clock skew.
- Background sync (syncing while the app is closed) is out of scope for now.
  It can be added later with `expo-background-task` without changing the
  outbox design.
- Not yet implemented: the sync runner (`mobile/src/offline/sync/`), the
  server batch endpoint, and the punch payload schema. They depend on the
  timekeeping data model.
