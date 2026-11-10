import { runMigrations } from '@/offline/migrations';
import {
  enqueuePendingEvents,
  getEventCounts,
  listPendingEvents,
  listUnsyncedEvents,
  markEventForRetry,
  markEventRejected,
  markEventsSyncing,
  markEventSynced,
  releaseEvents,
} from '@/offline/queue/pending-events';
import { runSync } from '@/offline/sync/sync-runner';
import { createFakeServer, type FakeServer } from '@/test-utils/fake-timekeeping-server';
import { openTestDatabase, type TestDatabase } from '@/test-utils/node-sqlite';

import type { PunchPayload } from './punch-events';
import { recordPunches, submitOnlineOnly, type PunchDeps } from './punch-service';

let db: TestDatabase;
let server: FakeServer;
let syncRequests: number;
let counter = 0;
const USER = 1;

beforeEach(async () => {
  db = openTestDatabase();
  await runMigrations(db);
  server = createFakeServer({ assigned: (_employee, jobId) => jobId !== 99 });
  syncRequests = 0;
});
afterEach(() => db.close());

function deps(): PunchDeps {
  return {
    countUnsynced: async (userId) => (await getEventCounts(db, userId)).unsynced,
    enqueue: (userId, events, status) => enqueuePendingEvents(db, userId, events, { status }),
    submit: (payload) => server.submit(USER, payload),
    markSynced: (id, outcome) => markEventSynced(db, id, outcome),
    markRejected: (id, error, outcome) => markEventRejected(db, id, error, outcome),
    markRetry: (id, error) => markEventForRetry(db, id, error),
    release: (ids) => releaseEvents(db, ids),
    requestSync: () => {
      syncRequests += 1;
    },
  };
}

