import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';

import { describeError } from '@/api/error-messages';
import {
  Banner,
  Body,
  Button,
  Card,
  ListRow,
  QueryState,
  Screen,
  Segmented,
} from '@/components/ui';
import { Capability, useCan, useRolePath } from '@/features/auth/capabilities';
import { SessionRow } from '@/features/timekeeping/components/session-row';
import { formatDateTime } from '@/lib/company-time';

import { useRejectedEvents, useStaffSessions } from '../hooks';

type Tab = 'exceptions' | 'all' | 'rejected';

/**
 * Attendance for staff. LeadHands see only the jobs they manage; Managers and
 * Admins see everything (the server applies the scope).
 */
export function StaffAttendanceScreen() {
  const can = useCan();
  const router = useRouter();
  const to = useRolePath();
  const params = useLocalSearchParams<{ jobId?: string; jobNumber?: string }>();
  const jobId = params.jobId ? Number(params.jobId) : undefined;
  const [tab, setTab] = useState<Tab>('exceptions');
  const allowed = can(Capability.attendanceViewAny, Capability.attendanceViewCrew);

  const sessions = useStaffSessions(
    tab === 'all' ? 'all' : 'exceptions',
    jobId,
    allowed && tab !== 'rejected',
  );
  const rejected = useRejectedEvents(jobId, allowed && tab === 'rejected');
  const active = tab === 'rejected' ? rejected : sessions;

  if (!allowed) {
    return (
      <Screen>
        <Banner tone="danger">You do not have access to staff attendance.</Banner>
      </Screen>
    );
  }

  return (
    <Screen refreshing={active.isRefetching} onRefresh={() => void active.refetch()}>
      {jobId ? (
        <Card>
          <Body>Showing job {params.jobNumber ?? `#${jobId}`} only.</Body>
          <Button
            compact
            variant="secondary"
            label="Show all jobs"
            onPress={() => router.setParams({ jobId: undefined, jobNumber: undefined })}
          />
        </Card>
      ) : null}
      <Segmented
        value={tab}
        onChange={setTab}
        options={[
          { value: 'exceptions', label: 'Needs review' },
          { value: 'all', label: 'All' },
          { value: 'rejected', label: 'Refused punches' },
        ]}
      />
      {!can(Capability.attendanceReview) ? (
        <Body muted>Managers and Admins review attendance. You can see it for your jobs.</Body>
      ) : null}
      <QueryState
        isLoading={active.isPending}
        error={active.error ? describeError(active.error) : null}
        empty={active.isSuccess && (active.data?.results.length ?? 0) === 0}
        emptyText={tab === 'exceptions' ? 'Nothing needs review.' : 'Nothing to show.'}
      />
      {tab !== 'rejected' && sessions.data?.results.length ? (
        <Card>
          {sessions.data.results.map((session) => (
            <SessionRow
              key={session.id}
              session={session}
              showEmployee
              onPress={() => router.push(to(`/attendance/${session.id}`))}
            />
          ))}
        </Card>
      ) : null}
      {tab === 'rejected' && rejected.data?.results.length ? (
        <Card>
          {rejected.data.results.map((event) => (
            <ListRow
              key={event.id}
              title={`${event.employee.name} · ${event.job.job_number} · ${
                event.action_type === 'clock_in' ? 'clock in' : 'clock out'
              }`}
              subtitle={`${formatDateTime(event.captured_at)} · ${event.message}${
                event.performed_by ? ` · by ${event.performed_by.email}` : ''
              }`}
            />
          ))}
        </Card>
      ) : null}
      {active.data && active.data.count > active.data.results.length ? (
        <Body muted>
          Showing the latest {active.data.results.length} of {active.data.count}.
        </Body>
      ) : null}
    </Screen>
  );
}
