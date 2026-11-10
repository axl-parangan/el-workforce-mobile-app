# Offline layer

Implements the device side of
[ADR 002](../../../docs/decisions/002-offline-first-timekeeping.md).

```text
offline/
├── database/        # opens the SQLite DB and runs migrations (via <SQLiteProvider onInit>)
├── migrations/      # versioned local schema (PRAGMA user_version), append-only
├── queue/           # pending_events outbox: owner-scoped enqueue, listing, status transitions
├── repositories/    # reference_cache: last-known server data per account
├── sync/            # sync runner, single-flight controller, triggers (SyncProvider)
├── cached-fetch.ts  # server first, snapshot fallback when unreachable
├── use-cached-query.ts
└── hooks.ts         # outbox counts and event lists for the UI
```

## Local schema

| Version | Change                                                                        |
| ------- | ----------------------------------------------------------------------------- |
| 1       | `pending_events` (the outbox)                                                 |
| 2       | `pending_events.user_id` (owning account) and `outcome` (server answer, JSON) |
| 3       | `reference_cache(user_id, key, payload, fetched_at)`                          |

Migrations only add things. Existing queued events keep their ids,
timestamps and statuses. Queue order is SQLite's `rowid`, so events queued
together (such as a job switch) keep their order even with equal timestamps.

## Account ownership

Every event stores the user id of the account that recorded it.

- The sync runner reads only the signed-in account's events, and re-checks
  the account before every batch.
- The auth layer clears the sync owner and waits for any running sync
  (`syncService.idle()`) before tokens change. One account's events
  therefore never travel with another account's token.
- Sign-out and session expiry never delete events. Another account's events
  stay on the phone, are shown as "waiting for that account", and sync when
  it signs in again.
- Events from before ownership existed (`user_id` NULL) are never synced
  automatically.

## Flow of a punch

```text
Time / Crew screen ──► usePunch() ──► recordPunches()
   1. account has unsent events? ──yes──► enqueue as 'pending', request sync
   2. otherwise enqueue as 'syncing' (reserved), then submit online in order:
        201 accepted                 → markEventSynced(outcome)
        403/409 with details.result  → markEventRejected(outcome)   (kept, shown in History)
        offline / 5xx / 401          → markEventForRetry; later events released to 'pending'

sync triggers: sign-in or launch, network regained, app foregrounded, after queueing
   runSync(): listPendingEvents(owner, 100) → markEventsSyncing → POST /timekeeping/sync/
     processed (accepted, or group with per-employee results) → synced
     processed (self punch refused) / invalid / error         → rejected (kept)
     network error / 5xx / missing result                     → retry (attempts + 1)
```

Manager and Admin group punches are online-only (decision M7). They never
enter the outbox; a retry reuses the same `event_id`.

## Cached reference data

`useCachedQuery` fetches from the server and stores a snapshot per account.
When the server cannot be reached (network error or 5xx), it returns the
snapshot instead. Real answers such as 403 and 404 are never hidden behind
cached data. Snapshots older than 24 hours show a warning but never block
clock-in (M6). The cache is cleared at sign-out.

Cached keys: `assignments.mine`, `jobs.assigned`, `timekeeping.status`,
`job.{id}`, `crew.{jobId}`, `sessions.page.{n}`, `session.{id}`.

## Rules

- **Write locally first.** Do not decide whether to write based on
  connectivity; `useNetworkStatus()` is for UI hints only.
- **Never delete unsynced events**, including on sign-out or session expiry.
- **Every event has a client UUID**, and the server de-duplicates on it.
- **Migrations are append-only.** Never edit a migration that has shipped.
- The **server is authoritative**. Local state is provisional until synced.

## Tests

- Database code runs against Node's SQLite (`src/test-utils/node-sqlite.ts`),
  so migrations and queue SQL are tested for real.
- `src/test-utils/fake-timekeeping-server.ts` models the server rules
  (ordering, idempotency, one open session) for runner and punch-service tests.
- `*live*.test.ts` run against a real backend when `LIVE_API_URL` is set.

## Not implemented

- Background sync while the app is closed.
- Provisional crew status from queued group punches (open question MB3).
