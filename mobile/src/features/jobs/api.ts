import { apiRequest } from '@/api/client';
import { fetchAllPages, paginatedSchema, withQuery } from '@/api/pagination';

import {
  assignmentSchema,
  assignResponseSchema,
  employeeOptionSchema,
  jobSchema,
  type JobInput,
} from './schemas';

// --- Jobs ------------------------------------------------------------------------

export function listJobs(params: {
  search?: string;
  status?: string;
  managed_by_me?: boolean;
  assigned_to_me?: boolean;
  page?: number;
  page_size?: number;
}) {
  return apiRequest(withQuery('/jobs/', params), { schema: paginatedSchema(jobSchema) });
}

/** All jobs the user is actively assigned to (cached offline). */
export function listAllAssignedJobs() {
  return fetchAllPages('/jobs/', jobSchema, { assigned_to_me: true });
}

export function getJob(id: number) {
  return apiRequest(`/jobs/${id}/`, { schema: jobSchema });
}

export function createJob(input: JobInput) {
  return apiRequest('/jobs/', { method: 'POST', body: input, schema: jobSchema });
}

export function updateJob(id: number, input: JobInput) {
  return apiRequest(`/jobs/${id}/`, { method: 'PATCH', body: input, schema: jobSchema });
}

export function designateLeadHand(jobId: number, employeeId: number | null) {
  return apiRequest(`/jobs/${jobId}/lead-hand/`, {
    method: 'PUT',
    body: { employee_id: employeeId },
    schema: jobSchema,
  });
}

// --- Assignments -------------------------------------------------------------------

export function listJobAssignments(jobId: number, status: 'active' | 'all' = 'active') {
  return fetchAllPages(`/jobs/${jobId}/assignments/`, assignmentSchema, { status });
}

/** The caller's own active assignments: the offline source for clock-in. */
export function listAllMyAssignments() {
  return fetchAllPages('/assignments/mine/', assignmentSchema, { status: 'active' });
}

export function listMyAssignmentHistory() {
  return fetchAllPages('/assignments/mine/', assignmentSchema, { status: 'all' });
}

export function assignEmployees(
  jobId: number,
  body: { employee_ids: number[]; start_date?: string | null; end_date?: string | null },
) {
  return apiRequest(`/jobs/${jobId}/assignments/`, {
    method: 'POST',
    body,
    schema: assignResponseSchema,
  });
}

export function updateAssignmentDates(
  id: number,
  body: { start_date?: string | null; end_date?: string | null },
) {
  return apiRequest(`/assignments/${id}/`, { method: 'PATCH', body, schema: assignmentSchema });
}

export function endAssignment(id: number, endDate?: string) {
  return apiRequest(`/assignments/${id}/end/`, {
    method: 'POST',
    body: endDate ? { end_date: endDate } : {},
    schema: assignmentSchema,
  });
}

export function cancelAssignment(id: number) {
  return apiRequest(`/assignments/${id}/cancel/`, {
    method: 'POST',
    body: {},
    schema: assignmentSchema,
  });
}

// --- Employees (Managers and Admins) -------------------------------------------------

export function searchEmployees(params: { search?: string; role?: string; is_active?: boolean }) {
  return apiRequest(withQuery('/workforce/employees/', { ...params, page_size: 50 }), {
    schema: paginatedSchema(employeeOptionSchema),
  });
}
