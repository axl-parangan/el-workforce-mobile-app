import type { Migration } from '.';

/**
 * The outbox: actions recorded on the device that still need to reach the
 * server. The payload is opaque JSON so this table does not depend on the
 * (not yet finalised) server schema.
 *
 * Status lifecycle:
 *   pending -> syncing -> synced
 *                     \-> pending  (transient failure; attempts + 1)
 *                     \-> rejected (server refused permanently; kept for review)
 */
export const migration001PendingEvents: Migration = {
  version: 1,
  name: 'create pending_events',
  async up(db) {
    await db.execAsync(`
      CREATE TABLE pending_events (
        id TEXT PRIMARY KEY NOT NULL,
        type TEXT NOT NULL,
        payload TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending'
          CHECK (status IN ('pending', 'syncing', 'synced', 'rejected')),
        attempts INTEGER NOT NULL DEFAULT 0,
        last_error TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );
      CREATE INDEX idx_pending_events_status_created
        ON pending_events (status, created_at);
    `);
  },
};
