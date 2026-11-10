import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';

import { NetworkError } from '@/api/errors';
import type { CurrentUser } from '@/features/auth/schemas';
import type { PunchPayload } from '@/features/timekeeping/punch-events';
import type { Crew } from '@/features/timekeeping/schemas';
import { makeJob, makeUser } from '@/test-utils/fixtures';

import { CrewScreen } from './crew-screen';

let mockUser: CurrentUser;
let mockManages = true;
const mockPunch = jest.fn();
const mockSubmit = jest.fn();

const mockCrew: Crew = {
  job: { id: 1, job_number: 'J-1' },
  crew: [
    {
      employee: { id: 30, name: 'Ana', has_account: true },
      assignment_id: 1,
      clocked_in: false,
      open_session: null,
    },
    {
      employee: { id: 40, name: 'Field Hand', has_account: false },
      assignment_id: 2,
      clocked_in: true,
      open_session: { id: 9, job: { id: 1, job_number: 'J-1', name: 'Job 1' }, clock_in_at: null },
    },
  ],
};

jest.mock('@/features/auth/auth-provider', () => ({ useAuth: () => ({ user: mockUser }) }));
jest.mock('expo-router', () => ({
  Stack: { Screen: () => null },
  useLocalSearchParams: () => ({ id: '1' }),
}));
jest.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: jest.fn() }),
}));
jest.mock('@/lib/location', () => ({
  capturePunchLocation: async () => ({ status: 'unavailable', reason: 'timeout' }),
}));
jest.mock('@/lib/ids', () => {
  let n = 0;
  return { newClientId: () => `event-${++n}` };
});
jest.mock('@/features/jobs/hooks', () => ({
  useJob: () => ({
    data: { data: mockJobFor(), fetchedAt: new Date().toISOString(), fromCache: false },
    isPending: false,
  }),
}));
jest.mock('@/features/timekeeping/hooks', () => ({
  ...jest.requireActual('@/features/timekeeping/hooks'),
  useCrew: () => ({
    data: { data: mockCrew, fetchedAt: new Date().toISOString(), fromCache: false },
    isPending: false,
    isSuccess: true,
    refetch: jest.fn(),
  }),
  usePunch: () => mockPunch,
}));
jest.mock('@/features/timekeeping/api', () => ({
  submitPunch: (payload: unknown) => mockSubmit(payload),
}));
jest.mock('@/features/timekeeping/components/sync-status', () => ({ SyncStatus: () => null }));

function mockJobFor() {
  return makeJob({ id: 1 }, { manages_job: mockManages });
}

function batchFor(payload: PunchPayload) {
  return {
    action_type: payload.action_type,
    results: payload.employee_ids!.map((id) => ({
      employee: { id, name: `Employee ${id}` },
      status: id === 40 ? 'rejected' : 'accepted',
      code: id === 40 ? 'already_clocked_in' : 'clocked_in',
      message: id === 40 ? 'Already clocked in.' : 'Clocked in.',
      session_id: null,
      punch_id: null,
      processed_at: null,
    })),
  };
}

beforeEach(() => {
  mockPunch.mockReset();
  mockSubmit.mockReset();
  mockManages = true;
});

it('refuses a LeadHand on a job they do not manage', async () => {
  mockUser = makeUser('leadhand');
  mockManages = false;
  await render(<CrewScreen />);
  expect(screen.getByText(/Only the LeadHand who manages this job/)).toBeTruthy();
  expect(screen.queryByTestId('crew-clock-in')).toBeNull();
});

it('refuses Employees', async () => {
  mockUser = makeUser('worker');
  await render(<CrewScreen />);
  expect(screen.queryByTestId('crew-clock-in')).toBeNull();
});

it('lets a LeadHand group-punch selected employees through the outbox, with per-employee results', async () => {
  mockUser = makeUser('leadhand');
  mockPunch.mockImplementation(async ([payload]: PunchPayload[]) => [
    { kind: 'accepted', payload, result: batchFor(payload!) },
  ]);
  await render(<CrewScreen />);

  await fireEvent.press(screen.getByTestId('crew-30'));
  await fireEvent.press(screen.getByTestId('crew-40'));
  await fireEvent.press(screen.getByTestId('crew-clock-in'));

  await waitFor(() => expect(mockPunch).toHaveBeenCalled());
  const [[payload]] = mockPunch.mock.calls[0] as [PunchPayload[]];
  expect(payload).toMatchObject({ action_type: 'clock_in', job_id: 1, employee_ids: [30, 40] });
  expect(payload!.reason).toBeUndefined();
  expect(mockSubmit).not.toHaveBeenCalled();
  expect(await screen.findByText('Clock-in: 1 of 2 accepted')).toBeTruthy();
  expect(screen.getByText('✕ Employee 40: Already clocked in.')).toBeTruthy();
});

it('tells a LeadHand an offline group punch was saved', async () => {
  mockUser = makeUser('leadhand');
  mockPunch.mockImplementation(async ([payload]: PunchPayload[]) => [
    { kind: 'queued', payload, reason: 'offline' },
  ]);
  await render(<CrewScreen />);
  await fireEvent.press(screen.getByTestId('crew-30'));
  await fireEvent.press(screen.getByTestId('crew-clock-out'));
  expect(await screen.findByTestId('crew-result')).toHaveTextContent(/Saved on this phone for 1/);
});

it('keeps Manager group punches online-only and retries with the same event id (M7)', async () => {
  mockUser = makeUser('manager');
  mockSubmit.mockRejectedValueOnce(new NetworkError());
  mockSubmit.mockImplementationOnce(async (payload: PunchPayload) => batchFor(payload));
  await render(<CrewScreen />);

  await fireEvent.changeText(screen.getByLabelText('Reason (optional)'), 'Phone was dead');
  await fireEvent.press(screen.getByTestId('crew-30'));
  await fireEvent.press(screen.getByTestId('crew-clock-in'));

  expect(await screen.findByTestId('crew-result')).toHaveTextContent(/need a connection/);
  expect(mockPunch).not.toHaveBeenCalled();

  await fireEvent.press(screen.getByTestId('crew-retry'));
  await waitFor(() => expect(mockSubmit).toHaveBeenCalledTimes(2));
  const [first, second] = mockSubmit.mock.calls.map(([p]) => p as PunchPayload);
  expect(second).toEqual(first);
  expect(first).toMatchObject({ employee_ids: [30], reason: 'Phone was dead' });
  expect(await screen.findByText('Clock-in: 1 of 1 accepted')).toBeTruthy();
});
