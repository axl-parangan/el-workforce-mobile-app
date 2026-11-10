import { StyleSheet, Text } from 'react-native';

import { colors, ListRow } from '@/components/ui';

import { JOB_STATUS_LABELS, type Job } from '../schemas';

export function JobRow({ job, onPress }: { job: Job; onPress: () => void }) {
  const details = [JOB_STATUS_LABELS[job.status], job.address].filter(Boolean).join(' · ');
  return (
    <ListRow
      testID={`job-${job.id}`}
      title={`${job.job_number} · ${job.name}`}
      subtitle={details}
      onPress={onPress}
      right={job.viewer.manages_job ? <Text style={styles.badge}>You lead</Text> : undefined}
    />
  );
}

const styles = StyleSheet.create({
  badge: { color: colors.primary, fontSize: 13, fontWeight: '600' },
});
