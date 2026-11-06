import { Redirect } from 'expo-router';

import { PlaceholderScreen } from '@/components/placeholder-screen';
import { useAuth } from '@/features/auth/auth-provider';

/** Entry point: sends the user to the route group that matches their session and role. */
export default function Index() {
  const { status, user } = useAuth();

  if (status !== 'signedIn') return <Redirect href="/sign-in" />;

  switch (user.role) {
    case 'worker':
      return <Redirect href="/worker" />;
    case 'leadhand':
      return <Redirect href="/leadhand" />;
    case 'admin':
      // TODO: confirm whether Admins use the mobile app (see docs/development/open-questions.md).
      return (
        <PlaceholderScreen
          title="Admin"
          description="Administration is not available in the mobile app yet."
        />
      );
  }
}
