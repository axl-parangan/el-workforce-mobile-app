import { StyleSheet, Text } from 'react-native';

import { colors, ListRow } from '@/components/ui';
import { formatDuration, formatTime } from '@/lib/company-time';

import type { Session } from '../schemas';

export const REVIEW_LABELS: Record<string, string> = {
  not_required: 'No review needed',
  pending: 'Needs review',
  approved: 'Approved',
  rejected: 'Rejected',
};

export function sessionTimes(session: Session): string {
  const start = session.clock_in ? formatTime(session.clock_in.at) : '?';
  const end = session.clock_out ? formatTime(session.clock_out.at) : 'now';
  const duration =
    session.duration_seconds !== null ? ` · ${formatDuration(session.duration_seconds)}` : '';
  return `${session.work_date} · ${start}–${end}${duration}`;
}

export function SessionRow({
  session,
  onPress,
  showEmployee = false,
}: {
  session: Session;
  onPress: () => void;
  showEmployee?: boolean;
}) {
  const flagged = session.review_status === 'pending' || session.review_status === 'rejected';
  const title = showEmployee
    ? `${session.employee.name} · ${session.job.job_number}`
    : `${session.job.job_number} · ${session.job.name}`;
  return (
    <ListRow
      testID={`session-${session.id}`}
      title={title}
      subtitle={sessionTimes(session)}
      onPress={onPress}
      right={
        <Text style={[styles.badge, flagged && styles.flagged]}>
          {session.session_status === 'open'
            ? 'Open'
            : (REVIEW_LABELS[session.review_status] ?? session.review_status)}
        </Text>
      }
    />
  );
}

const styles = StyleSheet.create({
  badge: { fontSize: 13, color: colors.muted },
  flagged: { color: colors.warning, fontWeight: '600' },
});
