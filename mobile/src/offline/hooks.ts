import { useQuery } from '@tanstack/react-query';
import { useSQLiteContext } from 'expo-sqlite';

import { useAuth } from '@/features/auth/auth-provider';

import {
  getEventCounts,
  listEventsSettledSince,
  listRecentEvents,
  listUnsyncedEvents,
} from './queue/pending-events';
import { outboxQueryKey } from './sync/sync-provider';

/** Local reads never wait for the network. */
const local = { networkMode: 'always', staleTime: 0 } as const;

/** Waiting, recently rejected, and other accounts' events. Works signed out too. */
export function useOutboxCounts() {
  const db = useSQLiteContext();
  const { user } = useAuth();
  const userId = user?.id ?? null;
  return useQuery({
    ...local,
    queryKey: [...outboxQueryKey, 'counts', userId],
    queryFn: () => getEventCounts(db, userId),
  });
}

/** The account's unsynced events plus those settled after `since`, oldest first. */
export function useUnsettledEvents(since: string | null) {
  const db = useSQLiteContext();
  const { user } = useAuth();
  const userId = user?.id;
  return useQuery({
    ...local,
    queryKey: [...outboxQueryKey, 'unsettled', userId, since],
    enabled: userId !== undefined,
    queryFn: async () => {
      const [unsynced, settled] = await Promise.all([
        listUnsyncedEvents(db, userId!),
        since ? listEventsSettledSince(db, userId!, since) : Promise.resolve([]),
      ]);
      return [...settled, ...unsynced].sort((a, b) => a.sequence - b.sequence);
    },
  });
}

/** The account's recent device activity, newest first. */
export function useRecentEvents() {
  const db = useSQLiteContext();
  const { user } = useAuth();
  const userId = user?.id;
  return useQuery({
    ...local,
    queryKey: [...outboxQueryKey, 'recent', userId],
    enabled: userId !== undefined,
    queryFn: () => listRecentEvents(db, userId!),
  });
}
