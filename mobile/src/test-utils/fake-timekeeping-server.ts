/**
 * An in-memory model of the timekeeping API rules the app depends on
 * (docs/api/timekeeping.md): device-time ordering with clock-outs first on
 * ties (Q13), idempotent replay by event_id, conflicts across accounts, one
 * open session per employee, and per-employee results for group punches.
 */
import { ApiError, NetworkError } from '@/api/errors';
import { compareByProcessingOrder, type PunchPayload } from '@/features/timekeeping/punch-events';
import type { BatchResult, ItemResult, SyncResponse } from '@/features/timekeeping/schemas';

export type FakeSession = { employeeId: number; jobId: number; in: string; out: string | null };

type Stored = { userId: number; fingerprint: string; batch: BatchResult };

export function createFakeServer({
  employeeFor = (userId: number) => userId * 10,
  assigned = (_employeeId: number, _jobId: number) => true,
}: {
  employeeFor?: (userId: number) => number;
  assigned?: (employeeId: number, jobId: number) => boolean;
} = {}) {
  const sessions: FakeSession[] = [];
  const stored = new Map<string, Stored>();
  let nextId = 1;
  /** Requests received, with the account whose token was used. */
  const requests: { userId: number | null; eventIds: string[] }[] = [];
  let online = true;
  let loseNextResponse = false;

  function itemFor(employeeId: number, payload: PunchPayload): ItemResult {
    const base = {
      employee: { id: employeeId, name: `Employee ${employeeId}` },
      processed_at: payload.captured_at,
    };
    const reject = (code: string, message: string): ItemResult => ({
      ...base,
      status: 'rejected',
      code,
      message,
      session_id: null,
      punch_id: null,
    });
    const open = sessions.find((s) => s.employeeId === employeeId && s.out === null);
    if (payload.action_type === 'clock_in') {
      if (!assigned(employeeId, payload.job_id)) {
        return reject('no_active_assignment', 'No active assignment to this job.');
      }
      if (open) return reject('already_clocked_in', `Already clocked in to job ${open.jobId}.`);
      sessions.push({ employeeId, jobId: payload.job_id, in: payload.captured_at, out: null });
      return {
        ...base,
        status: 'accepted',
        code: 'clocked_in',
        message: 'Clocked in.',
        session_id: sessions.length,
        punch_id: nextId++,
      };
    }
    if (!open) return reject('no_open_session', 'No open session.');
    if (open.jobId !== payload.job_id) {
      return reject('open_session_on_other_job', 'The open session is on another job.');
    }
    open.out = payload.captured_at;
    return {
      ...base,
      status: 'accepted',
      code: 'clocked_out',
      message: 'Clocked out.',
      session_id: sessions.indexOf(open) + 1,
      punch_id: nextId++,
    };
  }

  function process(userId: number, payload: PunchPayload, source: string): BatchResult {
    const fingerprint = JSON.stringify({ ...payload, event_id: undefined });
    const existing = stored.get(payload.event_id);
    if (existing) {
      if (existing.userId !== userId || existing.fingerprint !== fingerprint) {
        throw new ApiError(409, 'idempotency_key_conflict', 'Event id already used.');
      }
      return { ...existing.batch, replayed: true };
    }
    const employees = payload.employee_ids ?? [employeeFor(userId)];
    const batch: BatchResult = {
      event_id: payload.event_id,
      batch_id: nextId++,
      action_type: payload.action_type,
      source,
      job: { id: payload.job_id, job_number: `J-${payload.job_id}`, name: `Job ${payload.job_id}` },
      performed_by: { id: userId, email: `user${userId}@example.com` },
      captured_at: payload.captured_at,
      received_at: payload.captured_at,
      entry_reason: payload.reason ?? '',
      location: {
        status: 'location_unavailable',
        flags: [],
        requires_review: false,
        latitude: null,
        longitude: null,
        accuracy_meters: null,
        distance_meters: null,
      },
      results: employees.map((employeeId) => itemFor(employeeId, payload)),
      replayed: false,
    };
    stored.set(payload.event_id, { userId, fingerprint, batch });
    return batch;
  }

  function finishRequest() {
    if (loseNextResponse) {
      loseNextResponse = false;
      throw new NetworkError('Connection dropped before the response arrived');
    }
  }

  return {
    sessions,
    requests,
    setOnline(value: boolean) {
      online = value;
    },
    /** The server stores the events, but the device never sees the response. */
    dropNextResponse() {
      loseNextResponse = true;
    },
    /** `POST /timekeeping/sync/` made with `userId`'s token. */
    async sync(userId: number | null, payloads: PunchPayload[]): Promise<SyncResponse> {
      requests.push({ userId, eventIds: payloads.map((p) => p.event_id) });
      if (!online) throw new NetworkError();
      if (userId === null) throw new ApiError(401, 'not_authenticated', 'Not authenticated.');
      const order = payloads
        .map((payload, sequence) => ({ payload, sequence }))
        .sort(compareByProcessingOrder);
      const results = new Map<string, SyncResponse['results'][number]>();
      for (const { payload } of order) {
        try {
          results.set(payload.event_id, {
            event_id: payload.event_id,
            status: 'processed',
            batch: process(userId, payload, 'mobile_offline_sync'),
          });
        } catch (error) {
          const e = error as ApiError;
          results.set(payload.event_id, {
            event_id: payload.event_id,
            status: 'error',
            error: { code: e.code, message: e.message },
          });
        }
      }
      finishRequest();
      return { results: payloads.map((p) => results.get(p.event_id)!) };
    },
    /** Individual or group punch endpoint, made with `userId`'s token. */
    async submit(userId: number, payload: PunchPayload): Promise<BatchResult> {
      requests.push({ userId, eventIds: [payload.event_id] });
      if (!online) throw new NetworkError();
      const batch = process(userId, payload, 'mobile_online');
      finishRequest();
      const rejected = batch.results.find((r) => r.status === 'rejected');
      if (payload.employee_ids === undefined && rejected) {
        const status = rejected.code === 'no_active_assignment' ? 403 : 409;
        throw new ApiError(status, rejected.code, rejected.message, { result: batch });
      }
      return batch;
    },
  };
}

export type FakeServer = ReturnType<typeof createFakeServer>;
