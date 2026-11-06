import type { SQLiteDatabase } from 'expo-sqlite';

import { migration001PendingEvents } from './001-pending-events';

export type Migration = {
  /** Strictly increasing. Stored in `PRAGMA user_version`. */
  version: number;
  name: string;
  up: (db: SQLiteDatabase) => Promise<void>;
};

/**
 * Append-only list. Never edit a migration that has shipped; add a new one.
 */
export const MIGRATIONS: readonly Migration[] = [migration001PendingEvents];

export async function runMigrations(db: SQLiteDatabase): Promise<void> {
  const row = await db.getFirstAsync<{ user_version: number }>('PRAGMA user_version');
  let currentVersion = row?.user_version ?? 0;

  for (const migration of MIGRATIONS) {
    if (migration.version <= currentVersion) continue;
    if (migration.version !== currentVersion + 1) {
      throw new Error(`Local migration ${migration.version} (${migration.name}) is out of order`);
    }
    await db.withTransactionAsync(async () => {
      await migration.up(db);
      // PRAGMA does not accept bound parameters; version is a trusted integer.
      await db.execAsync(`PRAGMA user_version = ${migration.version}`);
    });
    currentVersion = migration.version;
  }
}
