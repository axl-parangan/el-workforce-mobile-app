/**
 * End-to-end check of the app's sync code against a running backend: the real
 * outbox (SQLite), the real runner, the real wire format and response schema.
 *
 * Skipped unless LIVE_API_URL is set, e.g.
 *   LIVE_API_URL=http://localhost:8000/api/v1 npx jest live-backend
 * Uses the development database's demo accounts (see docs/development/mobile-qa-checklist.md).
 */
import { ApiError } from '@/api/errors';
import { recordPunches } from '@/features/timekeeping/punch-service';
import { batchResultSchema, syncResponseSchema } from '@/features/timekeeping/schemas';
import { toSyncEvent, type PunchPayload } from '@/features/timekeeping/punch-events';
import { get, live, request, signIn, type Account } from '@/test-utils/live-api';
import { openTestDatabase, type TestDatabase } from '@/test-utils/node-sqlite';

import { runMigrations } from '../migrations';
import {
  enqueuePendingEvents,
  getEventCounts,
  listPendingEvents,
  markEventForRetry,
  markEventRejected,
  markEventsSyncing,
  markEventSynced,
  releaseEvents,
} from '../queue/pending-events';
import { runSync, type SyncDeps } from './sync-runner';

function uuid(): string {
  return 'xxxxxxxx-xxxx-4xxx-8xxx-xxxxxxxxxxxx'.replace(/x/g, () =>
    Math.floor(Math.random() * 16).toString(16),
  );
}

/** A random past work date, so repeated runs don't overlap earlier sessions. */
function randomPastDate(): string {
  const day = new Date(Date.UTC(2024, 0, 1) + Math.floor(Math.random() * 600) * 86400000);
  return day.toISOString().slice(0, 10);
}

