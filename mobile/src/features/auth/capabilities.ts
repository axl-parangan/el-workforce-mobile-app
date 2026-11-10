import type { Href } from 'expo-router';

import { useAuth } from './auth-provider';
import type { CurrentUser, Role } from './schemas';

/**
 * Capability names issued by the server in `/auth/me` (backend
 * apps/accounts/authorization.py). The app only *reads* them to decide which
 * actions to offer; the API enforces every permission.
 */
export const Capability = {
  attendanceRecordSelf: 'attendance.record_self',
  attendanceRecordCrew: 'attendance.record_crew',
  attendanceRecordAny: 'attendance.record_any',
  attendanceViewCrew: 'attendance.view_crew',
  attendanceViewAny: 'attendance.view_any',
  attendanceReview: 'attendance.review',
  jobsViewAny: 'jobs.view_any',
  jobsCreate: 'jobs.create',
  jobsEditAny: 'jobs.edit_any',
  jobsEditManaged: 'jobs.edit_managed',
  assignmentsManage: 'assignments.manage',
  assignmentsViewCrew: 'assignments.view_crew',
  employeesViewAny: 'employees.view_any',
} as const;
export type CapabilityName = (typeof Capability)[keyof typeof Capability];

export function can(user: CurrentUser | null, ...capabilities: CapabilityName[]): boolean {
  if (!user) return false;
  return capabilities.some((capability) => user.capabilities.includes(capability));
}

/** `can` bound to the signed-in user. */
export function useCan() {
  const { user } = useAuth();
  return (...capabilities: CapabilityName[]) => can(user, ...capabilities);
}

/** Each role group lives under its own path prefix (decision M2). */
const ROLE_BASE: Record<Exclude<Role, 'unknown'>, string> = {
  admin: '/admin',
  manager: '/manager',
  leadhand: '/leadhand',
  worker: '/worker',
};

export function rolePath(role: Role | undefined, path = ''): Href {
  const base = role && role !== 'unknown' ? ROLE_BASE[role] : '';
  return `${base}${path}` as Href;
}

/** Builds hrefs inside the signed-in user's role group, e.g. `to('/jobs/12')`. */
export function useRolePath() {
  const { user } = useAuth();
  return (path = '') => rolePath(user?.role, path);
}
