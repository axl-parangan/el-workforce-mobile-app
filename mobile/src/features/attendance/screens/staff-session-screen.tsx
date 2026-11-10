import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useLocalSearchParams } from 'expo-router';
import { useState } from 'react';

import { describeError } from '@/api/error-messages';
import {
  Banner,
  Body,
  Button,
  Card,
  Heading,
  QueryState,
  Screen,
  TextField,
} from '@/components/ui';
import { useAuth } from '@/features/auth/auth-provider';
import { Capability, can } from '@/features/auth/capabilities';
import { reviewSession } from '@/features/timekeeping/api';
import { SessionDetails } from '@/features/timekeeping/components/session-details';
import type { StaffSession } from '@/features/timekeeping/schemas';
import { formatDateTime } from '@/lib/company-time';

import { useStaffSession } from '../hooks';

/** Why the review form is not offered, or null when it is. Mirrors the server rules. */
export function reviewBlocker(
  user: Parameters<typeof can>[0],
  session: StaffSession,
): string | null {
  if (!can(user, Capability.attendanceReview)) return 'Managers and Admins review attendance.';
  if (user?.employee?.id === session.employee.id) {
    return 'You cannot review your own timesheet. Another Manager or Admin will review it.';
  }
  if (session.session_status === 'open') return 'Open sessions can be reviewed once they close.';
  return null;
}

export function StaffSessionScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { user } = useAuth();
  const query = useStaffSession(Number(id));
  const session = query.data;

  return (
    <Screen refreshing={query.isRefetching} onRefresh={() => void query.refetch()}>
      <QueryState
        isLoading={query.isPending}
        error={query.error ? describeError(query.error) : null}
      />
      {session ? (
        <>
          <SessionDetails session={session} />
          <Card>
            <Heading>Reviews</Heading>
            {session.reviews.length === 0 ? <Body muted>Not reviewed yet.</Body> : null}
            {session.reviews.map((review) => (
              <Body key={review.id}>
                {review.decision === 'approved' ? 'Approved' : 'Rejected'} by{' '}
                {review.reviewed_by?.email ?? 'unknown'} on {formatDateTime(review.reviewed_at)}:{' '}
                {review.reason}
              </Body>
            ))}
          </Card>
          {reviewBlocker(user, session) ? (
            <Body muted>{reviewBlocker(user, session)}</Body>
          ) : (
            <ReviewForm session={session} />
          )}
        </>
      ) : null}
    </Screen>
  );
}

function ReviewForm({ session }: { session: StaffSession }) {
  const queryClient = useQueryClient();
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: (decision: 'approved' | 'rejected') =>
      reviewSession(session.id, decision, reason.trim()),
    onSuccess: async () => {
      setReason('');
      await queryClient.invalidateQueries({ queryKey: ['timekeeping', 'staff'] });
    },
    onError: (e) => setError(describeError(e)),
  });

  function decide(decision: 'approved' | 'rejected') {
    if (!reason.trim()) {
      setError('Enter a reason for the decision.');
      return;
    }
    setError(null);
    mutation.mutate(decision);
  }

  return (
    <Card>
      <Heading>Review</Heading>
      {error ? <Banner tone="danger">{error}</Banner> : null}
      <TextField
        label="Reason"
        value={reason}
        onChangeText={setReason}
        placeholder="Required, e.g. Confirmed with the LeadHand"
        multiline
      />
      <Button
        label="Approve"
        testID="approve"
        busy={mutation.isPending}
        onPress={() => decide('approved')}
      />
      <Button
        label="Reject"
        variant="danger"
        testID="reject"
        busy={mutation.isPending}
        onPress={() => decide('rejected')}
      />
      <Body muted>Decisions are kept as history. Punches and location data are never changed.</Body>
    </Card>
  );
}
