import type { z } from 'zod';

import { ApiError, NetworkError } from '@/api/errors';

import type { Snapshot } from './repositories/reference-cache';

/** Data from the server, or from the device cache when the server cannot be reached. */
export type Cached<T> = {
  data: T;
  /** When the server produced this data. */
  fetchedAt: string;
  fromCache: boolean;
};

/** Older than this, the UI warns that reference data may be out of date (M6). */
export const STALE_AFTER_MS = 24 * 3600 * 1000;

export function isStale(fetchedAt: string, now: number = Date.now()): boolean {
  return now - Date.parse(fetchedAt) > STALE_AFTER_MS;
}

/** Failures where showing the last known data beats showing an error. */
export function isUnreachable(error: unknown): boolean {
  return error instanceof NetworkError || (error instanceof ApiError && error.status >= 500);
}

/**
 * Fetches fresh data and stores a snapshot; when the server is unreachable,
 * returns the last snapshot instead. Other errors (403, 404, an expired
 * session) are real answers and are re-thrown, never masked by the cache.
 */
export async function cachedFetch<T>({
  fetcher,
  schema,
  read,
  write,
  now = () => new Date().toISOString(),
}: {
  fetcher: () => Promise<T>;
  schema: z.ZodType<T>;
  read: () => Promise<Snapshot | null>;
  write: (data: T, fetchedAt: string) => Promise<void>;
  now?: () => string;
}): Promise<Cached<T>> {
  try {
    const data = await fetcher();
    const fetchedAt = now();
    // A failed cache write must not hide fresh data.
    await write(data, fetchedAt).catch(() => undefined);
    return { data, fetchedAt, fromCache: false };
  } catch (error) {
    if (!isUnreachable(error)) throw error;
    const snapshot = await read();
    if (!snapshot) throw error;
    // A snapshot written by an older app version may no longer match.
    const parsed = schema.safeParse(snapshot.payload);
    if (!parsed.success) throw error;
    return { data: parsed.data, fetchedAt: snapshot.fetchedAt, fromCache: true };
  }
}
