import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';

import { ApiError } from '@/api/errors';

import { SignInScreen } from './sign-in-screen';

const mockSignIn = jest.fn();

let mockWaiting = 0;

jest.mock('../auth-provider', () => ({
  useAuth: () => ({ signIn: mockSignIn }),
}));
jest.mock('@/offline/hooks', () => ({
  useOutboxCounts: () => ({
    data: { unsynced: 0, recentlyRejected: 0, otherAccounts: mockWaiting },
  }),
}));

beforeEach(() => {
  mockSignIn.mockReset();
  mockWaiting = 0;
});

it('validates the form before calling the API', async () => {
  await render(<SignInScreen />);

  await fireEvent.press(screen.getByTestId('sign-in-submit'));

  expect(screen.getByText('Enter a valid email address.')).toBeTruthy();
  expect(screen.getByText('Enter your password.')).toBeTruthy();
  expect(mockSignIn).not.toHaveBeenCalled();
});

it('signs in with a normalised email', async () => {
  mockSignIn.mockResolvedValue(undefined);
  await render(<SignInScreen />);

  await fireEvent.changeText(screen.getByLabelText('Email'), '  Wendy@Example.com ');
  await fireEvent.changeText(screen.getByLabelText('Password'), 'secret');
  await fireEvent.press(screen.getByTestId('sign-in-submit'));

  await waitFor(() =>
    expect(mockSignIn).toHaveBeenCalledWith({ email: 'wendy@example.com', password: 'secret' }),
  );
});

it('shows a friendly message for wrong credentials', async () => {
  mockSignIn.mockRejectedValue(new ApiError(401, 'no_active_account', 'No active account'));
  await render(<SignInScreen />);

  await fireEvent.changeText(screen.getByLabelText('Email'), 'wendy@example.com');
  await fireEvent.changeText(screen.getByLabelText('Password'), 'wrong');
  await fireEvent.press(screen.getByTestId('sign-in-submit'));

  expect(await screen.findByText('Email or password is incorrect.')).toBeTruthy();
});

it('explains punches waiting for the account that recorded them', async () => {
  mockWaiting = 2;
  await render(<SignInScreen />);

  expect(screen.getByTestId('sign-in-waiting')).toHaveTextContent(
    '2 punches on this phone are waiting to be sent. They are sent only after the account that recorded them signs in again.',
  );
});
