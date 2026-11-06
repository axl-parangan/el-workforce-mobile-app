# Offline layer

Implements the device side of
[ADR 002](../../../docs/decisions/002-offline-first-timekeeping.md).

```text
offline/
├── database/      # opens the SQLite DB and runs migrations (via <SQLiteProvider onInit>)
├── migrations/    # versioned local schema (PRAGMA user_version), append-only
├── queue/         # pending_events outbox: enqueue + status transitions
├── repositories/  # TODO: cached reference data (profile, assigned jobs, crew roster)
└── sync/          # TODO: sync runner that drains the outbox
```

## Flow of an offline-capable action (e.g. a punch)

```text
UI ──► feature service ──► db.withTransactionAsync(
                              write local record (repositories/)
                              enqueuePendingEvent(queue/)        ◄── UUID = idempotency key
                           )
                                   │
         triggers: network regained / app foregrounded / manual / new event while online
                                   ▼
                           sync runner (sync/)
                             listPendingEvents → markEventSyncing
                             POST batch to API
                             per-event result:
                               accepted | duplicate | flagged → markEventSynced
                               rejected                       → markEventRejected (kept, shown to user)
                               network error / 5xx            → markEventForRetry
```

## Rules

- **Write locally first.** Do not decide whether to write based on
  connectivity; `useNetworkStatus()` is for UI hints only.
- **Never delete unsynced events**, including on sign-out or session expiry.
- **Every event has a client UUID** (`newClientId()`), and the server
  de-duplicates on it.
- **Migrations are append-only.** Never edit a migration that has shipped.
- The **server is authoritative**. Local state is provisional until synced.

## Not implemented yet (by design)

- The sync runner and its triggers. The server endpoint now exists:
  `POST /api/v1/timekeeping/sync/` (see `docs/api/timekeeping.md`). One
  outbox `punch` event maps to one sync event, and `pending_events.id` is
  its `event_id`.
- The punch payload shape and local punch/session tables. These depend on
  the timekeeping ERD.
- Cached repositories for jobs and crew. These depend on the jobs and
  workforce ERD.
- Background sync while the app is closed.
