import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { Alert } from 'react-native';

import { makeUser } from '@/test-utils/fixtures';

import { AccountScreen, SIGN_OUT_WITH_PENDING_MESSAGE } from './account-screen';

const mockSignOut = jest.fn(async () => undefined);
const mockUser = makeUser('leadhand');
let mockUnsynced = 0;

jest.mock('@/features/auth/auth-provider', () => ({
  useAuth: () => ({ user: mockUser, signOut: mockSignOut }),
}));
jest.mock('@/offline/hooks', () => ({
  useOutboxCounts: () => ({
    data: { unsynced: mockUnsynced, recentlyRejected: 0, otherAccounts: 0 },
    isSuccess: true,
  }),
}));
jest.mock('@/features/timekeeping/components/sync-status', () => ({ SyncStatus: () => null }));

let alertSpy: jest.SpyInstance;
beforeEach(() => {
  mockSignOut.mockClear();
  alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => undefined);
});
afterEach(() => alertSpy.mockRestore());

it('signs out straight away when nothing is waiting', async () => {
  mockUnsynced = 0;
  await render(<AccountScreen />);
  await fireEvent.press(screen.getByTestId('sign-out'));
  await waitFor(() => expect(mockSignOut).toHaveBeenCalled());
  expect(alertSpy).not.toHaveBeenCalled();
});

it('warns and requires confirmation with unsent punches (M10)', async () => {
  mockUnsynced = 2;
  await render(<AccountScreen />);
  await fireEvent.press(screen.getByTestId('sign-out'));

  expect(mockSignOut).not.toHaveBeenCalled();
  expect(alertSpy).toHaveBeenCalledWith(
    'Punches not sent yet',
    SIGN_OUT_WITH_PENDING_MESSAGE(2),
    expect.any(Array),
  );
  expect(SIGN_OUT_WITH_PENDING_MESSAGE(2)).toMatch(/stay on this phone/);

  const buttons = alertSpy.mock.calls[0]![2] as { text: string; onPress?: () => void }[];
  expect(buttons.map((b) => b.text)).toEqual(['Stay signed in', 'Sign out']);
  await act(async () => buttons[1]!.onPress!());
  await waitFor(() => expect(mockSignOut).toHaveBeenCalled());
});
