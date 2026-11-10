import { useRouter } from 'expo-router';
import { useState } from 'react';

import { describeError } from '@/api/error-messages';
import { CacheStatus } from '@/components/cache-status';
import { Body, Button, Card, QueryState, Screen, Segmented, TextField } from '@/components/ui';
import { Capability, useCan, useRolePath } from '@/features/auth/capabilities';

import { JobRow } from '../components/job-row';
import { useAssignedJobs, useJobList } from '../hooks';
import type { JobStatus } from '../schemas';

/**
 * Managers and Admins search every job. Employees and LeadHands see the jobs
 * they are assigned to, which are cached for offline use.
 */
export function JobsListScreen() {
  const can = useCan();
  return can(Capability.jobsViewAny) ? <CompanyJobs /> : <AssignedJobs />;
}

function NewJobButton() {
  const can = useCan();
  const to = useRolePath();
  const router = useRouter();
  if (!can(Capability.jobsCreate)) return null;
  return (
    <Button
      label="New job"
      variant="secondary"
      testID="new-job"
      onPress={() => router.push(to('/jobs/new'))}
    />
  );
}

function AssignedJobs() {
  const router = useRouter();
  const to = useRolePath();
  const can = useCan();
  const query = useAssignedJobs();
  const [filter, setFilter] = useState<'all' | 'managed'>('all');
  const leads = can(Capability.attendanceRecordCrew);

  const jobs = (query.data?.data ?? []).filter((job) => filter === 'all' || job.viewer.manages_job);

  return (
    <Screen refreshing={query.isRefetching} onRefresh={() => void query.refetch()}>
      <CacheStatus cached={query.data} />
      <NewJobButton />
      {leads ? (
        <Segmented
          value={filter}
          onChange={setFilter}
          options={[
            { value: 'all', label: 'Assigned to me' },
            { value: 'managed', label: 'I lead' },
          ]}
        />
      ) : null}
      <QueryState
        isLoading={query.isPending}
        error={query.error ? describeError(query.error) : null}
        empty={query.isSuccess && jobs.length === 0}
        emptyText={
          filter === 'managed' ? 'You do not lead any jobs.' : 'You are not assigned to any jobs.'
        }
      />
      {jobs.length ? (
        <Card>
          {jobs.map((job) => (
            <JobRow key={job.id} job={job} onPress={() => router.push(to(`/jobs/${job.id}`))} />
          ))}
        </Card>
      ) : null}
    </Screen>
  );
}

const STATUS_FILTERS: { value: JobStatus | 'all'; label: string }[] = [
  { value: 'active', label: 'Active' },
  { value: 'planned', label: 'Planned' },
  { value: 'on_hold', label: 'On hold' },
  { value: 'all', label: 'All' },
];

function CompanyJobs() {
  const router = useRouter();
  const to = useRolePath();
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState<JobStatus | 'all'>('active');
  const query = useJobList(
    { search: search.trim() || undefined, status: status === 'all' ? undefined : status },
    true,
  );
  const jobs = query.data?.results ?? [];

  return (
    <Screen refreshing={query.isRefetching} onRefresh={() => void query.refetch()}>
      <NewJobButton />
      <TextField
        label="Search"
        placeholder="Job number or name"
        value={search}
        onChangeText={setSearch}
        autoCapitalize="none"
      />
      <Segmented value={status} onChange={setStatus} options={STATUS_FILTERS} />
      <QueryState
        isLoading={query.isPending}
        error={query.error ? describeError(query.error) : null}
        empty={query.isSuccess && jobs.length === 0}
        emptyText="No jobs match."
      />
      {jobs.length ? (
        <Card>
          {jobs.map((job) => (
            <JobRow key={job.id} job={job} onPress={() => router.push(to(`/jobs/${job.id}`))} />
          ))}
        </Card>
      ) : null}
      {query.data && query.data.count > jobs.length ? (
        <Body muted>
          Showing {jobs.length} of {query.data.count}. Refine the search to narrow the list.
        </Body>
      ) : null}
    </Screen>
  );
}
