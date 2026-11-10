import type { Migration } from '.';

/**
 * Ties every outbox event to the account that recorded it, so events are only
 * ever synced with that account's token.
 *
 * - `user_id`: the server user id of the signed-in account at enqueue time.
 *   Rows queued before this migration keep NULL. Their owner is unknown, so
 *   they are never synced automatically; they stay visible as "waiting for
 *   the original account" and are never deleted.
 * - `outcome`: a JSON summary of the server's answer (accepted or rejected
 *   employees, codes, messages), shown in history and pending-sync screens.
 *
 * Existing rows, ids, timestamps and statuses are preserved: this only adds
 * nullable columns. Queue order uses SQLite's `rowid`, which already reflects
 * insertion order for existing rows.
 */
export const migration002PendingEventOwner: Migration = {
  version: 2,
  name: 'add pending_events.user_id and outcome',
  async up(db) {
    await db.execAsync(`
      ALTER TABLE pending_events ADD COLUMN user_id INTEGER;
      ALTER TABLE pending_events ADD COLUMN outcome TEXT;
      CREATE INDEX idx_pending_events_user_status
        ON pending_events (user_id, status);
    `);
  },
};
