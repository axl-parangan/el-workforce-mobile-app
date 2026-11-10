import { useQueryClient } from '@tanstack/react-query';
import { useSQLiteContext } from 'expo-sqlite';
import { useCallback, useMemo } from 'react';

import { useAuth } from '@/features/auth/auth-provider';
import { UserFacingError } from '@/api/errors';
import { paginatedSchema } from '@/api/pagination';
import { newClientId } from '@/lib/ids';
import { useUnsettledEvents } from '@/offline/hooks';
import {
  enqueuePendingEvents,
  getEventCounts,
  markEventForRetry,
  markEventRejected,
  markEventSynced,
  releaseEvents,
} from '@/offline/queue/pending-events';
import { CacheKeys } from '@/offline/repositories/reference-cache';
import { outboxQueryKey, useSync } from '@/offline/sync/sync-provider';
import { getSessionOwner } from '@/offline/sync/sync-service';
import { useCachedQuery } from '@/offline/use-cached-query';

import { getAttendanceStatus, getCrew, getMySession, listMySessions, submitPunch } from './api';
import { deriveAttendance } from './attendance-state';
import type { PunchPayload } from './punch-events';
import { recordPunches } from './punch-service';
import { crewSchema, sessionSchema, statusSchema } from './schemas';

export const timekeepingKeys = {
  status: ['timekeeping', 'status'] as const,
  sessions: (page: number) => ['timekeeping', 'sessions', page] as const,
  session: (id: number) => ['timekeeping', 'session', id] as const,
  crew: (jobId: number) => ['timekeeping', 'crew', jobId] as const,
  staff: ['timekeeping', 'staff'] as const,
};

export function useAttendanceStatus() {
  const { user } = useAuth();
  return useCachedQuery({
    cacheKey: CacheKeys.attendanceStatus,
    queryKey: timekeepingKeys.status,
    fetcher: getAttendanceStatus,
    schema: statusSchema,
    enabled: Boolean(user?.employee),
  });
}

/** Server status plus this account's punches the server has not reflected yet. */
export function useAttendanceView() {
  const { user } = useAuth();
  const status = useAttendanceStatus();
  const fetchedAt = status.data?.fetchedAt ?? null;
  const events = useUnsettledEvents(fetchedAt);
  const view = useMemo(
    () =>
      deriveAttendance({
        status: status.data?.data ?? null,
        statusFetchedAt: fetchedAt,
        events: events.data ?? [],
        employeeId: user?.employee?.id ?? null,
      }),
    [status.data, fetchedAt, events.data, user?.employee?.id],
  );
  return { view, status, ready: status.isFetched && events.isFetched };
}

export function useMySessions(page: number) {
  return useCachedQuery({
    cacheKey: `sessions.page.${page}`,
    queryKey: timekeepingKeys.sessions(page),
    fetcher: () => listMySessions(page),
    schema: paginatedSchema(sessionSchema),
  });
}

export function useMySession(id: number) {
  return useCachedQuery({
    cacheKey: `session.${id}`,
    queryKey: timekeepingKeys.session(id),
    fetcher: () => getMySession(id),
    schema: sessionSchema,
    enabled: Number.isInteger(id),
  });
}

/** The crew roster of a job (LeadHand/Manager/Admin), cached for offline group punches. */
export function useCrew(jobId: number) {
  return useCachedQuery({
    cacheKey: CacheKeys.crew(jobId),
    queryKey: timekeepingKeys.crew(jobId),
    fetcher: () => getCrew(jobId),
    schema: crewSchema,
    enabled: Number.isInteger(jobId),
  });
}

export function newPunch(
  fields: Omit<PunchPayload, 'event_id'> & { event_id?: string },
): PunchPayload {
  return { ...fields, event_id: fields.event_id ?? newClientId() };
}

/** Records punches for the signed-in account (online first, outbox fallback). */
export function usePunch() {
  const db = useSQLiteContext();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { requestSync } = useSync();
  const userId = user?.id;

  return useCallback(
    async (payloads: PunchPayload[]) => {
      if (userId === undefined || getSessionOwner() !== userId) {
        throw new UserFacingError('Sign in again to record attendance.');
      }
      try {
        return await recordPunches(
          {
            countUnsynced: async (owner) => (await getEventCounts(db, owner)).unsynced,
            enqueue: (owner, events, status) => enqueuePendingEvents(db, owner, events, { status }),
            submit: submitPunch,
            markSynced: (id, outcome) => markEventSynced(db, id, outcome),
            markRejected: (id, error, outcome) => markEventRejected(db, id, error, outcome),
            markRetry: (id, error) => markEventForRetry(db, id, error),
            release: (ids) => releaseEvents(db, ids),
            requestSync: () => void requestSync(),
          },
          userId,
          payloads,
        );
      } finally {
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: outboxQueryKey }),
          queryClient.invalidateQueries({ queryKey: ['timekeeping'] }),
        ]);
      }
    },
    [db, queryClient, requestSync, userId],
  );
}
