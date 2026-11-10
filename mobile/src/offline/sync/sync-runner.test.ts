import type { PunchPayload } from '@/features/timekeeping/punch-events';
import { createFakeServer, type FakeServer } from '@/test-utils/fake-timekeeping-server';
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
} from '../queue/pending-events';
import { createSyncController, runSync, type SyncDeps } from './sync-runner';

let db: TestDatabase;
let server: FakeServer;
let owner: number | null;
let counter = 0;

beforeEach(async () => {
  db = openTestDatabase();
  await runMigrations(db);
  server = createFakeServer();
  owner = null;
});
afterEach(() => db.close());

function deps(overrides: Partial<SyncDeps> = {}): SyncDeps {
  return {
    getOwner: () => owner,
    listPending: (userId, limit) => listPendingEvents(db, userId, limit),
    markSyncing: (ids) => markEventsSyncing(db, ids),
    markSynced: (id, outcome) => markEventSynced(db, id, outcome),
    markRejected: (id, error, outcome) => markEventRejected(db, id, error, outcome),
    markRetry: (id, error) => markEventForRetry(db, id, error),
    // The request always carries the token of whoever is signed in right now.
    upload: (events) => server.sync(owner, events),
    ...overrides,
  };
}

function punch(action: PunchPayload['action_type'], at: string, jobId = 1): PunchPayload {
  counter += 1;
  return {
    event_id: `00000000-0000-4000-8000-${String(counter).padStart(12, '0')}`,
    action_type: action,
    job_id: jobId,
    captured_at: at,
    location: null,
  };
}

async function queue(userId: number, ...payloads: PunchPayload[]) {
  await enqueuePendingEvents(
    db,
    userId,
    payloads.map((payload) => ({ type: 'punch', id: payload.event_id, payload })),
  );
}

async function statuses() {
  return db.getAllAsync<{ id: string; status: string; user_id: number }>(
    'SELECT id, status, user_id FROM pending_events ORDER BY rowid',
  );
}

describe('offline workday', () => {
  it('syncs an offline 08:00 clock-in and 17:00 clock-out exactly once into one closed session', async () => {
    owner = 1;
    // Captured offline, queued separately at the times they happened.
    await queue(1, punch('clock_in', '2026-03-10T08:00:00-04:00'));
    await queue(1, punch('clock_out', '2026-03-10T17:00:00-04:00'));

    // Reconnect at 18:00.
    const report = await runSync(deps());
    expect(report).toMatchObject({ status: 'done', synced: 2, rejected: 0, retrying: 0 });
    expect(server.sessions).toEqual([
      {
        employeeId: 10,
        jobId: 1,
        in: '2026-03-10T08:00:00-04:00',
        out: '2026-03-10T17:00:00-04:00',
      },
    ]);
    expect((await statuses()).map((s) => s.status)).toEqual(['synced', 'synced']);

    // Later triggers have nothing to send.
    await runSync(deps());
    expect(server.requests).toHaveLength(1);
  });

  it('never duplicates when the response is lost after the server stored the events', async () => {
    owner = 1;
    const clockIn = punch('clock_in', '2026-03-10T08:00:00-04:00');
    const clockOut = punch('clock_out', '2026-03-10T17:00:00-04:00');
    await queue(1, clockIn, clockOut);

    server.dropNextResponse();
    const first = await runSync(deps());
    expect(first).toMatchObject({ status: 'failed', retrying: 2 });
    expect((await statuses()).map((s) => s.status)).toEqual(['pending', 'pending']);

    const second = await runSync(deps());
    expect(second).toMatchObject({ status: 'done', synced: 2 });
    // Same event ids both times; the server replayed instead of re-processing.
    expect(server.requests.map((r) => r.eventIds)).toEqual([
      [clockIn.event_id, clockOut.event_id],
      [clockIn.event_id, clockOut.event_id],
    ]);
    expect(server.sessions).toHaveLength(1);
  });

  it('keeps everything queued while offline and retries on the next trigger', async () => {
    owner = 1;
    await queue(1, punch('clock_in', '2026-03-10T08:00:00-04:00'));
    server.setOnline(false);
    expect(await runSync(deps())).toMatchObject({ status: 'failed', retrying: 1 });
    const [event] = await listPendingEvents(db, 1);
    expect(event).toMatchObject({ attempts: 1, status: 'pending' });

    server.setOnline(true);
    expect(await runSync(deps())).toMatchObject({ synced: 1 });
  });
});

describe('job switching', () => {
  it('handles a clock-out and clock-in recorded at the same instant', async () => {
    owner = 1;
    await queue(1, punch('clock_in', '2026-03-10T07:00:00-04:00', 1));
    // Switch to job 2 at 10:30: clock-out queued first, same captured_at.
    await queue(
      1,
      punch('clock_out', '2026-03-10T10:30:00-04:00', 1),
      punch('clock_in', '2026-03-10T10:30:00-04:00', 2),
    );
    await queue(1, punch('clock_out', '2026-03-10T17:00:00-04:00', 2));
    // Back to job 1 later the same day.
    await queue(1, punch('clock_in', '2026-03-10T17:30:00-04:00', 1));

    expect(await runSync(deps())).toMatchObject({ synced: 5, rejected: 0 });
    expect(server.sessions).toEqual([
      {
        employeeId: 10,
        jobId: 1,
        in: '2026-03-10T07:00:00-04:00',
        out: '2026-03-10T10:30:00-04:00',
      },
      {
        employeeId: 10,
        jobId: 2,
        in: '2026-03-10T10:30:00-04:00',
        out: '2026-03-10T17:00:00-04:00',
      },
      { employeeId: 10, jobId: 1, in: '2026-03-10T17:30:00-04:00', out: null },
    ]);
  });
});

