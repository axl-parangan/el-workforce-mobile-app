import { openTestDatabase, type TestDatabase } from '@/test-utils/node-sqlite';

import { MIGRATIONS, runMigrations } from '../migrations';
import { migration001PendingEvents } from '../migrations/001-pending-events';
import { clearReferenceCache, readSnapshot, writeSnapshot } from '../repositories/reference-cache';
import {
  enqueuePendingEvent,
  enqueuePendingEvents,
  getEventCounts,
  listPendingEvents,
  listUnsyncedEvents,
  markEventForRetry,
  markEventRejected,
  markEventsSyncing,
  markEventSynced,
  releaseEvents,
  resetInterruptedSyncs,
} from './pending-events';

jest.mock('@/lib/ids', () => {
  let n = 0;
  return { newClientId: () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}` };
});

let db: TestDatabase;

afterEach(() => db.close());

async function migrated() {
  db = openTestDatabase();
  await runMigrations(db);
  return db;
}

const punch = (n: number) => ({ type: 'punch' as const, payload: { n } });

describe('migration 002 (event ownership)', () => {
  it('preserves events queued before ownership existed and never syncs them', async () => {
    db = openTestDatabase();
    // A device still on local schema version 1, with queued events.
    await migration001PendingEvents.up(db);
    await db.execAsync('PRAGMA user_version = 1');
    for (const id of ['legacy-b', 'legacy-a']) {
      await db.runAsync(
        `INSERT INTO pending_events (id, type, payload, status, attempts, created_at, updated_at)
         VALUES (?, 'punch', '{"job_id":1}', 'pending', 2, '2026-03-10T12:00:00Z', '2026-03-10T12:00:00Z')`,
        id,
      );
    }

    await runMigrations(db);

    const version = await db.getFirstAsync<{ user_version: number }>('PRAGMA user_version');
    expect(version?.user_version).toBe(MIGRATIONS.length);
    const rows = await db.getAllAsync<Record<string, unknown>>(
      'SELECT rowid, * FROM pending_events ORDER BY rowid',
    );
    expect(rows).toEqual([
      expect.objectContaining({ id: 'legacy-b', attempts: 2, user_id: null, status: 'pending' }),
      expect.objectContaining({ id: 'legacy-a', attempts: 2, user_id: null, status: 'pending' }),
    ]);
    expect(rows[0]).toMatchObject({ created_at: '2026-03-10T12:00:00Z', payload: '{"job_id":1}' });

    // Ownerless events are never handed to the sync runner for any account...
    expect(await listPendingEvents(db, 1)).toEqual([]);
    // ...but they stay visible as waiting for their original account.
    expect(await getEventCounts(db, 1)).toEqual({
      unsynced: 0,
      recentlyRejected: 0,
      otherAccounts: 2,
    });
  });

  it('is a no-op on an up-to-date database', async () => {
    await migrated();
    await enqueuePendingEvent(db, 1, punch(1));
    await runMigrations(db);
    expect(await listPendingEvents(db, 1)).toHaveLength(1);
  });
});

describe('outbox ownership', () => {
  it('lists only the owner’s events, in insertion order', async () => {
    await migrated();
    const [a1] = await enqueuePendingEvents(db, 1, [punch(1)]);
    const [b1] = await enqueuePendingEvents(db, 2, [punch(2)]);
    const [a2, a3] = await enqueuePendingEvents(db, 1, [punch(3), punch(4)]);

    expect((await listPendingEvents(db, 1)).map((e) => e.id)).toEqual([a1, a2, a3]);
    expect((await listPendingEvents(db, 2)).map((e) => e.id)).toEqual([b1]);
    expect(await getEventCounts(db, 1)).toMatchObject({ unsynced: 3, otherAccounts: 1 });
    expect(await getEventCounts(db, 2)).toMatchObject({ unsynced: 1, otherAccounts: 3 });
    // Nobody signed in: everything waits for its account.
    expect(await getEventCounts(db, null)).toMatchObject({ unsynced: 0, otherAccounts: 4 });
  });

  it('keeps events queued together in order even with identical timestamps', async () => {
    await migrated();
    const ids = await enqueuePendingEvents(db, 1, [punch(1), punch(2)]);
    const events = await listPendingEvents(db, 1);
    expect(events.map((e) => e.id)).toEqual(ids);
    expect(events[0]!.createdAt).toBe(events[1]!.createdAt);
    expect(events[0]!.sequence).toBeLessThan(events[1]!.sequence);
  });

  it('enqueues a batch atomically', async () => {
    await migrated();
    const [existing] = await enqueuePendingEvents(db, 1, [punch(1)]);
    await expect(
      enqueuePendingEvents(db, 1, [punch(2), { type: 'punch', payload: {}, id: existing }]),
    ).rejects.toThrow();
    expect(await listPendingEvents(db, 1)).toHaveLength(1);
  });

  it('reserves events for an online attempt so the runner skips them', async () => {
    await migrated();
    const ids = await enqueuePendingEvents(db, 1, [punch(1), punch(2)], { status: 'syncing' });
    expect(await listPendingEvents(db, 1)).toEqual([]);
    expect(await listUnsyncedEvents(db, 1)).toHaveLength(2);

    await releaseEvents(db, [ids[1]!]);
    expect((await listPendingEvents(db, 1)).map((e) => e.id)).toEqual([ids[1]]);
  });
});

describe('status transitions', () => {
  it('records outcomes and never deletes events', async () => {
    await migrated();
    const [ok, bad, retry] = await enqueuePendingEvents(db, 1, [punch(1), punch(2), punch(3)]);
    await markEventsSyncing(db, [ok!, bad!, retry!]);

    await markEventSynced(db, ok!, { code: 'clocked_in', message: 'Clocked in.' });
    await markEventRejected(db, bad!, 'Already clocked in.', {
      code: 'already_clocked_in',
      message: 'Already clocked in.',
    });
    await markEventForRetry(db, retry!, 'offline');

    const all = await db.getAllAsync<{ id: string; status: string; attempts: number }>(
      'SELECT id, status, attempts FROM pending_events ORDER BY rowid',
    );
    expect(all).toEqual([
      { id: ok, status: 'synced', attempts: 0 },
      { id: bad, status: 'rejected', attempts: 0 },
      { id: retry, status: 'pending', attempts: 1 },
    ]);
    expect(await getEventCounts(db, 1)).toEqual({
      unsynced: 1,
      recentlyRejected: 1,
      otherAccounts: 0,
    });
  });

  it('returns interrupted syncs to the queue at launch', async () => {
    await migrated();
    await enqueuePendingEvents(db, 1, [punch(1)], { status: 'syncing' });
    await resetInterruptedSyncs(db);
    expect(await listPendingEvents(db, 1)).toHaveLength(1);
  });
});

describe('reference cache', () => {
  it('stores snapshots per account and clears them without touching the outbox', async () => {
    await migrated();
    await enqueuePendingEvent(db, 1, punch(1));
    await writeSnapshot(db, 1, 'jobs.assigned', [{ id: 1 }], '2026-03-10T12:00:00Z');
    await writeSnapshot(db, 1, 'jobs.assigned', [{ id: 2 }], '2026-03-10T13:00:00Z');

    expect(await readSnapshot(db, 1, 'jobs.assigned')).toEqual({
      payload: [{ id: 2 }],
      fetchedAt: '2026-03-10T13:00:00Z',
    });
    expect(await readSnapshot(db, 2, 'jobs.assigned')).toBeNull();

    await clearReferenceCache(db);
    expect(await readSnapshot(db, 1, 'jobs.assigned')).toBeNull();
    expect(await listPendingEvents(db, 1)).toHaveLength(1);
  });
});
