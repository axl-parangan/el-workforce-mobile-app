import { Capability, can } from '@/features/auth/capabilities';
import type { CurrentUser } from '@/features/auth/schemas';

import type { Job } from './schemas';

/**
 * Which job actions to offer. Mirrors the server rules (docs/api/jobs.md);
 * the API still enforces every one of them. LeadHand rights apply only to
 * jobs they manage (`viewer.manages_job`).
 */
export function jobPermissions(user: CurrentUser | null, job: Pick<Job, 'viewer'>) {
  const manages = job.viewer.manages_job;
  const companyWide = can(user, Capability.jobsEditAny);
  return {
    canEdit: companyWide || (can(user, Capability.jobsEditManaged) && manages),
    /** LeadHands may only change name, address and dates (Q3). */
    editsAllFields: companyWide,
    canRecordCrew:
      can(user, Capability.attendanceRecordAny) ||
      (can(user, Capability.attendanceRecordCrew) && manages),
    /** Manager/Admin group punches are online-only (M7); LeadHand ones can be queued. */
    crewPunchesOnlineOnly: can(user, Capability.attendanceRecordAny),
    canViewAssignments:
      can(user, Capability.assignmentsManage) ||
      (can(user, Capability.assignmentsViewCrew) && manages),
    canManageAssignments: can(user, Capability.assignmentsManage),
    canDesignateLeadHand: can(user, Capability.assignmentsManage),
    canViewAttendance:
      can(user, Capability.attendanceViewAny) ||
      (can(user, Capability.attendanceViewCrew) && manages),
  };
}

export type JobPermissions = ReturnType<typeof jobPermissions>;

/** Fields a LeadHand may send when creating or editing a job (Q3). */
export const LEADHAND_JOB_FIELDS = ['job_number', 'name', 'address', 'start_date', 'end_date'];
