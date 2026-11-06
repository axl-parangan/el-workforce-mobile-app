import type { SQLiteDatabase } from 'expo-sqlite';

import { newClientId } from '@/lib/ids';

/** Extend as offline-capable actions are introduced (e.g. 'punch'). */
export type PendingEventType = 'punch';

export type PendingEventStatus = 'pending' | 'syncing' | 'synced' | 'rejected';

export type PendingEvent = {
  /** Client-generated UUID. Sent to the server as the idempotency key. */
  id: string;
  type: PendingEventType;
  payload: unknown;
  status: PendingEventStatus;
  attempts: number;
  lastError: string | null;
  createdAt: string;
  updatedAt: string;
};

type PendingEventRow = {
  id: string;
  type: PendingEventType;
  payload: string;
  status: PendingEventStatus;
  attempts: number;
  last_error: string | null;
  created_at: string;
  updated_at: string;
};

function fromRow(row: PendingEventRow): PendingEvent {
  return {
    id: row.id,
    type: row.type,
    payload: JSON.parse(row.payload) as unknown,
    status: row.status,
    attempts: row.attempts,
    lastError: row.last_error,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

/**
 * Persists an event to the outbox. Call this inside the same transaction as
 * any local state change it represents so the two can never diverge.
 */
export async function enqueuePendingEvent(
  db: SQLiteDatabase,
  event: { type: PendingEventType; payload: unknown; id?: string },
): Promise<string> {
  const id = event.id ?? newClientId();
  const now = new Date().toISOString();
  await db.runAsync(
    `INSERT INTO pending_events (id, type, payload, status, attempts, created_at, updated_at)
     VALUES (?, ?, ?, 'pending', 0, ?, ?)`,
    id,
    event.type,
    JSON.stringify(event.payload),
    now,
    now,
  );
  return id;
}

/** Oldest first, so events reach the server in the order they happened. */
export async function listPendingEvents(db: SQLiteDatabase, limit = 50): Promise<PendingEvent[]> {
  const rows = await db.getAllAsync<PendingEventRow>(
    `SELECT * FROM pending_events WHERE status = 'pending' ORDER BY created_at, id LIMIT ?`,
    limit,
  );
  return rows.map(fromRow);
}

export async function countUnsyncedEvents(db: SQLiteDatabase): Promise<number> {
  const row = await db.getFirstAsync<{ count: number }>(
    `SELECT COUNT(*) AS count FROM pending_events WHERE status IN ('pending', 'syncing')`,
  );
  return row?.count ?? 0;
}

export async function markEventSyncing(db: SQLiteDatabase, id: string): Promise<void> {
  await db.runAsync(
    `UPDATE pending_events SET status = 'syncing', updated_at = ? WHERE id = ?`,
    new Date().toISOString(),
    id,
  );
}

/** The server accepted the event (including "already received" duplicates). */
export async function markEventSynced(db: SQLiteDatabase, id: string): Promise<void> {
  await db.runAsync(
    `UPDATE pending_events SET status = 'synced', last_error = NULL, updated_at = ? WHERE id = ?`,
    new Date().toISOString(),
    id,
  );
}

/** Transient failure (offline, timeout, 5xx): keep it queued for the next attempt. */
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
    new Date().toISOString(),
    id,
  );
}

/** Permanent failure. The event is kept (never deleted) so it can be shown and reviewed. */
export async function markEventRejected(
  db: SQLiteDatabase,
  id: string,
  error: string,
): Promise<void> {
  await db.runAsync(
    `UPDATE pending_events SET status = 'rejected', last_error = ?, updated_at = ? WHERE id = ?`,
    error,
    new Date().toISOString(),
    id,
  );
}

export async function resetInterruptedSyncs(db: SQLiteDatabase): Promise<void> {
  await db.runAsync(
    `UPDATE pending_events SET status = 'pending', updated_at = ? WHERE status = 'syncing'`,
    new Date().toISOString(),
  );
}
