import type { SQLiteDatabase } from 'expo-sqlite';

import { runMigrations } from '../migrations';
import { resetInterruptedSyncs } from '../queue/pending-events';

export const DATABASE_NAME = 'workforce.db';

/** Passed to <SQLiteProvider onInit>. Runs once per app launch before children render. */
export async function initializeDatabase(db: SQLiteDatabase): Promise<void> {
  await db.execAsync('PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON;');
  await runMigrations(db);
  // A sync interrupted by an app kill must be retried, not lost.
  await resetInterruptedSyncs(db);
}