live('sync against the live backend', () => {
  let db: TestDatabase;
  let owner: Account | null;
  let worker: Account;
  let lead: Account;
  let jobId: number;

  beforeAll(async () => {
    worker = await signIn('demo.worker@example.com', 'Demo-worker-2026');
    lead = await signIn('demo.lead@example.com', 'Demo-lead-2026');
    const mine = await get(worker, '/assignments/mine/');
    jobId = mine.results[0].job.id;
  });

  beforeEach(async () => {
    db = openTestDatabase();
    await runMigrations(db);
    owner = null;
  });
  afterEach(() => db?.close());

  function deps(): SyncDeps {
    return {
      getOwner: () => owner?.userId ?? null,
      listPending: (userId, limit) => listPendingEvents(db, userId, limit),
      markSyncing: (ids) => markEventsSyncing(db, ids),
      markSynced: (id, outcome) => markEventSynced(db, id, outcome),
      markRejected: (id, error, outcome) => markEventRejected(db, id, error, outcome),
      markRetry: (id, error) => markEventForRetry(db, id, error),
      // Always the token of whoever is signed in at that moment.
      upload: async (events) => {
        const response = await request('POST', '/timekeeping/sync/', {
          token: owner!.token,
          body: { events: events.map(toSyncEvent) },
        });
        expect(response.status).toBe(200);
        return syncResponseSchema.parse(response.json);
      },
    };
  }

  function punch(action: PunchPayload['action_type'], at: string): PunchPayload {
    return {
      event_id: uuid(),
      action_type: action,
      job_id: jobId,
      captured_at: at,
      location: null,
    };
  }

  async function queue(account: Account, ...payloads: PunchPayload[]) {
    await enqueuePendingEvents(
      db,
      account.userId,
      payloads.map((payload) => ({ type: 'punch', id: payload.event_id, payload })),
    );
  }

  async function sessionsOn(account: Account, date: string) {
    const body = await get(
      account,
      `/timekeeping/sessions/?work_date_from=${date}&work_date_to=${date}&job_id=${jobId}`,
    );
    return body.results as {
      session_status: string;
      clock_in: { at: string; event_id: string } | null;
      clock_out: { at: string; event_id: string } | null;
    }[];
  }

  it('offline 08:00 clock-in and 17:00 clock-out sync once into one closed session', async () => {
    const date = randomPastDate();
    const clockIn = punch('clock_in', `${date}T08:00:00-05:00`);
    const clockOut = punch('clock_out', `${date}T17:00:00-05:00`);
    // Recorded offline, at the time they happened.
    await queue(worker, clockIn);
    await queue(worker, clockOut);

    // Reconnect: the worker is signed in.
    owner = worker;
    expect(await runSync(deps())).toMatchObject({ status: 'done', synced: 2, rejected: 0 });

    // A retry of the same events (as if the response had been lost) changes nothing.
    await db.runAsync(`UPDATE pending_events SET status = 'pending'`);
    expect(await runSync(deps())).toMatchObject({ synced: 2, rejected: 0 });

    const sessions = await sessionsOn(worker, date);
    expect(sessions).toHaveLength(1);
    expect(sessions[0]).toMatchObject({
      session_status: 'closed',
      clock_in: { event_id: clockIn.event_id },
      clock_out: { event_id: clockOut.event_id },
    });
    expect(Date.parse(sessions[0]!.clock_in!.at)).toBe(Date.parse(clockIn.captured_at));
    expect(Date.parse(sessions[0]!.clock_out!.at)).toBe(Date.parse(clockOut.captured_at));
  });

  it('keeps each account’s punches for that account on a shared phone', async () => {
    const date = randomPastDate();
    // The worker punches offline, signs out; the LeadHand signs in on the same phone.
    await queue(worker, punch('clock_in', `${date}T07:00:00-05:00`));
    await queue(worker, punch('clock_out', `${date}T11:00:00-05:00`));
    await queue(lead, punch('clock_in', `${date}T07:30:00-05:00`));
    await queue(lead, punch('clock_out', `${date}T11:30:00-05:00`));

    owner = lead;
    expect(await runSync(deps())).toMatchObject({ synced: 2 });
    expect(await sessionsOn(lead, date)).toHaveLength(1);
    // The worker's punches were not sent with the LeadHand's token.
    expect(await sessionsOn(worker, date)).toHaveLength(0);
    expect(await getEventCounts(db, lead.userId)).toMatchObject({ unsynced: 0, otherAccounts: 2 });

    // The worker signs back in: their punches go up under their own account.
    owner = worker;
    expect(await runSync(deps())).toMatchObject({ synced: 2 });
    expect(await sessionsOn(worker, date)).toHaveLength(1);
    expect(await getEventCounts(db, worker.userId)).toMatchObject({
      unsynced: 0,
      otherAccounts: 0,
    });
  });

  it('online punches: accepted, replayed, rejected with details, and a same-instant switch', async () => {
    const date = randomPastDate();
    const submit = async (payload: PunchPayload) => {
      const action = payload.action_type === 'clock_in' ? 'clock-in' : 'clock-out';
      const { action_type: _a, ...body } = toSyncEvent(payload);
      const response = await request('POST', `/timekeeping/${action}/`, {
        token: worker.token,
        body,
      });
      if (response.status !== 201) {
        const { code, message, details } = response.json.error;
        throw new ApiError(response.status, code, message, details);
      }
      return batchResultSchema.parse(response.json);
    };
    const punchDeps = {
      countUnsynced: async (userId: number) => (await getEventCounts(db, userId)).unsynced,
      enqueue: (
        userId: number,
        events: Parameters<typeof enqueuePendingEvents>[2],
        status: 'pending' | 'syncing',
      ) => enqueuePendingEvents(db, userId, events, { status }),
      submit,
      markSynced: (id: string, outcome: Parameters<typeof markEventSynced>[2]) =>
        markEventSynced(db, id, outcome),
      markRejected: (
        id: string,
        error: string,
        outcome?: Parameters<typeof markEventRejected>[3],
      ) => markEventRejected(db, id, error, outcome),
      markRetry: (id: string, error: string) => markEventForRetry(db, id, error),
      release: (ids: string[]) => releaseEvents(db, ids),
      requestSync: () => undefined,
    };

    const clockIn = punch('clock_in', `${date}T08:00:00-05:00`);
    expect(await recordPunches(punchDeps, worker.userId, [clockIn])).toMatchObject([
      { kind: 'accepted' },
    ]);
    // Replaying the same event id online is idempotent.
    const replay = await submit(clockIn);
    expect(replay.replayed).toBe(true);

    // A second clock-in is refused; the stored result arrives in details.result.
    const second = await recordPunches(punchDeps, worker.userId, [
      punch('clock_in', `${date}T09:00:00-05:00`),
    ]);
    expect(second).toMatchObject([{ kind: 'rejected', code: 'already_clocked_in' }]);
    expect(second[0]!.kind === 'rejected' && second[0]!.result?.event_id).toBe(
      second[0]!.payload.event_id,
    );

    // Out and back in at one instant (the server processes the clock-out first).
    const switched = await recordPunches(punchDeps, worker.userId, [
      punch('clock_out', `${date}T12:00:00-05:00`),
      punch('clock_in', `${date}T12:00:00-05:00`),
    ]);
    expect(switched.map((o) => o.kind)).toEqual(['accepted', 'accepted']);
    await recordPunches(punchDeps, worker.userId, [punch('clock_out', `${date}T16:00:00-05:00`)]);

    const sessions = await sessionsOn(worker, date);
    expect(sessions.map((s) => s.session_status)).toEqual(['closed', 'closed']);
  });
});
