import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { Alert } from 'react-native';

import type { CurrentUser } from '@/features/auth/schemas';
import { makeAssignment, makeJob, makeUser } from '@/test-utils/fixtures';

import type { AttendanceView } from '../attendance-state';
import type { PunchPayload } from '../punch-events';
import type { PunchOutcome } from '../punch-service';
import { TimeScreen } from './time-screen';

let mockUser: CurrentUser;
let mockView: AttendanceView;
let mockAssignments = [makeAssignment(1), makeAssignment(2)];
const mockJobs = [makeJob({ id: 1 }), makeJob({ id: 2 })];
const mockPunch = jest.fn<Promise<PunchOutcome[]>, [PunchPayload[]]>();

jest.mock('@/features/auth/auth-provider', () => ({ useAuth: () => ({ user: mockUser }) }));
jest.mock('@/lib/location', () => ({
  capturePunchLocation: async () => ({ status: 'unavailable', reason: 'permission_denied' }),
}));
jest.mock('@/lib/ids', () => {
  let n = 0;
  return { newClientId: () => `event-${++n}` };
});
jest.mock('@/features/jobs/hooks', () => ({
  useMyAssignments: () => ({
    data: { data: mockAssignments, fetchedAt: new Date().toISOString(), fromCache: false },
    isPending: false,
    isSuccess: true,
    refetch: jest.fn(),
  }),
  useAssignedJobs: () => ({
    data: { data: mockJobs, fetchedAt: new Date().toISOString(), fromCache: false },
    refetch: jest.fn(),
  }),
}));
jest.mock('../hooks', () => ({
  ...jest.requireActual('../hooks'),
  useAttendanceView: () => ({
    view: mockView,
    status: { data: undefined, refetch: jest.fn(), isRefetching: false, error: null },
    ready: true,
  }),
  usePunch: () => mockPunch,
}));
jest.mock('../components/sync-status', () => ({ SyncStatus: () => null }));

function accept(payload: PunchPayload): PunchOutcome {
  return { kind: 'accepted', payload, result: {} as never };
}

let alertSpy: jest.SpyInstance;
beforeEach(() => {
  mockUser = makeUser('worker');
  mockView = { open: null, provisional: false };
  mockAssignments = [makeAssignment(1), makeAssignment(2)];
  mockPunch.mockReset();
  mockPunch.mockImplementation(async (payloads) => payloads.map(accept));
  // Confirm every dialog by pressing its last button.
  alertSpy = jest
    .spyOn(Alert, 'alert')
    .mockImplementation((_title, _message, buttons) => buttons?.at(-1)?.onPress?.());
});
afterEach(() => alertSpy.mockRestore());

it('explains when the account has no employee record', async () => {
  mockUser = makeUser('worker', { employee: null });
  await render(<TimeScreen />);
  expect(screen.getByText(/No employee record is linked/)).toBeTruthy();
});

it('clocks in to an assigned job', async () => {
  await render(<TimeScreen />);
  expect(screen.getByText('Not clocked in')).toBeTruthy();

  await fireEvent.press(screen.getByTestId('clock-in-2'));

  await waitFor(() => expect(mockPunch).toHaveBeenCalledTimes(1));
  const [payloads] = mockPunch.mock.calls[0]!;
  expect(payloads).toEqual([
    expect.objectContaining({ action_type: 'clock_in', job_id: 2, location: null }),
  ]);
  expect(payloads[0]!.employee_ids).toBeUndefined();
  expect(await screen.findByTestId('punch-notice')).toHaveTextContent(/Clocked in to J-2/);
  expect(alertSpy).not.toHaveBeenCalled();
});

it('says when a punch was saved offline', async () => {
  mockPunch.mockImplementation(async (payloads) =>
    payloads.map((payload) => ({ kind: 'queued', payload, reason: 'offline' })),
  );
  await render(<TimeScreen />);
  await fireEvent.press(screen.getByTestId('clock-in-1'));
  expect(await screen.findByTestId('punch-notice')).toHaveTextContent(/Saved on this phone/);
});

