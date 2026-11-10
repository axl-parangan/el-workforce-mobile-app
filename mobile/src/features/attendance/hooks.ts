import { useQuery } from '@tanstack/react-query';

import {
  getStaffSession,
  listRejectedEvents,
  listStaffSessions,
  type StaffListKind,
} from '@/features/timekeeping/api';

export const staffKeys = {
  list: (kind: string, jobId?: number) => ['timekeeping', 'staff', kind, jobId ?? null] as const,
  session: (id: number) => ['timekeeping', 'staff', 'session', id] as const,
};

/** Staff attendance lists are online-only: they are for review, not for punching. */
export function useStaffSessions(kind: StaffListKind, jobId?: number, enabled = true) {
  return useQuery({
    queryKey: staffKeys.list(kind, jobId),
    queryFn: () => listStaffSessions(kind, { job_id: jobId }),
    enabled,
  });
}

export function useRejectedEvents(jobId?: number, enabled = true) {
  return useQuery({
    queryKey: staffKeys.list('rejected', jobId),
    queryFn: () => listRejectedEvents({ job_id: jobId }),
    enabled,
  });
}

export function useStaffSession(id: number) {
  return useQuery({
    queryKey: staffKeys.session(id),
    queryFn: () => getStaffSession(id),
    enabled: Number.isInteger(id),
  });
}
