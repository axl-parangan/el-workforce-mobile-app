import { render, screen } from '@testing-library/react-native';

import type { CurrentUser } from '@/features/auth/schemas';
import type { Job } from '@/features/jobs/schemas';
import { makeJob, makeUser } from '@/test-utils/fixtures';

import { JobDetailScreen } from './job-detail-screen';

let mockUser: CurrentUser;
let mockJob: Job;

jest.mock('@/features/auth/auth-provider', () => ({ useAuth: () => ({ user: mockUser }) }));
jest.mock('expo-router', () => ({
  Stack: { Screen: () => null },
  useLocalSearchParams: () => ({ id: '1' }),
  useRouter: () => ({ push: jest.fn() }),
}));
jest.mock('../hooks', () => ({
  useJob: () => ({
    data: { data: mockJob, fetchedAt: new Date().toISOString(), fromCache: false },
    isPending: false,
    isError: false,
    refetch: jest.fn(),
  }),
  useAssignedJobs: () => ({ data: undefined }),
}));

const ACTIONS = ['open-crew', 'open-assignments', 'open-attendance', 'open-lead-hand', 'edit-job'];

function visibleActions() {
  return ACTIONS.filter((id) => screen.queryByTestId(id));
}

it('shows Employees the job but no crew or management actions', async () => {
  mockUser = makeUser('worker');
  mockJob = makeJob({ name: 'Warehouse' });
  await render(<JobDetailScreen />);
  expect(screen.getByText('Warehouse')).toBeTruthy();
  expect(screen.getByText('You are assigned to this job.')).toBeTruthy();
  expect(visibleActions()).toEqual([]);
});

it('shows LeadHands crew actions only on jobs they manage', async () => {
  mockUser = makeUser('leadhand');
  mockJob = makeJob({}, { manages_job: true, is_lead_hand: true });
  await render(<JobDetailScreen />);
  expect(visibleActions()).toEqual([
    'open-crew',
    'open-assignments',
    'open-attendance',
    'edit-job',
  ]);
  expect(screen.getByText('Crew assignments')).toBeTruthy();
});

it('shows a LeadHand nothing extra on a job they work on but do not manage', async () => {
  mockUser = makeUser('leadhand');
  mockJob = makeJob({}, { manages_job: false });
  await render(<JobDetailScreen />);
  expect(visibleActions()).toEqual([]);
});

it.each(['manager', 'admin'] as const)('shows %s every management action', async (role) => {
  mockUser = makeUser(role);
  mockJob = makeJob({}, { manages_job: false, my_assignment_id: null });
  await render(<JobDetailScreen />);
  expect(visibleActions()).toEqual(ACTIONS);
  expect(screen.getByText('Manage assignments')).toBeTruthy();
});
