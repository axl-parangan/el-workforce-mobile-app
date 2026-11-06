import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';

import { AppProviders } from '@/components/app-providers';
import { useAuth } from '@/features/auth/auth-provider';

export default function RootLayout() {
  return (
    <AppProviders>
      <StatusBar style="dark" />
      <RootNavigator />
    </AppProviders>
  );
}

/**
 * Route groups are gated by session and role. These guards are a UX concern
 * only; the API enforces authorisation on every request.
 */
function RootNavigator() {
  const { status, user } = useAuth();

  // Keep the screen blank while the stored session is restored.
  if (status === 'loading') return null;

  const role = user?.role;

  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="index" />

      <Stack.Protected guard={status === 'signedOut'}>
        <Stack.Screen name="(auth)" />
      </Stack.Protected>

      <Stack.Protected guard={role === 'worker'}>
        <Stack.Screen name="(worker)" />
      </Stack.Protected>

      <Stack.Protected guard={role === 'leadhand'}>
        <Stack.Screen name="(leadhand)" />
      </Stack.Protected>
    </Stack>
  );
}
