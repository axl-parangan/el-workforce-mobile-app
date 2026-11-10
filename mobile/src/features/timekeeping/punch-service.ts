import { describeError, messageForCode } from '@/api/error-messages';
import { ApiError } from '@/api/errors';
import type { EventOutcome, NewPendingEvent } from '@/offline/queue/pending-events';

import { isRejectedSelfPunch, outcomeFromBatch, type PunchPayload } from './punch-events';
import { batchResultSchema, type BatchResult } from './schemas';

export type PunchDeps = {
  /** The owner's events still waiting to reach the server (pending or in flight). */
  countUnsynced: (userId: number) => Promise<number>;
  enqueue: (
    userId: number,
    events: NewPendingEvent[],
    status: 'pending' | 'syncing',
  ) => Promise<string[]>;
  submit: (payload: PunchPayload) => Promise<BatchResult>;
  markSynced: (id: string, outcome: EventOutcome) => Promise<void>;
  markRejected: (id: string, error: string, outcome?: EventOutcome) => Promise<void>;
  markRetry: (id: string, error: string) => Promise<void>;
  release: (ids: string[]) => Promise<void>;
  requestSync: () => void;
};

export type PunchOutcome =
  | { kind: 'accepted'; payload: PunchPayload; result: BatchResult }
  | {
      kind: 'rejected';
      payload: PunchPayload;
      code: string;
      message: string;
      result: BatchResult | null;
    }
  /** Saved on the device; the sync runner will deliver it with the same event_id. */
  | { kind: 'queued'; payload: PunchPayload; reason: string };

/** Answers that mean "try again later", never "refused". */
function isTransient(error: unknown): boolean {
  if (!(error instanceof ApiError)) return true; // network, timeout, unexpected body
  return (
    error.status === 401 || error.status === 408 || error.status === 429 || error.status >= 500
  );
}

function rejectedFromError(payload: PunchPayload, error: ApiError): PunchOutcome {
  const details = error.details as { result?: unknown } | undefined;
  const stored = batchResultSchema.safeParse(details?.result);
  const result = stored.success ? stored.data : null;
  const rejection = result?.results.find((r) => r.status === 'rejected');
  return {
    kind: 'rejected',
    payload,
    code: rejection?.code ?? error.code,
    message: rejection?.message ?? messageForCode(error.code, error.message),
    result,
  };
}

/**
 * Records punches for `userId`, preserving their order (a job switch is a
 * clock-out then a clock-in with the same `captured_at`).
 *
 * The events are written to the outbox first, so nothing is lost if the app
 * dies. Then, when the account has nothing else waiting, each is submitted
 * online in order (M5). An unreachable server leaves the event (and the ones
 * after it) queued under the same event_id for the sync runner. When older
 * events are still waiting, new ones queue behind them so the server always
 * receives them together and orders them by device time.
 */
export async function recordPunches(
  deps: PunchDeps,
  userId: number,
  payloads: PunchPayload[],
): Promise<PunchOutcome[]> {
  const backlog = (await deps.countUnsynced(userId)) > 0;
  const events = payloads.map((payload) => ({
    type: 'punch' as const,
    id: payload.event_id,
    payload,
  }));

  if (backlog) {
    await deps.enqueue(userId, events, 'pending');
    deps.requestSync();
    return payloads.map((payload) => ({
      kind: 'queued',
      payload,
      reason: 'Earlier punches are still waiting to sync.',
    }));
  }

  // Reserved ('syncing') so the background runner does not send them concurrently.
  await deps.enqueue(userId, events, 'syncing');
  const outcomes: PunchOutcome[] = [];

  for (const [index, payload] of payloads.entries()) {
    try {
      const result = await deps.submit(payload);
      const outcome = outcomeFromBatch(result);
      if (isRejectedSelfPunch(payload, result)) {
        await deps.markRejected(payload.event_id, outcome.message, outcome);
        outcomes.push({
          kind: 'rejected',
          payload,
          code: outcome.code,
          message: outcome.message,
          result,
        });
      } else {
        await deps.markSynced(payload.event_id, outcome);
        outcomes.push({ kind: 'accepted', payload, result });
      }
    } catch (error) {
      if (isTransient(error)) {
        const reason = describeError(error);
        await deps.markRetry(payload.event_id, reason);
        const rest = payloads.slice(index + 1);
        await deps.release(rest.map((p) => p.event_id));
        outcomes.push({ kind: 'queued', payload, reason });
        rest.forEach((p) => outcomes.push({ kind: 'queued', payload: p, reason }));
        return outcomes;
      }
      const rejected = rejectedFromError(payload, error as ApiError);
      if (rejected.kind === 'rejected') {
        const outcome = rejected.result
          ? outcomeFromBatch(rejected.result)
          : { code: rejected.code, message: rejected.message };
        await deps.markRejected(payload.event_id, rejected.message, outcome);
      }
      outcomes.push(rejected);
    }
  }
  return outcomes;
}

/**
 * Manager/Admin group punches are online-only (M7): nothing is queued. The
 * caller keeps the payload, so retrying after a network error reuses the same
 * event_id and the server replays instead of duplicating.
 */
export async function submitOnlineOnly(
  submit: (payload: PunchPayload) => Promise<BatchResult>,
  payload: PunchPayload,
): Promise<PunchOutcome | { kind: 'offline'; payload: PunchPayload; message: string }> {
  try {
    return { kind: 'accepted', payload, result: await submit(payload) };
  } catch (error) {
    if (error instanceof ApiError && !isTransient(error)) return rejectedFromError(payload, error);
    return { kind: 'offline', payload, message: describeError(error) };
  }
}
