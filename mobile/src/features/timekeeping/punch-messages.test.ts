import type { PunchPayload } from './punch-events';
import { noticeForPunch, noticeForSwitch } from './punch-messages';
import type { PunchOutcome } from './punch-service';

const label = (jobId: number) => `J-${jobId}`;
const at = '2026-03-10T10:30:00-04:00';
const payload = (action: PunchPayload['action_type'], jobId: number): PunchPayload => ({
  event_id: `${action}-${jobId}`,
  action_type: action,
  job_id: jobId,
  captured_at: at,
  location: null,
});
const accepted = (p: PunchPayload): PunchOutcome => ({
  kind: 'accepted',
  payload: p,
  result: {} as never,
});
const queued = (p: PunchPayload): PunchOutcome => ({
  kind: 'queued',
  payload: p,
  reason: 'offline',
});
const rejected = (p: PunchPayload, message: string): PunchOutcome => ({
  kind: 'rejected',
  payload: p,
  code: 'x',
  message,
  result: null,
});

it('describes single punches', () => {
  expect(noticeForPunch(accepted(payload('clock_in', 1)), label)).toEqual({
    tone: 'success',
    text: 'Clocked in to J-1 at 10:30.',
  });
  expect(noticeForPunch(queued(payload('clock_out', 1)), label).text).toMatch(
    /^Clocked out of J-1 at 10:30\. Saved on this phone/,
  );
  expect(noticeForPunch(rejected(payload('clock_in', 1), 'Nope.'), label)).toEqual({
    tone: 'danger',
    text: 'Not recorded: Nope.',
  });
});

describe('noticeForSwitch', () => {
  const out = payload('clock_out', 1);
  const into = payload('clock_in', 2);

  it('confirms a completed move', () => {
    expect(noticeForSwitch([accepted(out), accepted(into)], label)).toEqual({
      tone: 'success',
      text: 'Moved from J-1 to J-2 at 10:30.',
    });
  });

  it('explains a move saved offline', () => {
    expect(noticeForSwitch([queued(out), queued(into)], label).tone).toBe('info');
  });

  it('offers clock-back-in only when the clock-out succeeded and the clock-in was refused (M8)', () => {
    const notice = noticeForSwitch([accepted(out), rejected(into, 'Not assigned.')], label);
    expect(notice.clockBackIn).toEqual({ jobId: 1, label: 'J-1' });
    expect(notice.text).toBe(
      'Clocked out of J-1 at 10:30, but the clock-in at J-2 was refused: Not assigned.',
    );

    const failedOut = noticeForSwitch([rejected(out, 'No open session.'), accepted(into)], label);
    expect(failedOut.clockBackIn).toBeUndefined();
    expect(failedOut.text).toBe(
      'Could not clock out of J-1: No open session. You are now clocked in to J-2.',
    );
  });
});