describe('account ownership', () => {
  it('never sends one account’s events with another account’s token', async () => {
    await queue(1, punch('clock_in', '2026-03-10T08:00:00-04:00'));
    const otherUsersEvent = punch('clock_in', '2026-03-10T08:05:00-04:00');
    await queue(2, otherUsersEvent);

    owner = 2; // user 2 signs in on the same phone
    expect(await runSync(deps())).toMatchObject({ synced: 1 });
    expect(server.requests).toEqual([{ userId: 2, eventIds: [otherUsersEvent.event_id] }]);
    // User 1's punch is untouched and still waiting.
    expect(await getEventCounts(db, 2)).toMatchObject({ unsynced: 0, otherAccounts: 1 });

    owner = 1; // the original account signs back in
    expect(await runSync(deps())).toMatchObject({ synced: 1 });
    expect(server.requests[1]!.userId).toBe(1);
    expect(server.sessions.map((s) => s.employeeId).sort()).toEqual([10, 20]);
  });

  it('does nothing while signed out', async () => {
    await queue(1, punch('clock_in', '2026-03-10T08:00:00-04:00'));
    expect(await runSync(deps())).toMatchObject({ status: 'skipped' });
    expect(server.requests).toEqual([]);
  });

  it('stops before the next batch if the account changes mid-sync', async () => {
    owner = 1;
    for (let i = 0; i < 150; i += 1) {
      await queue(
        1,
        punch(i % 2 ? 'clock_out' : 'clock_in', new Date(Date.UTC(2026, 2, 1, 0, i)).toISOString()),
      );
    }
    const report = await runSync(
      deps({
        upload: async (events) => {
          const response = await server.sync(owner, events);
          owner = 2; // sign-out and another sign-in while the first batch was in flight
          return response;
        },
      }),
    );
    expect(report.synced).toBe(100);
    expect(server.requests).toHaveLength(1);
    expect(server.requests[0]!.userId).toBe(1);
    expect(await listPendingEvents(db, 1)).toHaveLength(50);
  });
});

describe('results', () => {
  it('uploads in batches of at most 100, in queue order', async () => {
    owner = 1;
    for (let i = 0; i < 150; i += 1) {
      await queue(
        1,
        punch(i % 2 ? 'clock_out' : 'clock_in', new Date(Date.UTC(2026, 2, 1, 0, i)).toISOString()),
      );
    }
    expect(await runSync(deps())).toMatchObject({ synced: 150 });
    expect(server.requests.map((r) => r.eventIds.length)).toEqual([100, 50]);
    expect(server.sessions).toHaveLength(75);
  });

  it('marks refused self punches as rejected and keeps them', async () => {
    owner = 1;
    await queue(1, punch('clock_out', '2026-03-10T08:00:00-04:00'));
    expect(await runSync(deps())).toMatchObject({ rejected: 1, synced: 0 });
    const [row] = await db.getAllAsync<{ status: string; last_error: string; outcome: string }>(
      'SELECT status, last_error, outcome FROM pending_events',
    );
    expect(row!.status).toBe('rejected');
    expect(JSON.parse(row!.outcome)).toMatchObject({ code: 'no_open_session' });
  });

  it('marks invalid and error results as rejected without retrying', async () => {
    owner = 1;
    const invalid = punch('clock_in', '2026-03-10T08:00:00-04:00');
    const error = punch('clock_in', '2026-03-10T09:00:00-04:00');
    await queue(1, invalid, error);
    const report = await runSync(
      deps({
        upload: async () => ({
          results: [
            {
              event_id: invalid.event_id,
              status: 'invalid',
              error: { code: 'validation_error', message: 'Bad event.' },
            },
            {
              event_id: error.event_id,
              status: 'error',
              error: { code: 'idempotency_key_conflict', message: 'Conflict.' },
            },
          ],
        }),
      }),
    );
    expect(report).toMatchObject({ rejected: 2, retrying: 0 });
    expect((await statuses()).map((s) => s.status)).toEqual(['rejected', 'rejected']);
  });

  it('never sends a damaged queue row', async () => {
    owner = 1;
    await enqueuePendingEvents(db, 1, [
      { type: 'punch', id: 'damaged', payload: { nonsense: true } },
    ]);
    expect(await runSync(deps())).toMatchObject({ rejected: 1 });
    expect(server.requests).toEqual([]);
  });
});

describe('createSyncController', () => {
  it('runs one sync at a time and once more for requests made during a run', async () => {
    let release!: () => void;
    let runs = 0;
    const controller = createSyncController(async () => {
      runs += 1;
      if (runs === 1) await new Promise<void>((resolve) => (release = resolve));
      return { status: 'done', synced: 0, rejected: 0, retrying: 0 };
    });

    const first = controller.request();
    const second = controller.request();
    const third = controller.request();
    expect(controller.running).toBe(true);
    release();
    await Promise.all([first, second, third]);
    await controller.idle();

    expect(runs).toBe(2);
    expect(controller.running).toBe(false);
  });
});
