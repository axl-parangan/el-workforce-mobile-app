import { ApiError, NetworkError, ResponseValidationError, UserFacingError } from './errors';

/** Friendly wording for server error codes the user can act on. */
const CODE_MESSAGES: Record<string, string> = {
  no_active_account: 'Email or password is incorrect.',
  no_active_assignment: 'You are not assigned to this job.',
  assignment_not_in_effect: 'Your assignment to this job is not in effect today.',
  job_not_active: 'This job is not active.',
  employee_inactive: 'This employee is inactive.',
  already_clocked_in: 'Already clocked in to another session.',
  no_open_session: 'There is no open session to clock out of.',
  open_session_on_other_job: 'The open session is on a different job.',
  not_job_lead_hand: 'You do not manage this job.',
  admin_entry_not_current: 'This entry is too old to record. Use a correction instead.',
  cannot_review_own_timesheet: 'You cannot review your own timesheet.',
  field_not_editable: 'You are not allowed to change some of these fields.',
  job_not_editable: 'You are not allowed to edit this job.',
  job_not_assignable: 'This job does not accept new assignments.',
  not_eligible_lead_hand: 'Only an active LeadHand can lead a job.',
  assignment_not_active: 'This assignment is no longer active.',
  assignment_has_sessions: 'This assignment has attendance. End it instead of cancelling.',
  end_date_in_future: 'The end date cannot be in the future.',
};

export function messageForCode(code: string, fallback?: string): string {
  return CODE_MESSAGES[code] ?? fallback ?? 'Something went wrong.';
}

/** A short, user-facing explanation of any error thrown by the API layer. */
export function describeError(error: unknown): string {
  if (error instanceof UserFacingError) return error.message;
  if (error instanceof NetworkError) {
    return 'You are offline or the server cannot be reached. Try again when connected.';
  }
  if (error instanceof ApiError) {
    if (error.code === 'validation_error' && error.details && typeof error.details === 'object') {
      const first = Object.entries(error.details as Record<string, unknown>)[0];
      if (first) {
        const [field, messages] = first;
        const text = Array.isArray(messages) ? String(messages[0]) : String(messages);
        return `${field.replace(/_/g, ' ')}: ${text}`;
      }
    }
    return messageForCode(error.code, error.message);
  }
  if (error instanceof ResponseValidationError) {
    return 'The server sent an unexpected response. Please update the app.';
  }
  return 'Something went wrong.';
}
