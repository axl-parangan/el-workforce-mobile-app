import { useQuery } from '@tanstack/react-query';
import { useSQLiteContext } from 'expo-sqlite';
import type { z } from 'zod';

import { useAuth } from '@/features/auth/auth-provider';

import { cachedFetch } from './cached-fetch';
import { readSnapshot, writeSnapshot } from './repositories/reference-cache';

/**
 * A query whose last result is kept on the device for the signed-in account,
 * so screens keep working offline. It runs even while offline (networkMode
 * 'always') so it can fall back to the snapshot.
 */
export function useCachedQuery<T>({
  cacheKey,
  queryKey,
  fetcher,
  schema,
  enabled = true,
}: {
  cacheKey: string;
  queryKey: readonly unknown[];
  fetcher: () => Promise<T>;
  schema: z.ZodType<T>;
  enabled?: boolean;
}) {
  const db = useSQLiteContext();
  const { user } = useAuth();
  const userId = user?.id;

  return useQuery({
    queryKey: [...queryKey, { userId }],
    enabled: enabled && userId !== undefined,
    networkMode: 'always',
    queryFn: () =>
      cachedFetch({
        fetcher,
        schema,
        read: () => readSnapshot(db, userId!, cacheKey),
        write: (data, fetchedAt) => writeSnapshot(db, userId!, cacheKey, data, fetchedAt),
      }),
  });
}
