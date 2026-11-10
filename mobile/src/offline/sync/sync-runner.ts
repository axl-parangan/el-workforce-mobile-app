import { describeError } from '@/api/error-messages';
import {
  isRejectedSelfPunch,
  outcomeFromBatch,
  punchPayloadSchema,
  type PunchPayload,
} from '@/features/timekeeping/punch-events';
import type { SyncResponse } from '@/features/timekeeping/schemas';

import type { EventOutcome, PendingEvent } from '../queue/pending-events';

export type SyncDeps = {
  /** The account currently signed in, or null. Read before every batch. */
  getOwner: () => number | null;
  listPending: (userId: number, limit: number) => Promise<PendingEvent[]>;
  markSyncing: (ids: string[]) => Promise<void>;
  markSynced: (id: string, outcome: EventOutcome) => Promise<void>;
  markRejected: (id: string, error: string, outcome?: EventOutcome) => Promise<void>;
  markRetry: (id: string, error: string) => Promise<void>;
  /** `POST /timekeeping/sync/` with the signed-in account's token. */
  upload: (events: PunchPayload[]) => Promise<SyncResponse>;
};

export type SyncReport = {
  status: 'skipped' | 'done' | 'failed';
  synced: number;
  rejected: number;
  retrying: number;
  error?: string;
};

export const SYNC_BATCH_SIZE = 100;

/**
 * Drains the signed-in account's outbox in insertion order, in batches of up
 * to 100 (the API limit).
 *
 * - Only the owner's events are read, and the owner is re-checked before each
 *   batch, so one account's events never travel with another account's token.
 * - Every event keeps its id, payload and `captured_at`: retries are replays
 *   the server de-duplicates (ADR 002).
 * - A network error or 5xx keeps the whole batch queued for the next trigger.
 */
export async function runSync(deps: SyncDeps, maxBatches = 20): Promise<SyncReport> {
  const owner = deps.getOwner();
  const report: SyncReport = { status: 'skipped', synced: 0, rejected: 0, retrying: 0 };
  if (owner === null) return report;
  report.status = 'done';

  for (let batch = 0; batch < maxBatches; batch += 1) {
    if (deps.getOwner() !== owner) break;
    const events = (await deps.listPending(owner, SYNC_BATCH_SIZE)).filter(
      (event) => event.userId === owner,
    );
    if (events.length === 0) break;

    const valid: { event: PendingEvent; payload: PunchPayload }[] = [];
    for (const event of events) {
      const parsed = punchPayloadSchema.safeParse(event.payload);
      if (parsed.success && parsed.data.event_id === event.id) {
        valid.push({ event, payload: parsed.data });
      } else {
        // Kept for inspection, never sent: the server could not process it either.
        await deps.markRejected(event.id, 'This saved punch is damaged and cannot be sent.');
        report.rejected += 1;
      }
    }
    if (valid.length === 0) continue;

    await deps.markSyncing(valid.map(({ event }) => event.id));
    let response: SyncResponse;
    try {
      response = await deps.upload(valid.map(({ payload }) => payload));
    } catch (error) {
      const message = describeError(error);
      for (const { event } of valid) await deps.markRetry(event.id, message);
      report.retrying += valid.length;
      report.status = 'failed';
      report.error = message;
      return report;
    }

    const results = new Map(
      response.results.filter((r) => r.event_id !== null).map((r) => [r.event_id!, r]),
    );
    for (const { event, payload } of valid) {
      const result = results.get(event.id);
      if (!result) {
        await deps.markRetry(event.id, 'The server did not return a result.');
        report.retrying += 1;
      } else if (result.status === 'processed') {
        const outcome = outcomeFromBatch(result.batch);
        if (isRejectedSelfPunch(payload, result.batch)) {
          await deps.markRejected(event.id, outcome.message, outcome);
          report.rejected += 1;
        } else {
          await deps.markSynced(event.id, outcome);
          report.synced += 1;
        }
      } else {
        // `invalid` or `error`: nothing was stored and a retry cannot succeed.
        const { code, message } = result.error;
        await deps.markRejected(event.id, message, { code, message });
        report.rejected += 1;
      }
    }
    if (events.length < SYNC_BATCH_SIZE) break;
  }
  return report;
}

/**
 * Single-flight wrapper: concurrent requests share one run, and a request
 * made during a run schedules exactly one more run afterwards (so an event
 * queued mid-sync is not left behind).
 */
export function createSyncController(run: () => Promise<SyncReport>) {
  let current: Promise<SyncReport> | null = null;
  let again = false;

  return {
    request(): Promise<SyncReport> {
      if (current) {
        again = true;
        return current;
      }
      current = (async () => {
        let report: SyncReport;
        do {
          again = false;
          report = await run();
        } while (again);
        return report;
      })().finally(() => {
        current = null;
      });
      return current;
    },
    /** Resolves once no run is in progress (used before tokens change). */
    async idle(): Promise<void> {
      while (current) await current.catch(() => undefined);
    },
    get running() {
      return current !== null;
    },
  };
}
