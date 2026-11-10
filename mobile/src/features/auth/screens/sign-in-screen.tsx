import { useState } from 'react';

import { describeError } from '@/api/error-messages';
import { Banner, Body, Button, Screen, TextField } from '@/components/ui';
import { useOutboxCounts } from '@/offline/hooks';

import { useAuth } from '../auth-provider';
import { credentialsSchema } from '../schemas';

/** Email + password sign-in (ADR 007). */
export function SignInScreen() {
  const { signIn } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Signed out, every unsent punch belongs to some account that must sign in to send it.
  const waiting = useOutboxCounts().data?.otherAccounts ?? 0;

  async function submit() {
    setError(null);
    const parsed = credentialsSchema.safeParse({ email, password });
    if (!parsed.success) {
      const issues = parsed.error.issues;
      setFieldErrors({
        email: issues.some((i) => i.path[0] === 'email')
          ? 'Enter a valid email address.'
          : undefined,
        password: issues.some((i) => i.path[0] === 'password') ? 'Enter your password.' : undefined,
      });
      return;
    }
    setFieldErrors({});
    setBusy(true);
    try {
      await signIn(parsed.data);
    } catch (caught) {
      setError(describeError(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen title="Sign in" topInset>
      <Body muted>Use the email address your manager registered for you.</Body>
      {waiting > 0 ? (
        <Banner tone="info" testID="sign-in-waiting">
          {waiting === 1 ? '1 punch' : `${waiting} punches`} on this phone{' '}
          {waiting === 1 ? 'is' : 'are'} waiting to be sent. They are sent only after the account
          that recorded them signs in again.
        </Banner>
      ) : null}
      {error ? (
        <Banner tone="danger" testID="sign-in-error">
          {error}
        </Banner>
      ) : null}
      <TextField
        label="Email"
        value={email}
        onChangeText={setEmail}
        autoCapitalize="none"
        autoComplete="email"
        keyboardType="email-address"
        textContentType="emailAddress"
        error={fieldErrors.email}
      />
      <TextField
        label="Password"
        value={password}
        onChangeText={setPassword}
        secureTextEntry
        autoComplete="password"
        textContentType="password"
        error={fieldErrors.password}
        onSubmitEditing={submit}
      />
      <Button label="Sign in" onPress={submit} busy={busy} testID="sign-in-submit" />
    </Screen>
  );
}
