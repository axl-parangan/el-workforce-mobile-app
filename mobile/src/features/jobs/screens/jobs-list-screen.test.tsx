import { fireEvent, render, screen } from '@testing-library/react-native';

import type { CurrentUser } from '@/features/auth/schemas';
import { makeJob, makeUser } from '@/test-utils/fixtures';

import { JobsListScreen } from './jobs-list-screen';

let mockUser: CurrentUser;
const mockPush = jest.fn();
const mockAssigned = jest.fn();
const mockList = jest.fn();

jest.mock('@/features/auth/auth-provider', () => ({ useAuth: () => ({ user: mockUser }) }));
jest.mock('expo-router', () => ({ useRouter: () => ({ push: mockPush }) }));
jest.mock('../hooks', () => ({
  useAssignedJobs: () => mockAssigned(),
  useJobList: (params: unknown, enabled: boolean) => mockList(params, enabled),
}));

const jobs = [
  makeJob({ id: 1, name: 'Warehouse' }, { manages_job: true }),
  makeJob({ id: 2, name: 'Tower' }),
];

function cachedResult(fetchedAt: string, fromCache: boolean) {
  return {
    data: { data: jobs, fetchedAt, fromCache },
    isPending: false,
    isSuccess: true,
    isRefetching: false,
    error: null,
    refetch: jest.fn(),
  };
}

beforeEach(() => {
  jest.clearAllMocks();
  mockList.mockReturnValue({ data: undefined, isPending: true, refetch: jest.fn() });
});

it('shows an Employee their assigned jobs, without crew filters or job creation', async () => {
  mockUser = makeUser('worker');
  mockAssigned.mockReturnValue(cachedResult(new Date().toISOString(), false));

  await render(<JobsListScreen />);

  expect(screen.getByText('J-1 · Warehouse')).toBeTruthy();
  expect(screen.getByText('J-2 · Tower')).toBeTruthy();
  expect(screen.queryByText('I lead')).toBeNull();
  expect(screen.queryByTestId('new-job')).toBeNull();
  expect(screen.queryByLabelText('Search')).toBeNull();
  expect(mockList).not.toHaveBeenCalled();

  await fireEvent.press(screen.getByTestId('job-2'));
  expect(mockPush).toHaveBeenCalledWith('/worker/jobs/2');
});

it('lets a LeadHand filter to the jobs they lead', async () => {
  mockUser = makeUser('leadhand');
  mockAssigned.mockReturnValue(cachedResult(new Date().toISOString(), false));

  await render(<JobsListScreen />);
  await fireEvent.press(screen.getByText('I lead'));

  expect(screen.getByText('J-1 · Warehouse')).toBeTruthy();
  expect(screen.queryByText('J-2 · Tower')).toBeNull();
  expect(screen.getByTestId('new-job')).toBeTruthy();
});

it('warns when the offline copy is older than 24 hours, without blocking (M6)', async () => {
  mockUser = makeUser('worker');
  mockAssigned.mockReturnValue(cachedResult('2020-01-01T00:00:00Z', true));

  await render(<JobsListScreen />);

  expect(screen.getByTestId('cache-stale')).toBeTruthy();
  expect(screen.getByText('J-1 · Warehouse')).toBeTruthy();
});

it('shows recent offline data with an offline notice', async () => {
  mockUser = makeUser('worker');
  mockAssigned.mockReturnValue(cachedResult(new Date().toISOString(), true));

  await render(<JobsListScreen />);

  expect(screen.getByTestId('cache-offline')).toBeTruthy();
});

it('gives Managers a company-wide search instead of the assigned list', async () => {
  mockUser = makeUser('manager');
  mockList.mockReturnValue({
    data: { count: 2, next: null, previous: null, results: jobs },
    isPending: false,
    isSuccess: true,
    isRefetching: false,
    error: null,
    refetch: jest.fn(),
  });

  await render(<JobsListScreen />);

  expect(screen.getByLabelText('Search')).toBeTruthy();
  expect(mockList).toHaveBeenLastCalledWith({ search: undefined, status: 'active' }, true);
  expect(mockAssigned).not.toHaveBeenCalled();
  await fireEvent.changeText(screen.getByLabelText('Search'), 'tow');
  expect(mockList).toHaveBeenLastCalledWith({ search: 'tow', status: 'active' }, true);
});
