import type { SQLiteDatabase } from 'expo-sqlite';

import { syncPunches } from '@/features/timekeeping/api';

import {
  listPendingEvents,
  markEventForRetry,
  markEventRejected,
  markEventsSyncing,
  markEventSynced,
} from '../queue/pending-events';
import { createSyncController, runSync, type SyncReport } from './sync-runner';

/**
 * App-wide sync state. The auth layer sets the session owner (the signed-in
 * account's user id) and waits for `idle()` before tokens change, so a sync
 * started for one account can never continue with another account's token.
 */
let database: SQLiteDatabase | null = null;
let owner: number | null = null;
const listeners = new Set<(report: SyncReport) => void>();

export function setSyncDatabase(db: SQLiteDatabase | null): void {
  database = db;
}

export function setSessionOwner(userId: number | null): void {
  owner = userId;
}

export function getSessionOwner(): number | null {
  return owner;
}

const controller = createSyncController(async () => {
  const db = database;
  if (!db) return { status: 'skipped', synced: 0, rejected: 0, retrying: 0 };
  let report: SyncReport;
  try {
    report = await runSync({
      getOwner: getSessionOwner,
      listPending: (userId, limit) => listPendingEvents(db, userId, limit),
      markSyncing: (ids) => markEventsSyncing(db, ids),
      markSynced: (id, outcome) => markEventSynced(db, id, outcome),
      markRejected: (id, error, outcome) => markEventRejected(db, id, error, outcome),
      markRetry: (id, error) => markEventForRetry(db, id, error),
      upload: syncPunches,
    });
  } catch (error) {
    // Triggers are fire-and-forget; an unexpected failure (e.g. the database)
    // is reported, never thrown, and the events stay queued.
    report = { status: 'failed', synced: 0, rejected: 0, retrying: 0, error: String(error) };
  }
  listeners.forEach((listener) => listener(report));
  return report;
});

export const syncService = {
  request: controller.request,
  idle: controller.idle,
  isRunning: () => controller.running,
  subscribe(listener: (report: SyncReport) => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};
