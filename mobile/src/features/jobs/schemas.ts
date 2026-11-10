import { z } from 'zod';

/** Mirrors docs/api/jobs.md. Decimals arrive as strings. */
export const jobStatusSchema = z.enum(['planned', 'active', 'on_hold', 'completed', 'cancelled']);
export type JobStatus = z.infer<typeof jobStatusSchema>;

export const JOB_STATUS_LABELS: Record<JobStatus, string> = {
  planned: 'Planned',
  active: 'Active',
  on_hold: 'On hold',
  completed: 'Completed',
  cancelled: 'Cancelled',
};

const personSchema = z.object({ id: z.number().int(), name: z.string() }).nullable();

export const jobSchema = z.object({
  id: z.number().int(),
  job_number: z.string(),
  name: z.string(),
  address: z.string(),
  status: jobStatusSchema,
  start_date: z.string().nullable(),
  end_date: z.string().nullable(),
  geofence: z.object({
    configured: z.boolean(),
    latitude: z.string().nullable(),
    longitude: z.string().nullable(),
    radius_meters: z.number().int().nullable(),
  }),
  lead_hand: z.object({ employee_id: z.number().int(), name: z.string() }).nullable(),
  viewer: z.object({
    manages_job: z.boolean(),
    is_lead_hand: z.boolean(),
    my_assignment_id: z.number().int().nullable(),
  }),
  created_by: personSchema,
  updated_by: personSchema,
  created_at: z.string(),
  updated_at: z.string(),
});
export type Job = z.infer<typeof jobSchema>;

export const assignmentStatusSchema = z.enum(['active', 'ended', 'cancelled']);
export type AssignmentStatus = z.infer<typeof assignmentStatusSchema>;

export const assignmentSchema = z.object({
  id: z.number().int(),
  job: z.object({ id: z.number().int(), job_number: z.string(), name: z.string() }),
  employee: z.object({
    id: z.number().int(),
    name: z.string(),
    employee_number: z.string().nullable(),
    has_account: z.boolean(),
  }),
  status: assignmentStatusSchema,
  start_date: z.string().nullable(),
  end_date: z.string().nullable(),
  is_lead_hand: z.boolean(),
  assigned_at: z.string(),
  assigned_by: personSchema,
  updated_at: z.string(),
});
export type Assignment = z.infer<typeof assignmentSchema>;

export const assignResponseSchema = z.object({
  job: z.object({ id: z.number().int(), job_number: z.string() }),
  results: z.array(
    z.object({
      employee_id: z.number().int(),
      status: z.enum(['assigned', 'rejected']),
      code: z.string(),
      message: z.string(),
      assignment: assignmentSchema.nullable(),
    }),
  ),
});
export type AssignResponse = z.infer<typeof assignResponseSchema>;

/** Read-only employee list (decision M4). Never includes pay. */
export const employeeOptionSchema = z.object({
  id: z.number().int(),
  name: z.string(),
  employee_number: z.string().nullable(),
  is_active: z.boolean(),
  has_account: z.boolean(),
  account: z.object({ role: z.string(), is_active: z.boolean() }).nullable(),
});
export type EmployeeOption = z.infer<typeof employeeOptionSchema>;

/** Job fields a form may send. */
export type JobInput = Partial<{
  job_number: string;
  name: string;
  address: string;
  start_date: string | null;
  end_date: string | null;
  status: JobStatus;
  latitude: string | null;
  longitude: string | null;
  geofence_radius_meters: number | null;
  lead_hand_id: number | null;
}>;
