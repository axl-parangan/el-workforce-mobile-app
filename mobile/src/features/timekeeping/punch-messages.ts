import { formatTime } from '@/lib/company-time';

import type { PunchOutcome } from './punch-service';

export type Notice = {
  tone: 'success' | 'info' | 'warning' | 'danger';
  text: string;
  /** M8: offered after clocking out of a job when the clock-in at the next job was refused. */
  clockBackIn?: { jobId: number; label: string };
};

type Label = (jobId: number) => string;

const QUEUED = 'Saved on this phone. It will be sent automatically when you are back online.';

export function noticeForPunch(outcome: PunchOutcome, label: Label): Notice {
  const job = label(outcome.payload.job_id);
  const at = formatTime(outcome.payload.captured_at);
  const verb = outcome.payload.action_type === 'clock_in' ? 'Clocked in to' : 'Clocked out of';
  switch (outcome.kind) {
    case 'accepted':
      return { tone: 'success', text: `${verb} ${job} at ${at}.` };
    case 'queued':
      return { tone: 'info', text: `${verb} ${job} at ${at}. ${QUEUED}` };
    case 'rejected':
      return { tone: 'danger', text: `Not recorded: ${outcome.message}` };
  }
}

/** A job switch is a clock-out at A then a clock-in at B with the same time. */
export function noticeForSwitch([out, into]: [PunchOutcome, PunchOutcome], label: Label): Notice {
  const from = label(out.payload.job_id);
  const to = label(into.payload.job_id);
  const at = formatTime(out.payload.captured_at);

  if (out.kind === 'rejected') {
    const next =
      into.kind === 'accepted'
        ? ` You are now clocked in to ${to}.`
        : into.kind === 'rejected'
          ? ` The clock-in at ${to} was also refused: ${into.message}`
          : '';
    return { tone: 'danger', text: `Could not clock out of ${from}: ${out.message}${next}` };
  }
  if (into.kind === 'rejected') {
    // Never reversed automatically (M8): the employee decides.
    return {
      tone: 'danger',
      text: `Clocked out of ${from} at ${at}, but the clock-in at ${to} was refused: ${into.message}`,
      clockBackIn: { jobId: out.payload.job_id, label: from },
    };
  }
  if (out.kind === 'accepted' && into.kind === 'accepted') {
    return { tone: 'success', text: `Moved from ${from} to ${to} at ${at}.` };
  }
  return { tone: 'info', text: `Moved from ${from} to ${to} at ${at}. ${QUEUED}` };
}
