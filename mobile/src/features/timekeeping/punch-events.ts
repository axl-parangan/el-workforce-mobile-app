import { z } from 'zod';

import type { EventOutcome } from '@/offline/queue/pending-events';
import type { PunchLocation } from '@/lib/location';

import type { BatchResult } from './schemas';

/**
 * The payload stored in the offline outbox and sent to the API. Its `event_id`
 * is the outbox row id: the server's idempotency key (ADR 002).
 */
export const punchPayloadSchema = z.object({
  event_id: z.string(),
  action_type: z.enum(['clock_in', 'clock_out']),
  job_id: z.number().int(),
  /** Device time with UTC offset. Never replaced by the server's receipt time. */
  captured_at: z.string(),
  location: z
    .object({
      latitude: z.number(),
      longitude: z.number(),
      accuracy_meters: z.number().nullable(),
    })
    .nullable(),
  /** Group punches only. Omitted for self punches (the server derives the employee). */
  employee_ids: z.array(z.number().int()).optional(),
  reason: z.string().optional(),
});
export type PunchPayload = z.infer<typeof punchPayloadSchema>;

export function isGroupPunch(payload: PunchPayload): boolean {
  return payload.employee_ids !== undefined;
}

/** Exactly the fields the API accepts for a sync event, in a stable shape. */
export function toSyncEvent(payload: PunchPayload) {
  return {
    event_id: payload.event_id,
    action_type: payload.action_type,
    job_id: payload.job_id,
    captured_at: payload.captured_at,
    location: payload.location,
    ...(payload.employee_ids !== undefined ? { employee_ids: payload.employee_ids } : {}),
    ...(payload.reason ? { reason: payload.reason } : {}),
  };
}

export function toLocationPayload(location: PunchLocation): PunchPayload['location'] {
  if (location.status !== 'captured') return null;
  return {
    latitude: location.latitude,
    longitude: location.longitude,
    accuracy_meters: location.accuracyMeters,
  };
}

/** Summarises a stored server result for the outbox and history screens. */
export function outcomeFromBatch(batch: BatchResult): EventOutcome {
  const results = batch.results.map((result) => ({
    employeeId: result.employee.id,
    employee: result.employee.name,
    status: result.status === 'accepted' ? ('accepted' as const) : ('rejected' as const),
    code: result.code,
    message: result.message,
  }));
  const rejected = results.filter((r) => r.status === 'rejected');
  if (results.length === 1) {
    return { code: results[0]!.code, message: results[0]!.message, results };
  }
  return {
    code: rejected.length ? 'partially_rejected' : 'accepted',
    message: rejected.length
      ? `${results.length - rejected.length} of ${results.length} accepted.`
      : `All ${results.length} accepted.`,
    results,
  };
}

/** A self punch whose only result was refused. Group punches are judged per employee. */
export function isRejectedSelfPunch(payload: PunchPayload, batch: BatchResult): boolean {
  return !isGroupPunch(payload) && batch.results.every((r) => r.status === 'rejected');
}

/** Processing order used by the server (Q13): time, clock-outs first, then queue order. */
export function compareByProcessingOrder(
  a: { payload: PunchPayload; sequence: number },
  b: { payload: PunchPayload; sequence: number },
): number {
  const time = Date.parse(a.payload.captured_at) - Date.parse(b.payload.captured_at);
  if (time !== 0) return time;
  const rank = (p: PunchPayload) => (p.action_type === 'clock_out' ? 0 : 1);
  const action = rank(a.payload) - rank(b.payload);
  if (action !== 0) return action;
  return a.sequence - b.sequence;
}
