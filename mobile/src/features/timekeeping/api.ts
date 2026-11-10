import { apiRequest } from '@/api/client';
import { paginatedSchema, withQuery } from '@/api/pagination';

import { isGroupPunch, toSyncEvent, type PunchPayload } from './punch-events';
import {
  batchResultSchema,
  crewSchema,
  rejectedEventSchema,
  sessionSchema,
  staffSessionSchema,
  statusSchema,
  syncResponseSchema,
} from './schemas';

export function getAttendanceStatus() {
  return apiRequest('/timekeeping/status/', { schema: statusSchema });
}

export function listMySessions(page = 1) {
  return apiRequest(withQuery('/timekeeping/sessions/', { page }), {
    schema: paginatedSchema(sessionSchema),
  });
}

export function getMySession(id: number) {
  return apiRequest(`/timekeeping/sessions/${id}/`, { schema: sessionSchema });
}

export function getCrew(jobId: number) {
  return apiRequest(`/timekeeping/jobs/${jobId}/crew/`, { schema: crewSchema });
}

/** Online submission of one punch event (the same event_id as the queued copy). */
export function submitPunch(payload: PunchPayload) {
  const action = payload.action_type === 'clock_in' ? 'clock-in' : 'clock-out';
  const path = `/timekeeping/${isGroupPunch(payload) ? `group-${action}` : action}/`;
  const { action_type: _action, ...body } = toSyncEvent(payload);
  return apiRequest(path, { method: 'POST', body, schema: batchResultSchema });
}

/** Uploads up to 100 queued events (`POST /timekeeping/sync/`). */
export function syncPunches(events: PunchPayload[]) {
  return apiRequest('/timekeeping/sync/', {
    method: 'POST',
    body: { events: events.map(toSyncEvent) },
    schema: syncResponseSchema,
  });
}

// --- Staff ---------------------------------------------------------------------------

export type StaffListKind = 'all' | 'exceptions';

export function listStaffSessions(kind: StaffListKind, params: { job_id?: number } = {}) {
  const path = kind === 'exceptions' ? '/staff/attendance/exceptions/' : '/staff/attendance/';
  return apiRequest(withQuery(path, params), { schema: paginatedSchema(staffSessionSchema) });
}

export function listRejectedEvents(params: { job_id?: number } = {}) {
  return apiRequest(withQuery('/staff/attendance/rejected-events/', params), {
    schema: paginatedSchema(rejectedEventSchema),
  });
}

export function getStaffSession(id: number) {
  return apiRequest(`/staff/attendance/${id}/`, { schema: staffSessionSchema });
}

export function reviewSession(id: number, decision: 'approved' | 'rejected', reason: string) {
  return apiRequest(`/staff/attendance/${id}/review/`, {
    method: 'POST',
    body: { decision, reason },
    schema: staffSessionSchema,
  });
}
