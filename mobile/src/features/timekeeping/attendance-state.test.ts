import type { PendingEvent } from '@/offline/queue/pending-events';
import { makeAssignment, makeJob } from '@/test-utils/fixtures';

import { deriveAttendance } from './attendance-state';
import { clockInWarnings } from './eligibility';
import type { PunchPayload } from './punch-events';
import type { AttendanceStatus } from './schemas';

let sequence = 0;
function event(
  action: PunchPayload['action_type'],
  at: string,
  jobId: number,
  overrides: Partial<PendingEvent> = {},
  extra: Partial<PunchPayload> = {},
): PendingEvent {
  sequence += 1;
  const id = `e${sequence}`;
  return {
    id,
    type: 'punch',
    payload: {
      event_id: id,
      action_type: action,
      job_id: jobId,
      captured_at: at,
      location: null,
      ...extra,
    },
    status: 'pending',
    attempts: 0,
    lastError: null,
    outcome: null,
    userId: 1,
    sequence,
    createdAt: at,
    updatedAt: at,
    ...overrides,
  };
}

const openOnJob1: AttendanceStatus = {
  employee: { id: 10, name: 'Wendy' },
  clocked_in: true,
  open_session: {
    id: 5,
    employee: { id: 10, name: 'Wendy' },
    job: { id: 1, job_number: 'J-1', name: 'Job 1' },
    work_date: '2026-03-10',
    session_status: 'open',
    review_status: 'not_required',
    exception_flags: [],
    clock_in: {
      punch_id: 1,
      at: '2026-03-10T07:00:00-04:00',
      received_at: '2026-03-10T07:00:00-04:00',
      event_id: 'x',
      source: 'mobile_online',
      performed_by: null,
      location: {
        status: 'verified',
        flags: [],
        requires_review: false,
        latitude: null,
        longitude: null,
        accuracy_meters: null,
        distance_meters: null,
      },
    },
    clock_out: null,
    duration_seconds: null,
    reviewed_by: null,
    reviewed_at: null,
  },
};
const notClockedIn: AttendanceStatus = { ...openOnJob1, clocked_in: false, open_session: null };

describe('deriveAttendance', () => {
  const base = { statusFetchedAt: '2026-03-10T09:00:00.000Z', employeeId: 10 };

  it('uses the server status when nothing is pending', () => {
    expect(deriveAttendance({ ...base, status: openOnJob1, events: [] })).toEqual({
      open: { jobId: 1, since: '2026-03-10T07:00:00-04:00', sessionId: 5 },
      provisional: false,
    });
  });

  it('applies unsynced punches on top, provisionally', () => {
    const view = deriveAttendance({
      ...base,
      status: notClockedIn,
      events: [event('clock_in', '2026-03-10T08:00:00-04:00', 2)],
    });
    expect(view).toEqual({
      open: { jobId: 2, since: '2026-03-10T08:00:00-04:00', sessionId: null },
      provisional: true,
    });
  });

  it('applies a queued job switch in server order', () => {
    const view = deriveAttendance({
      ...base,
      status: openOnJob1,
      events: [
        event('clock_out', '2026-03-10T10:30:00-04:00', 1),
        event('clock_in', '2026-03-10T10:30:00-04:00', 2),
      ],
    });
    expect(view.open).toMatchObject({ jobId: 2, since: '2026-03-10T10:30:00-04:00' });
  });

  it('includes punches accepted after the snapshot, ignores older and refused ones', () => {
    const accepted = (employeeId: number) => ({
      code: 'clocked_out',
      message: '',
      results: [
        {
          employeeId,
          employee: 'Wendy',
          status: 'accepted' as const,
          code: 'clocked_out',
          message: '',
        },
      ],
    });
    const after = deriveAttendance({
      ...base,
      status: openOnJob1,
      events: [
        event('clock_out', '2026-03-10T10:00:00-04:00', 1, {
          status: 'synced',
          updatedAt: '2026-03-10T14:00:00.000Z',
          outcome: accepted(10),
        }),
      ],
    });
    expect(after).toEqual({ open: null, provisional: false });

    const before = deriveAttendance({
      ...base,
      status: openOnJob1,
      events: [
        event('clock_out', '2026-03-10T04:00:00-04:00', 1, {
          status: 'synced',
          updatedAt: '2026-03-10T08:30:00.000Z',
          outcome: accepted(10),
        }),
        event('clock_out', '2026-03-10T10:00:00-04:00', 1, {
          status: 'rejected',
          updatedAt: '2026-03-10T14:00:00.000Z',
        }),
      ],
    });
    expect(before.open).not.toBeNull();
  });

  it('counts a group punch only when it included this employee', () => {
    const others = event(
      'clock_in',
      '2026-03-10T08:00:00-04:00',
      3,
      {},
      { employee_ids: [30, 40] },
    );
    const mine = event('clock_in', '2026-03-10T08:00:00-04:00', 3, {}, { employee_ids: [10, 40] });
    expect(deriveAttendance({ ...base, status: notClockedIn, events: [others] }).open).toBeNull();
    expect(deriveAttendance({ ...base, status: notClockedIn, events: [mine] }).open).toMatchObject({
      jobId: 3,
    });
  });
});

describe('clockInWarnings', () => {
  const workDate = '2026-03-10';

  it('has no warnings for an active assignment on an active job', () => {
    expect(clockInWarnings({ assignment: makeAssignment(1), job: makeJob(), workDate })).toEqual(
      [],
    );
  });

  it('warns about assignment dates and job status', () => {
    expect(
      clockInWarnings({
        assignment: makeAssignment(1, { start_date: '2026-03-11' }),
        job: makeJob({ status: 'on_hold' }),
        workDate,
      }),
    ).toEqual(['Your assignment starts on 2026-03-11.', 'This job is on hold.']);
    expect(
      clockInWarnings({
        assignment: makeAssignment(1, { end_date: '2026-03-09' }),
        job: undefined,
        workDate,
      }),
    ).toEqual(['Your assignment ended on 2026-03-09.']);
    expect(clockInWarnings({ assignment: undefined, job: undefined, workDate })).toEqual([
      'You do not have an active assignment to this job.',
    ]);
  });
});
