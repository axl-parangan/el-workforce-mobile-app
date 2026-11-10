import type { SQLiteDatabase } from 'expo-sqlite';

import { newClientId } from '@/lib/ids';

/** Extend as offline-capable actions are introduced. */
export type PendingEventType = 'punch';

export type PendingEventStatus = 'pending' | 'syncing' | 'synced' | 'rejected';

/** The server's answer, kept for history and the pending-sync screens. */
export type EventOutcome = {
  code: string;
  message: string;
  /** Per-employee results (one for a self punch, several for a group punch). */
  results?: {
    employeeId: number;
    employee: string;
    status: 'accepted' | 'rejected';
    code: string;
    message: string;
  }[];
};

export type PendingEvent = {
  /** Client-generated UUID. Sent to the server as the idempotency key (`event_id`). */
  id: string;
  type: PendingEventType;
  payload: unknown;
  status: PendingEventStatus;
  attempts: number;
  lastError: string | null;
  outcome: EventOutcome | null;
  /**
   * The account that recorded the event. Events are only synced while this
   * account is signed in. `null` for events queued before ownership existed:
   * they are never synced automatically.
   */
  userId: number | null;
  /** Insertion order (SQLite rowid). Events queued together keep their order. */
  sequence: number;
  createdAt: string;
  updatedAt: string;
};

type PendingEventRow = {
  rowid: number;
  id: string;
  type: PendingEventType;
  payload: string;
  status: PendingEventStatus;
  attempts: number;
  last_error: string | null;
  outcome: string | null;
  user_id: number | null;
  created_at: string;
  updated_at: string;
};

const COLUMNS =
  'rowid, id, type, payload, status, attempts, last_error, outcome, user_id, created_at, updated_at';