function syncNow() {
  return runSync({
    getOwner: () => USER,
    listPending: (userId, limit) => listPendingEvents(db, userId, limit),
    markSyncing: (ids) => markEventsSyncing(db, ids),
    markSynced: (id, outcome) => markEventSynced(db, id, outcome),
    markRejected: (id, error, outcome) => markEventRejected(db, id, error, outcome),
    markRetry: (id, error) => markEventForRetry(db, id, error),
    upload: (events) => server.sync(USER, events),
  });
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

async function rows() {
  return db.getAllAsync<{ id: string; status: string; user_id: number }>(
    'SELECT id, status, user_id FROM pending_events ORDER BY rowid',
  );
}

it('submits online first and records the accepted result', async () => {
  const clockIn = punch('clock_in', '2026-03-10T08:00:00-04:00');
  const [outcome] = await recordPunches(deps(), USER, [clockIn]);

  expect(outcome).toMatchObject({ kind: 'accepted' });
  expect(await rows()).toEqual([{ id: clockIn.event_id, status: 'synced', user_id: USER }]);
  expect(server.sessions).toHaveLength(1);
  expect(syncRequests).toBe(0);
});

it('queues offline under the same event id, and sync delivers it exactly once', async () => {
  server.setOnline(false);
  const clockIn = punch('clock_in', '2026-03-10T08:00:00-04:00');
  const [outcome] = await recordPunches(deps(), USER, [clockIn]);
  expect(outcome).toMatchObject({ kind: 'queued' });
  expect(await rows()).toEqual([{ id: clockIn.event_id, status: 'pending', user_id: USER }]);

  server.setOnline(true);
  await syncNow();
  await syncNow();
  expect(server.requests.map((r) => r.eventIds)).toEqual([[clockIn.event_id], [clockIn.event_id]]);
  expect(server.sessions).toHaveLength(1);
  expect((await rows())[0]!.status).toBe('synced');
});

it('recovers when the online response was lost after the server stored the punch', async () => {
  server.dropNextResponse();
  const clockIn = punch('clock_in', '2026-03-10T08:00:00-04:00');
  expect((await recordPunches(deps(), USER, [clockIn]))[0]).toMatchObject({ kind: 'queued' });

  expect(await syncNow()).toMatchObject({ synced: 1 });
  expect(server.sessions).toHaveLength(1);
});

it('queues behind older unsynced punches instead of overtaking them', async () => {
  server.setOnline(false);
  await recordPunches(deps(), USER, [punch('clock_in', '2026-03-10T08:00:00-04:00')]);
  server.setOnline(true);

  // Online again, but the 08:00 clock-in has not synced yet.
  const clockOut = punch('clock_out', '2026-03-10T17:00:00-04:00');
  const [outcome] = await recordPunches(deps(), USER, [clockOut]);
  expect(outcome).toMatchObject({ kind: 'queued' });
  expect(syncRequests).toBe(1);
  expect(server.requests).toHaveLength(1); // only the failed offline attempt

  await syncNow();
  expect(server.sessions).toEqual([
    { employeeId: 10, jobId: 1, in: '2026-03-10T08:00:00-04:00', out: '2026-03-10T17:00:00-04:00' },
  ]);
});

it('reports the server’s rejection and keeps the event', async () => {
  const [outcome] = await recordPunches(deps(), USER, [
    punch('clock_out', '2026-03-10T08:00:00-04:00'),
  ]);
  expect(outcome).toMatchObject({ kind: 'rejected', code: 'no_open_session' });
  expect((await rows())[0]!.status).toBe('rejected');
});

describe('switching jobs', () => {
  it('clocks out of A and into B at the same instant', async () => {
    await recordPunches(deps(), USER, [punch('clock_in', '2026-03-10T07:00:00-04:00', 1)]);
    const outcomes = await recordPunches(deps(), USER, [
      punch('clock_out', '2026-03-10T10:30:00-04:00', 1),
      punch('clock_in', '2026-03-10T10:30:00-04:00', 2),
    ]);
    expect(outcomes.map((o) => o.kind)).toEqual(['accepted', 'accepted']);
    expect(server.sessions).toEqual([
      {
        employeeId: 10,
        jobId: 1,
        in: '2026-03-10T07:00:00-04:00',
        out: '2026-03-10T10:30:00-04:00',
      },
      { employeeId: 10, jobId: 2, in: '2026-03-10T10:30:00-04:00', out: null },
    ]);
  });

  it('reports a refused clock-in at B after the clock-out at A, without reverting it (M8)', async () => {
    await recordPunches(deps(), USER, [punch('clock_in', '2026-03-10T07:00:00-04:00', 1)]);
    const outcomes = await recordPunches(deps(), USER, [
      punch('clock_out', '2026-03-10T10:30:00-04:00', 1),
      punch('clock_in', '2026-03-10T10:30:00-04:00', 99), // not assigned to job 99
    ]);
    expect(outcomes).toMatchObject([
      { kind: 'accepted' },
      { kind: 'rejected', code: 'no_active_assignment' },
    ]);
    // A stays closed: nothing is reversed automatically.
    expect(server.sessions).toEqual([
      {
        employeeId: 10,
        jobId: 1,
        in: '2026-03-10T07:00:00-04:00',
        out: '2026-03-10T10:30:00-04:00',
      },
    ]);
  });

  it('queues both events in order when offline, and they sync correctly', async () => {
    await recordPunches(deps(), USER, [punch('clock_in', '2026-03-10T07:00:00-04:00', 1)]);
    server.setOnline(false);
    const out = punch('clock_out', '2026-03-10T10:30:00-04:00', 1);
    const into = punch('clock_in', '2026-03-10T10:30:00-04:00', 2);
    const outcomes = await recordPunches(deps(), USER, [out, into]);
    expect(outcomes.map((o) => o.kind)).toEqual(['queued', 'queued']);
    // The second event was released back to the queue, not left reserved.
    expect((await listUnsyncedEvents(db, USER)).map((e) => [e.id, e.status])).toEqual([
      [out.event_id, 'pending'],
      [into.event_id, 'pending'],
    ]);

    server.setOnline(true);
    expect(await syncNow()).toMatchObject({ synced: 2 });
    expect(server.sessions.map((s) => [s.jobId, s.in, s.out])).toEqual([
      [1, '2026-03-10T07:00:00-04:00', '2026-03-10T10:30:00-04:00'],
      [2, '2026-03-10T10:30:00-04:00', null],
    ]);
  });
});

describe('submitOnlineOnly (Manager/Admin group punches, M7)', () => {
  it('never queues, and a retry with the same event id is replayed', async () => {
    const group = { ...punch('clock_in', '2026-03-10T08:00:00-04:00'), employee_ids: [30, 40] };
    server.setOnline(false);
    expect(await submitOnlineOnly((p) => server.submit(USER, p), group)).toMatchObject({
      kind: 'offline',
    });
    expect(await rows()).toEqual([]);

    server.setOnline(true);
    server.dropNextResponse();
    await submitOnlineOnly((p) => server.submit(USER, p), group);
    const retried = await submitOnlineOnly((p) => server.submit(USER, p), group);
    expect(retried).toMatchObject({ kind: 'accepted' });
    expect(retried.kind === 'accepted' && retried.result.replayed).toBe(true);
    expect(server.sessions).toHaveLength(2);
  });
});
