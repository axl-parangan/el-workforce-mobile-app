import { z } from 'zod';

/** Mirrors docs/api/timekeeping.md. */
const jobRef = z.object({ id: z.number().int(), job_number: z.string(), name: z.string() });
const userRef = z.object({ id: z.number().int(), email: z.string() }).nullable();

export const locationResultSchema = z.object({
  status: z.string(),
  flags: z.array(z.string()),
  requires_review: z.boolean(),
  latitude: z.string().nullable(),
  longitude: z.string().nullable(),
  accuracy_meters: z.string().nullable(),
  distance_meters: z.string().nullable(),
});

export const itemResultSchema = z.object({
  employee: z.object({ id: z.number().int(), name: z.string() }),
  status: z.enum(['pending', 'accepted', 'rejected']),
  code: z.string(),
  message: z.string(),
  session_id: z.number().int().nullable(),
  punch_id: z.number().int().nullable(),
  processed_at: z.string().nullable(),
});
export type ItemResult = z.infer<typeof itemResultSchema>;

export const batchResultSchema = z.object({
  event_id: z.string(),
  batch_id: z.number().int(),
  action_type: z.enum(['clock_in', 'clock_out']),
  source: z.string(),
  job: jobRef,
  performed_by: userRef,
  captured_at: z.string(),
  received_at: z.string(),
  entry_reason: z.string().catch(''),
  location: locationResultSchema,
  results: z.array(itemResultSchema),
  replayed: z.boolean(),
});
export type BatchResult = z.infer<typeof batchResultSchema>;

const punchSchema = z
  .object({
    punch_id: z.number().int(),
    at: z.string(),
    received_at: z.string(),
    event_id: z.string(),
    source: z.string(),
    performed_by: userRef,
    location: locationResultSchema,
  })
  .nullable();

export const sessionSchema = z.object({
  id: z.number().int(),
  employee: z.object({ id: z.number().int(), name: z.string() }),
  job: jobRef,
  work_date: z.string(),
  session_status: z.enum(['open', 'closed']),
  review_status: z.string(),
  exception_flags: z.array(z.string()),
  clock_in: punchSchema,
  clock_out: punchSchema,
  duration_seconds: z.number().int().nullable(),
  reviewed_by: userRef,
  reviewed_at: z.string().nullable(),
});
export type Session = z.infer<typeof sessionSchema>;

export const staffSessionSchema = sessionSchema.extend({
  reviews: z.array(
    z.object({
      id: z.number().int(),
      decision: z.enum(['approved', 'rejected']),
      reason: z.string(),
      reviewed_by: userRef,
      reviewed_at: z.string(),
    }),
  ),
});
export type StaffSession = z.infer<typeof staffSessionSchema>;

export const statusSchema = z.object({
  employee: z.object({ id: z.number().int(), name: z.string() }),
  clocked_in: z.boolean(),
  open_session: sessionSchema.nullable(),
});
export type AttendanceStatus = z.infer<typeof statusSchema>;

export const crewSchema = z.object({
  job: z.object({ id: z.number().int(), job_number: z.string() }),
  crew: z.array(
    z.object({
      employee: z.object({ id: z.number().int(), name: z.string(), has_account: z.boolean() }),
      assignment_id: z.number().int(),
      clocked_in: z.boolean(),
      open_session: z
        .object({ id: z.number().int(), job: jobRef, clock_in_at: z.string().nullable() })
        .nullable(),
    }),
  ),
});
export type Crew = z.infer<typeof crewSchema>;

export const rejectedEventSchema = z.object({
  id: z.number().int(),
  event_id: z.string(),
  action_type: z.string(),
  source: z.string(),
  job: jobRef,
  employee: z.object({ id: z.number().int(), name: z.string() }),
  performed_by: userRef,
  captured_at: z.string(),
  received_at: z.string(),
  code: z.string(),
  message: z.string(),
});
export type RejectedEvent = z.infer<typeof rejectedEventSchema>;

const errorBody = z.object({
  code: z.string(),
  message: z.string(),
  details: z.unknown().optional(),
});

export const syncResponseSchema = z.object({
  results: z.array(
    z.union([
      z.object({ event_id: z.string(), status: z.literal('processed'), batch: batchResultSchema }),
      z.object({
        event_id: z.string().nullable(),
        status: z.enum(['invalid', 'error']),
        error: errorBody,
      }),
    ]),
  ),
});
export type SyncResponse = z.infer<typeof syncResponseSchema>;