function fromRow(row: PendingEventRow): PendingEvent {
  return {
    id: row.id,
    type: row.type,
    payload: JSON.parse(row.payload) as unknown,
    status: row.status,
    attempts: row.attempts,
    lastError: row.last_error,
    outcome: row.outcome ? (JSON.parse(row.outcome) as EventOutcome) : null,
    userId: row.user_id,
    sequence: row.rowid,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

function now(): string {
  return new Date().toISOString();
}

export type NewPendingEvent = { type: PendingEventType; payload: unknown; id?: string };

/**
 * Persists events to the outbox atomically and in the given order (e.g. the
 * clock-out and clock-in of a job switch). Every event is owned by `userId`.
 *
 * `status: 'syncing'` reserves the events for an immediate online attempt so
 * the background sync runner does not send them at the same time. If the app
 * dies mid-attempt, `resetInterruptedSyncs` returns them to `pending`.
 */
export async function enqueuePendingEvents(
  db: SQLiteDatabase,
  userId: number,
  events: NewPendingEvent[],
  { status = 'pending' }: { status?: 'pending' | 'syncing' } = {},
): Promise<string[]> {
  const timestamp = now();
  const ids = events.map((event) => event.id ?? newClientId());
  await db.withTransactionAsync(async () => {
    for (const [index, event] of events.entries()) {
      await db.runAsync(
        `INSERT INTO pending_events
           (id, type, payload, status, attempts, user_id, created_at, updated_at)
         VALUES (?, ?, ?, ?, 0, ?, ?, ?)`,
        ids[index]!,
        event.type,
        JSON.stringify(event.payload),
        status,
        userId,
        timestamp,
        timestamp,
      );
    }
  });
  return ids;
}

export async function enqueuePendingEvent(
  db: SQLiteDatabase,
  userId: number,
  event: NewPendingEvent,
  options?: { status?: 'pending' | 'syncing' },
): Promise<string> {
  const [id] = await enqueuePendingEvents(db, userId, [event], options);
  return id!;
}

/**
 * The next events to sync for `userId`, in insertion order. Never returns
 * another account's events, nor events without an owner.
 */
export async function listPendingEvents(
  db: SQLiteDatabase,
  userId: number,
  limit = 100,
): Promise<PendingEvent[]> {
  const rows = await db.getAllAsync<PendingEventRow>(
    `SELECT ${COLUMNS} FROM pending_events
      WHERE status = 'pending' AND user_id = ?
      ORDER BY rowid LIMIT ?`,
    userId,
    limit,
  );
  return rows.map(fromRow);
}

/** `userId`'s events not yet accepted by the server (pending or in flight), oldest first. */
export async function listUnsyncedEvents(
  db: SQLiteDatabase,
  userId: number,
): Promise<PendingEvent[]> {
  const rows = await db.getAllAsync<PendingEventRow>(
    `SELECT ${COLUMNS} FROM pending_events
      WHERE status IN ('pending', 'syncing') AND user_id = ?
      ORDER BY rowid`,
    userId,
  );
  return rows.map(fromRow);
}

/** `userId`'s events, newest first, for the device activity list. */
export async function listRecentEvents(
  db: SQLiteDatabase,
  userId: number,
  limit = 30,
): Promise<PendingEvent[]> {
  const rows = await db.getAllAsync<PendingEventRow>(
    `SELECT ${COLUMNS} FROM pending_events WHERE user_id = ? ORDER BY rowid DESC LIMIT ?`,
    userId,
    limit,
  );
  return rows.map(fromRow);
}

/** Events synced or rejected after `since`: used to bridge a stale status snapshot. */
export async function listEventsSettledSince(
  db: SQLiteDatabase,
  userId: number,
  since: string,
): Promise<PendingEvent[]> {
  const rows = await db.getAllAsync<PendingEventRow>(
    `SELECT ${COLUMNS} FROM pending_events
      WHERE user_id = ? AND status IN ('synced', 'rejected') AND updated_at > ?
      ORDER BY rowid`,
    userId,
    since,
  );
  return rows.map(fromRow);
}

export type EventCounts = {
  /** The signed-in account's events waiting to reach the server. */
  unsynced: number;
  /** The signed-in account's events rejected in the last 24 hours. */
  recentlyRejected: number;
  /** Unsynced events recorded by other accounts (or before ownership existed). */
  otherAccounts: number;
};

export async function getEventCounts(
  db: SQLiteDatabase,
  userId: number | null,
): Promise<EventCounts> {
  const since = new Date(Date.now() - 24 * 3600 * 1000).toISOString();
  const row = await db.getFirstAsync<EventCounts>(
    `SELECT
       COALESCE(SUM(CASE WHEN user_id IS ? AND status IN ('pending', 'syncing') THEN 1 ELSE 0 END), 0)
         AS unsynced,
       COALESCE(SUM(CASE WHEN user_id IS ? AND status = 'rejected' AND updated_at > ? THEN 1 ELSE 0 END), 0)
         AS recentlyRejected,
       COALESCE(SUM(CASE WHEN user_id IS NOT ? AND status IN ('pending', 'syncing') THEN 1 ELSE 0 END), 0)
         AS otherAccounts
     FROM pending_events`,
    userId,
    userId,
    since,
    userId,
  );
  return row ?? { unsynced: 0, recentlyRejected: 0, otherAccounts: 0 };
}

export async function markEventsSyncing(db: SQLiteDatabase, ids: string[]): Promise<void> {
  if (ids.length === 0) return;
  await db.runAsync(
    `UPDATE pending_events SET status = 'syncing', updated_at = ?
      WHERE id IN (${ids.map(() => '?').join(', ')})`,
    now(),
    ...ids,
  );
}

/** The server stored the event (including replays of an earlier upload). */
export async function markEventSynced(
  db: SQLiteDatabase,
  id: string,
  outcome?: EventOutcome,
): Promise<void> {
  await db.runAsync(
    `UPDATE pending_events SET status = 'synced', last_error = NULL, outcome = ?, updated_at = ?
      WHERE id = ?`,
    outcome ? JSON.stringify(outcome) : null,
    now(),
    id,
  );
}

/** Transient failure (offline, timeout, 5xx, expired session): retry later. */
export async function markEventForRetry(
  db: SQLiteDatabase,
  id: string,
  error: string,
): Promise<void> {
  await db.runAsync(
    `UPDATE pending_events
        SET status = 'pending', attempts = attempts + 1, last_error = ?, updated_at = ?
      WHERE id = ?`,
    error,
    now(),
    id,
  );
}

/** Returns reserved events to the queue without counting an attempt. */
export async function releaseEvents(db: SQLiteDatabase, ids: string[]): Promise<void> {
  if (ids.length === 0) return;
  await db.runAsync(
    `UPDATE pending_events SET status = 'pending', updated_at = ?
      WHERE status = 'syncing' AND id IN (${ids.map(() => '?').join(', ')})`,
    now(),
    ...ids,
  );
}

/** Permanent failure. The event is kept (never deleted) so it can be shown and reviewed. */
export async function markEventRejected(
  db: SQLiteDatabase,
  id: string,
  error: string,
  outcome?: EventOutcome,
): Promise<void> {
  await db.runAsync(
    `UPDATE pending_events SET status = 'rejected', last_error = ?, outcome = ?, updated_at = ?
      WHERE id = ?`,
    error,
    outcome ? JSON.stringify(outcome) : null,
    now(),
    id,
  );
}

export async function resetInterruptedSyncs(db: SQLiteDatabase): Promise<void> {
  await db.runAsync(
    `UPDATE pending_events SET status = 'pending', updated_at = ? WHERE status = 'syncing'`,
    now(),
  );
}
