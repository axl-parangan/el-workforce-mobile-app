import type { PendingEvent } from '@/offline/queue/pending-events';

import { compareByProcessingOrder, punchPayloadSchema, type PunchPayload } from './punch-events';
import type { AttendanceStatus } from './schemas';

export type OpenSession = {
  jobId: number;
  since: string;
  /** Null while the clock-in exists only on this device. */
  sessionId: number | null;
};

export type AttendanceView = {
  open: OpenSession | null;
  /** True when the view depends on punches the server has not accepted yet. */
  provisional: boolean;
};

/**
 * What the employee should see: the last server status, plus their own
 * punches the server has not reflected yet. Those are events still in the
 * outbox, and events accepted after the status snapshot was taken (e.g. an
 * online punch followed by losing the connection). Refused punches are
 * ignored. The server remains authoritative; this is a display hint.
 */
export function deriveAttendance({
  status,
  statusFetchedAt,
  events,
  employeeId,
}: {
  status: AttendanceStatus | null;
  statusFetchedAt: string | null;
  /** The account's unsynced events and those settled after the snapshot. */
  events: PendingEvent[];
  employeeId: number | null;
}): AttendanceView {
  const session = status?.open_session;
  let open: OpenSession | null = session
    ? { jobId: session.job.id, since: session.clock_in?.at ?? '', sessionId: session.id }
    : null;
  let provisional = false;

  const relevant: { payload: PunchPayload; sequence: number; unsynced: boolean }[] = [];
  for (const event of events) {
    const parsed = punchPayloadSchema.safeParse(event.payload);
    if (!parsed.success) continue;
    const payload = parsed.data;
    const unsynced = event.status === 'pending' || event.status === 'syncing';

    if (payload.employee_ids !== undefined) {
      // A group punch counts only if it included this employee.
      if (employeeId === null || !payload.employee_ids.includes(employeeId)) continue;
    }
    if (!unsynced) {
      if (event.status !== 'synced') continue;
      if (statusFetchedAt && event.updatedAt <= statusFetchedAt) continue;
      const mine = event.outcome?.results?.find((r) => r.employeeId === employeeId);
      const accepted = mine ? mine.status === 'accepted' : event.outcome?.results === undefined;
      if (!accepted) continue;
    }
    relevant.push({ payload, sequence: event.sequence, unsynced });
  }

  for (const { payload, unsynced } of relevant.sort(compareByProcessingOrder)) {
    if (payload.action_type === 'clock_in') {
      open = { jobId: payload.job_id, since: payload.captured_at, sessionId: null };
    } else if (!open || open.jobId === payload.job_id) {
      open = null;
    }
    if (unsynced) provisional = true;
  }
  return { open, provisional };
}
