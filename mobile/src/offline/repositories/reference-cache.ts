import type { SQLiteDatabase } from 'expo-sqlite';

export type Snapshot = { payload: unknown; fetchedAt: string };

/** Keys of cached reference data. Per-job keys use the job id. */
export const CacheKeys = {
  myAssignments: 'assignments.mine',
  assignedJobs: 'jobs.assigned',
  attendanceStatus: 'timekeeping.status',
  crew: (jobId: number) => `crew.${jobId}`,
  job: (jobId: number) => `job.${jobId}`,
} as const;

export async function readSnapshot(
  db: SQLiteDatabase,
  userId: number,
  key: string,
): Promise<Snapshot | null> {
  const row = await db.getFirstAsync<{ payload: string; fetched_at: string }>(
    'SELECT payload, fetched_at FROM reference_cache WHERE user_id = ? AND key = ?',
    userId,
    key,
  );
  if (!row) return null;
  return { payload: JSON.parse(row.payload) as unknown, fetchedAt: row.fetched_at };
}

export async function writeSnapshot(
  db: SQLiteDatabase,
  userId: number,
  key: string,
  payload: unknown,
  fetchedAt: string = new Date().toISOString(),
): Promise<void> {
  await db.runAsync(
    `INSERT INTO reference_cache (user_id, key, payload, fetched_at) VALUES (?, ?, ?, ?)
     ON CONFLICT (user_id, key) DO UPDATE SET payload = excluded.payload, fetched_at = excluded.fetched_at`,
    userId,
    key,
    JSON.stringify(payload),
    fetchedAt,
  );
}

/**
 * Removes every cached snapshot (on sign-out). Reference data is re-fetched on
 * the next sign-in. This never touches `pending_events`.
 */
export async function clearReferenceCache(db: SQLiteDatabase): Promise<void> {
  await db.runAsync('DELETE FROM reference_cache');
}
