import type { Migration } from '.';

/**
 * Last-known server data the app needs offline (assigned jobs, active
 * assignments, attendance status, LeadHand crew rosters). Stored as JSON
 * snapshots per account so one user never sees another user's cached data.
 *
 * Snapshots are disposable: they are cleared on sign-out and re-fetched
 * whenever the server is reachable. The server stays authoritative.
 */
export const migration003ReferenceCache: Migration = {
  version: 3,
  name: 'create reference_cache',
  async up(db) {
    await db.execAsync(`
      CREATE TABLE reference_cache (
        user_id INTEGER NOT NULL,
        key TEXT NOT NULL,
        payload TEXT NOT NULL,
        fetched_at TEXT NOT NULL,
        PRIMARY KEY (user_id, key)
      );
    `);
  },
};
