import type { CurrentUser } from '@/features/auth/schemas';
import type { Assignment, Job } from '@/features/jobs/schemas';

/** Capabilities as issued by backend/apps/accounts/authorization.py. */
const EMPLOYEE = [
  'attendance.record_self',
  'attendance.request_correction',
  'attendance.view_own',
  'jobs.view_assigned',
];
const LEADHAND = [
  ...EMPLOYEE,
  'assignments.view_crew',
  'attendance.record_crew',
  'attendance.view_crew',
  'jobs.create',
  'jobs.edit_managed',
  'jobs.lead',
];
const MANAGER = [
  ...EMPLOYEE,
  'accounts.manage_staff',
  'assignments.manage',
  'attendance.record_any',
  'attendance.review',
  'attendance.view_any',
  'employees.view_any',
  'jobs.create',
  'jobs.edit_any',
  'jobs.view_any',
];
const ADMIN = [...MANAGER, 'accounts.manage_managers'];

const ROLE_CAPABILITIES = { worker: EMPLOYEE, leadhand: LEADHAND, manager: MANAGER, admin: ADMIN };

export function makeUser(
  role: keyof typeof ROLE_CAPABILITIES,
  overrides: Partial<CurrentUser> = {},
): CurrentUser {
  const ids = { worker: 2, leadhand: 3, manager: 6, admin: 7 };
  return {
    id: ids[role],
    email: `${role}@example.com`,
    first_name: '',
    last_name: '',
    role,
    capabilities: [...ROLE_CAPABILITIES[role]].sort(),
    employee: { id: ids[role] * 10, name: `Demo ${role}` },
    ...overrides,
  };
}

export function makeJob(overrides: Partial<Job> = {}, viewer: Partial<Job['viewer']> = {}): Job {
  const id = overrides.id ?? 1;
  return {
    id,
    job_number: `J-${id}`,
    name: `Job ${id}`,
    address: '1 Main St',
    status: 'active',
    start_date: null,
    end_date: null,
    geofence: { configured: false, latitude: null, longitude: null, radius_meters: null },
    lead_hand: null,
    viewer: { manages_job: false, is_lead_hand: false, my_assignment_id: 100 + id, ...viewer },
    created_by: null,
    updated_by: null,
    created_at: '2026-11-01T08:00:00-04:00',
    updated_at: '2026-11-01T08:00:00-04:00',
    ...overrides,
  };
}

export function makeAssignment(jobId: number, overrides: Partial<Assignment> = {}): Assignment {
  return {
    id: 100 + jobId,
    job: { id: jobId, job_number: `J-${jobId}`, name: `Job ${jobId}` },
    employee: { id: 20, name: 'Demo worker', employee_number: null, has_account: true },
    status: 'active',
    start_date: null,
    end_date: null,
    is_lead_hand: false,
    assigned_at: '2026-11-01T08:00:00-04:00',
    assigned_by: null,
    updated_at: '2026-11-01T08:00:00-04:00',
    ...overrides,
  };
}
