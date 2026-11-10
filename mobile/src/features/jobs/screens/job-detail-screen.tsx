import { Stack, useLocalSearchParams, useRouter } from 'expo-router';

import { describeError } from '@/api/error-messages';
import { CacheStatus } from '@/components/cache-status';
import { Body, Button, Card, Heading, QueryState, Screen } from '@/components/ui';
import { useAuth } from '@/features/auth/auth-provider';
import { useRolePath } from '@/features/auth/capabilities';

import { useAssignedJobs, useJob } from '../hooks';
import { jobPermissions } from '../permissions';
import { JOB_STATUS_LABELS, type Job } from '../schemas';

export function JobDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const jobId = Number(id);
  const query = useJob(jobId);
  const assigned = useAssignedJobs();

  // Offline and never opened before: fall back to the cached assigned-jobs list.
  const fallback = assigned.data?.data.find((job) => job.id === jobId);
  const job = query.data?.data ?? (query.isError ? fallback : undefined);

  return (
    <Screen refreshing={query.isRefetching} onRefresh={() => void query.refetch()}>
      <Stack.Screen options={{ title: job?.job_number ?? 'Job' }} />
      <CacheStatus cached={query.data ?? (fallback ? assigned.data : undefined)} />
      <QueryState
        isLoading={query.isPending}
        error={!job && query.error ? describeError(query.error) : null}
      />
      {job ? <JobDetails job={job} /> : null}
    </Screen>
  );
}

function JobDetails({ job }: { job: Job }) {
  const { user } = useAuth();
  const router = useRouter();
  const to = useRolePath();
  const allowed = jobPermissions(user, job);
  const dates = [job.start_date, job.end_date].some(Boolean)
    ? `${job.start_date ?? 'No start date'} → ${job.end_date ?? 'no end date'}`
    : 'No dates set';

  return (
    <>
      <Card>
        <Heading>{job.name}</Heading>
        <Body>Status: {JOB_STATUS_LABELS[job.status]}</Body>
        {job.address ? <Body>{job.address}</Body> : null}
        <Body muted>{dates}</Body>
        <Body>LeadHand: {job.lead_hand?.name ?? 'None designated'}</Body>
        <Body muted>
          {job.geofence.configured
            ? `Site location ${job.geofence.latitude}, ${job.geofence.longitude} · radius ${
                job.geofence.radius_meters ?? 100
              } m`
            : 'No site location set: punches are not checked against a geofence.'}
        </Body>
      </Card>

      <Card>
        {job.viewer.manages_job ? (
          <Body>You lead this job.</Body>
        ) : job.viewer.my_assignment_id ? (
          <Body>You are assigned to this job.</Body>
        ) : (
          <Body muted>You are not assigned to this job.</Body>
        )}
        {job.status !== 'active' ? (
          <Body muted>Clock-in is only possible while the job is active.</Body>
        ) : null}
      </Card>

      {allowed.canRecordCrew ? (
        <Button
          label="Crew and group clock"
          testID="open-crew"
          onPress={() => router.push(to(`/jobs/${job.id}/crew`))}
        />
      ) : null}
      {allowed.canViewAssignments ? (
        <Button
          label={allowed.canManageAssignments ? 'Manage assignments' : 'Crew assignments'}
          variant="secondary"
          testID="open-assignments"
          onPress={() => router.push(to(`/jobs/${job.id}/assignments`))}
        />
      ) : null}
      {allowed.canViewAttendance ? (
        <Button
          label="Attendance for this job"
          variant="secondary"
          testID="open-attendance"
          onPress={() =>
            router.push(
              to(`/attendance?jobId=${job.id}&jobNumber=${encodeURIComponent(job.job_number)}`),
            )
          }
        />
      ) : null}
      {allowed.canDesignateLeadHand ? (
        <Button
          label="Change LeadHand"
          variant="secondary"
          testID="open-lead-hand"
          onPress={() => router.push(to(`/jobs/${job.id}/lead-hand`))}
        />
      ) : null}
      {allowed.canEdit ? (
        <Button
          label="Edit job"
          variant="secondary"
          testID="edit-job"
          onPress={() => router.push(to(`/jobs/${job.id}/edit`))}
        />
      ) : null}
    </>
  );
}
