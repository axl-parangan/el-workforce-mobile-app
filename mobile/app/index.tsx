import { Redirect } from 'expo-router';

import { PlaceholderScreen } from '@/components/placeholder-screen';
import { useAuth } from '@/features/auth/auth-provider';

/** Entry point: sends the user to the route group that matches their session and role. */
export default function Index() {
  const { status, user } = useAuth();

  if (status !== 'signedIn') return <Redirect href="/sign-in" />;

  switch (user.role) {
    case 'admin':
      return <Redirect href="/admin" />;
    case 'manager':
      return <Redirect href="/manager" />;
    case 'leadhand':
      return <Redirect href="/leadhand" />;
    case 'worker':
      return <Redirect href="/worker" />;
    case 'unknown':
      return (
        <PlaceholderScreen
          title="Update required"
          description="This version of the app does not support your account role. Please update the app."
        />
      );
  }
}
