/**
 * A tiny expo-sqlite stand-in backed by Node's built-in SQLite, so tests run
 * the real SQL (migrations, outbox queries) instead of mocks. It implements
 * only the async methods this app uses.
 */
import type { SQLiteDatabase } from 'expo-sqlite';

// eslint-disable-next-line @typescript-eslint/no-require-imports
const { DatabaseSync } = require('node:sqlite') as {
  DatabaseSync: new (path: string) => NodeDatabase;
};

type NodeStatement = {
  run: (...params: unknown[]) => { changes: number; lastInsertRowid: number | bigint };
  all: (...params: unknown[]) => unknown[];
  get: (...params: unknown[]) => unknown;
};
type NodeDatabase = {
  exec: (sql: string) => void;
  prepare: (sql: string) => NodeStatement;
  close: () => void;
};

function bind(params: unknown[]): unknown[] {
  const flat = params.length === 1 && Array.isArray(params[0]) ? params[0] : params;
  return flat.map((value) => (typeof value === 'boolean' ? Number(value) : value));
}

function plain<T>(row: unknown): T {
  return row === undefined ? (null as T) : ({ ...(row as object) } as T);
}

export type TestDatabase = SQLiteDatabase & { close: () => void };

export function openTestDatabase(): TestDatabase {
  const db = new DatabaseSync(':memory:');

  const api = {
    async execAsync(sql: string) {
      db.exec(sql);
    },
    async runAsync(sql: string, ...params: unknown[]) {
      const result = db.prepare(sql).run(...bind(params));
      return { changes: result.changes, lastInsertRowId: Number(result.lastInsertRowid) };
    },
    async getAllAsync<T>(sql: string, ...params: unknown[]) {
      return db
        .prepare(sql)
        .all(...bind(params))
        .map((row) => plain<T>(row));
    },
    async getFirstAsync<T>(sql: string, ...params: unknown[]) {
      return plain<T | null>(db.prepare(sql).get(...bind(params)));
    },
    // BEGIN/COMMIT like expo-sqlite, so an accidentally nested transaction fails here too.
    async withTransactionAsync(task: () => Promise<void>) {
      db.exec('BEGIN');
      try {
        await task();
        db.exec('COMMIT');
      } catch (error) {
        db.exec('ROLLBACK');
        throw error;
      }
    },
    close() {
      db.close();
    },
  };
  return api as unknown as TestDatabase;
}