it('asks for confirmation when cached data predicts a rejection, but does not block (M6)', async () => {
  mockAssignments = [makeAssignment(1, { start_date: '2999-01-01' })];
  await render(<TimeScreen />);
  await fireEvent.press(screen.getByTestId('clock-in-1'));

  await waitFor(() => expect(mockPunch).toHaveBeenCalled());
  expect(alertSpy).toHaveBeenCalledWith(
    'Clock in anyway?',
    expect.stringContaining('Your assignment starts on 2999-01-01.'),
    expect.any(Array),
  );
});

it('does not clock in when the warning is cancelled', async () => {
  mockAssignments = [makeAssignment(1, { start_date: '2999-01-01' })];
  alertSpy.mockImplementation((_t, _m, buttons) => buttons?.[0]?.onPress?.());
  await render(<TimeScreen />);
  await fireEvent.press(screen.getByTestId('clock-in-1'));
  expect(mockPunch).not.toHaveBeenCalled();
});

it('switches jobs with one timestamp, clock-out first', async () => {
  mockView = {
    open: { jobId: 1, since: '2026-03-10T07:00:00-04:00', sessionId: 5 },
    provisional: false,
  };
  await render(<TimeScreen />);
  expect(screen.getByText('Clocked in')).toBeTruthy();

  await fireEvent.press(screen.getByTestId('switch-2'));

  await waitFor(() => expect(mockPunch).toHaveBeenCalledTimes(1));
  const [[out, into]] = mockPunch.mock.calls[0]! as [PunchPayload[]];
  expect(out).toMatchObject({ action_type: 'clock_out', job_id: 1 });
  expect(into).toMatchObject({ action_type: 'clock_in', job_id: 2 });
  expect(out!.captured_at).toBe(into!.captured_at);
  expect(out!.event_id).not.toBe(into!.event_id);
  expect(await screen.findByTestId('punch-notice')).toHaveTextContent(/Moved from J-1/);
});

it('offers a manual clock-back-in when the new job refuses the clock-in (M8)', async () => {
  mockView = {
    open: { jobId: 1, since: '2026-03-10T07:00:00-04:00', sessionId: 5 },
    provisional: false,
  };
  mockPunch.mockImplementationOnce(async ([out, into]) => {
    mockView = { open: null, provisional: false };
    return [
      accept(out!),
      {
        kind: 'rejected',
        payload: into!,
        code: 'job_not_active',
        message: 'The job is not active.',
        result: null,
      },
    ];
  });
  const { rerender } = await render(<TimeScreen />);
  await fireEvent.press(screen.getByTestId('switch-2'));

  expect(await screen.findByTestId('punch-notice')).toHaveTextContent(
    /Clocked out of J-1 · Job 1 at .*, but the clock-in at J-2 · Job 2 was refused: The job is not active\./,
  );
  await rerender(<TimeScreen />);
  // Nothing was reversed automatically: only one punch call so far.
  expect(mockPunch).toHaveBeenCalledTimes(1);

  await fireEvent.press(screen.getByTestId('clock-back-in'));
  await waitFor(() => expect(mockPunch).toHaveBeenCalledTimes(2));
  expect(mockPunch.mock.calls[1]![0]).toEqual([
    expect.objectContaining({ action_type: 'clock_in', job_id: 1 }),
  ]);
});

it('clocks out of the open session’s job', async () => {
  mockView = {
    open: { jobId: 2, since: '2026-03-10T07:00:00-04:00', sessionId: null },
    provisional: true,
  };
  await render(<TimeScreen />);
  expect(screen.getByText(/not sent yet/)).toBeTruthy();

  await fireEvent.press(screen.getByTestId('clock-out'));
  await waitFor(() => expect(mockPunch).toHaveBeenCalled());
  expect(mockPunch.mock.calls[0]![0]).toEqual([
    expect.objectContaining({ action_type: 'clock_out', job_id: 2 }),
  ]);
});
