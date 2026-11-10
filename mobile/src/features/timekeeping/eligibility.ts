import type { Assignment, Job } from '@/features/jobs/schemas';
import { JOB_STATUS_LABELS } from '@/features/jobs/schemas';

/**
 * Client-side hints before a clock-in, from cached data. They never block on
 * their own: the user may confirm and the server decides (M6). They exist so
 * an employee is not surprised by a rejection that is visible in advance.
 */
export function clockInWarnings({
  assignment,
  job,
  workDate,
}: {
  assignment: Assignment | undefined;
  job: Job | undefined;
  /** Today in the company timezone (YYYY-MM-DD). */
  workDate: string;
}): string[] {
  const warnings: string[] = [];
  if (!assignment || assignment.status !== 'active') {
    warnings.push('You do not have an active assignment to this job.');
  } else {
    if (assignment.start_date && workDate < assignment.start_date) {
      warnings.push(`Your assignment starts on ${assignment.start_date}.`);
    }
    if (assignment.end_date && workDate > assignment.end_date) {
      warnings.push(`Your assignment ended on ${assignment.end_date}.`);
    }
  }
  if (job && job.status !== 'active') {
    warnings.push(`This job is ${JOB_STATUS_LABELS[job.status].toLowerCase()}.`);
  }
  return warnings;
}
