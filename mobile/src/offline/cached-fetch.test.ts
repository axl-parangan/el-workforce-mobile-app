import { z } from 'zod';

import { ApiError, NetworkError } from '@/api/errors';

import { cachedFetch, isStale } from './cached-fetch';
import type { Snapshot } from './repositories/reference-cache';

const schema = z.array(z.object({ id: z.number() }));

function setup(snapshot: Snapshot | null = null) {
  const store = { snapshot };
  return {
    store,
    read: jest.fn(async () => store.snapshot),
    write: jest.fn(async (data: unknown, fetchedAt: string) => {
      store.snapshot = { payload: data, fetchedAt };
    }),
  };
}

it('returns fresh data and stores a snapshot', async () => {
  const { store, read, write } = setup();
  const result = await cachedFetch({
    fetcher: async () => [{ id: 1 }],
    schema,
    read,
    write,
    now: () => '2026-03-10T12:00:00Z',
  });
  expect(result).toEqual({
    data: [{ id: 1 }],
    fetchedAt: '2026-03-10T12:00:00Z',
    fromCache: false,
  });
  expect(store.snapshot).toEqual({ payload: [{ id: 1 }], fetchedAt: '2026-03-10T12:00:00Z' });
  expect(read).not.toHaveBeenCalled();
});

it('falls back to the snapshot when offline', async () => {
  const { read, write } = setup({ payload: [{ id: 2 }], fetchedAt: '2026-03-09T12:00:00Z' });
  const result = await cachedFetch({
    fetcher: () => Promise.reject(new NetworkError()),
    schema,
    read,
    write,
  });
  expect(result).toEqual({ data: [{ id: 2 }], fetchedAt: '2026-03-09T12:00:00Z', fromCache: true });
  expect(write).not.toHaveBeenCalled();
});

it('falls back on server errors (5xx)', async () => {
  const { read, write } = setup({ payload: [], fetchedAt: '2026-03-09T12:00:00Z' });
  const result = await cachedFetch({
    fetcher: () => Promise.reject(new ApiError(503, 'unavailable', 'down')),
    schema,
    read,
    write,
  });
  expect(result.fromCache).toBe(true);
});

it('never masks a real answer such as 403 or 404 with cached data', async () => {
  const { read, write } = setup({ payload: [{ id: 2 }], fetchedAt: '2026-03-09T12:00:00Z' });
  const denied = new ApiError(404, 'not_found', 'Not found.');
  await expect(
    cachedFetch({ fetcher: () => Promise.reject(denied), schema, read, write }),
  ).rejects.toBe(denied);
});

it('re-throws when offline without a usable snapshot', async () => {
  const offline = new NetworkError();
  await expect(
    cachedFetch({ fetcher: () => Promise.reject(offline), schema, ...setup() }),
  ).rejects.toBe(offline);
  await expect(
    cachedFetch({
      fetcher: () => Promise.reject(offline),
      schema,
      ...setup({ payload: { unexpected: true }, fetchedAt: '2026-03-09T12:00:00Z' }),
    }),
  ).rejects.toBe(offline);
});

it('treats data older than 24 hours as stale (M6)', () => {
  const now = Date.parse('2026-03-10T12:00:00Z');
  expect(isStale('2026-03-09T12:30:00Z', now)).toBe(false);
  expect(isStale('2026-03-09T11:59:00Z', now)).toBe(true);
});
