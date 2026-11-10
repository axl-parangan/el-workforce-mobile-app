import { useRouter } from 'expo-router';
import { useState } from 'react';

import { describeError } from '@/api/error-messages';
import { CacheStatus } from '@/components/cache-status';
import { Body, Button, Card, QueryState, Screen, Segmented } from '@/components/ui';
import { useAuth } from '@/features/auth/auth-provider';
import { useRolePath } from '@/features/auth/capabilities';
import { useAssignedJobs } from '@/features/jobs/hooks';
import { useRecentEvents } from '@/offline/hooks';

import { DeviceEventRow } from '../components/device-event-row';
import { SessionRow } from '../components/session-row';
import { SyncStatus } from '../components/sync-status';
import { useMySessions } from '../hooks';

/** The signed-in employee's own attendance, plus punches recorded on this phone. */
export function HistoryScreen() {
  const [tab, setTab] = useState<'sessions' | 'device'>('sessions');
  return (
    <Screen>
      <Segmented
        value={tab}
        onChange={setTab}
        options={[
          { value: 'sessions', label: 'My sessions' },
          { value: 'device', label: 'On this phone' },
        ]}
      />
      {tab === 'sessions' ? <Sessions /> : <DeviceEvents />}
    </Screen>
  );
}

function Sessions() {
  const { user } = useAuth();
  const router = useRouter();
  const to = useRolePath();
  const [page, setPage] = useState(1);
  const query = useMySessions(page);

  if (!user?.employee) {
    return <Body muted>No employee record is linked to your account.</Body>;
  }
  const sessions = query.data?.data.results ?? [];
  return (
    <>
      <CacheStatus cached={query.data} />
      <QueryState
        isLoading={query.isPending}
        error={query.error ? describeError(query.error) : null}
        empty={query.isSuccess && sessions.length === 0}
        emptyText="No attendance recorded yet."
      />
      {sessions.length ? (
        <Card>
          {sessions.map((session) => (
            <SessionRow
              key={session.id}
              session={session}
              onPress={() => router.push(to(`/history/${session.id}`))}
            />
          ))}
        </Card>
      ) : null}
      {query.data?.data.next ? (
        <Button label="Older" variant="secondary" onPress={() => setPage((p) => p + 1)} />
      ) : null}
      {page > 1 ? (
        <Button label="Newer" variant="secondary" onPress={() => setPage((p) => p - 1)} />
      ) : null}
    </>
  );
}

function DeviceEvents() {
  const query = useRecentEvents();
  const jobs = useAssignedJobs();
  const events = query.data ?? [];
  const names = new Map((jobs.data?.data ?? []).map((job) => [job.id, job.job_number]));
  const jobLabel = (jobId: number) => names.get(jobId) ?? `job #${jobId}`;
  return (
    <>
      <SyncStatus showWhenClear />
      <QueryState
        isLoading={query.isPending}
        error={null}
        empty={query.isSuccess && events.length === 0}
        emptyText="No punches recorded on this phone with your account."
      />
      {events.length ? (
        <Card>
          {events.map((event) => (
            <DeviceEventRow key={event.id} event={event} jobLabel={jobLabel} />
          ))}
        </Card>
      ) : null}
    </>
  );
}
