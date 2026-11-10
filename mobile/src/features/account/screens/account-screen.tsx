import { useState } from 'react';
import { Alert } from 'react-native';

import { Body, Button, Card, Heading, Screen } from '@/components/ui';
import { useAuth } from '@/features/auth/auth-provider';
import { ROLE_LABELS } from '@/features/auth/schemas';
import { SyncStatus } from '@/features/timekeeping/components/sync-status';
import { useOutboxCounts } from '@/offline/hooks';

export const SIGN_OUT_WITH_PENDING_MESSAGE = (count: number) =>
  `${count === 1 ? '1 punch' : `${count} punches`} recorded with this account ${
    count === 1 ? 'has' : 'have'
  } not been sent yet. ${count === 1 ? 'It stays' : 'They stay'} on this phone and will be sent the next time you sign in with this account. Another account signing in on this phone will not send ${
    count === 1 ? 'it' : 'them'
  }.`;

export function AccountScreen() {
  const { user, signOut } = useAuth();
  const counts = useOutboxCounts();
  const [busy, setBusy] = useState(false);

  if (!user) return null;
  const fullName = [user.first_name, user.last_name].filter(Boolean).join(' ');

  async function doSignOut() {
    setBusy(true);
    try {
      await signOut();
    } finally {
      setBusy(false);
    }
  }

  function requestSignOut() {
    const unsynced = counts.data?.unsynced ?? 0;
    if (unsynced === 0) {
      void doSignOut();
      return;
    }
    // M10: warn and confirm; pending punches are never deleted.
    Alert.alert('Punches not sent yet', SIGN_OUT_WITH_PENDING_MESSAGE(unsynced), [
      { text: 'Stay signed in', style: 'cancel' },
      { text: 'Sign out', style: 'destructive', onPress: () => void doSignOut() },
    ]);
  }

  return (
    <Screen>
      <Card>
        <Heading>{user.employee?.name ?? (fullName || user.email)}</Heading>
        <Body muted>{user.email}</Body>
        <Body>Role: {ROLE_LABELS[user.role]}</Body>
        {user.employee ? null : (
          <Body muted>No employee record is linked to this account, so you cannot clock in.</Body>
        )}
      </Card>
      <SyncStatus showWhenClear />
      <Button
        label="Sign out"
        variant="secondary"
        busy={busy}
        testID="sign-out"
        onPress={requestSignOut}
      />
    </Screen>
  );
}
