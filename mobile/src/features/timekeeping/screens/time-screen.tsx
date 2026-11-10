import { useState } from 'react';
import { Alert } from 'react-native';

import { describeError } from '@/api/error-messages';
import { CacheStatus } from '@/components/cache-status';
import { Banner, Body, Button, Card, Heading, ListRow, QueryState, Screen } from '@/components/ui';
import { useAuth } from '@/features/auth/auth-provider';
import { useAssignedJobs, useMyAssignments } from '@/features/jobs/hooks';
import { JOB_STATUS_LABELS, type Assignment } from '@/features/jobs/schemas';
import { formatTime, nowIso, workDateFor } from '@/lib/company-time';
import { capturePunchLocation } from '@/lib/location';

import { SyncStatus } from '../components/sync-status';
import { clockInWarnings } from '../eligibility';
import { newPunch, useAttendanceView, usePunch } from '../hooks';
import { toLocationPayload } from '../punch-events';
import { noticeForPunch, noticeForSwitch, type Notice } from '../punch-messages';

function confirm(title: string, message: string, action: string): Promise<boolean> {
  return new Promise((resolve) =>
    Alert.alert(title, message, [
      { text: 'Cancel', style: 'cancel', onPress: () => resolve(false) },
      { text: action, onPress: () => resolve(true) },
    ]),
  );
}

/** Clock in, clock out and switch jobs. Works offline from cached assignments. */
export function TimeScreen() {
  const { user } = useAuth();
  if (!user?.employee) {
    return (
      <Screen>
        <Banner tone="warning">
          No employee record is linked to your account, so you cannot record attendance. Ask a
          manager to link one.
        </Banner>
      </Screen>
    );
  }
  return <TimeClock />;
}

function TimeClock() {
  const assignments = useMyAssignments();
  const assignedJobs = useAssignedJobs();
  const { view, status, ready } = useAttendanceView();
  const punch = usePunch();
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);

  const active = uniqueByJob(assignments.data?.data ?? []);
  const jobsById = new Map((assignedJobs.data?.data ?? []).map((job) => [job.id, job]));
  const label = (jobId: number) => {
    const job =
      jobsById.get(jobId) ??
      active.find((a) => a.job.id === jobId)?.job ??
      (status.data?.data.open_session?.job.id === jobId ? status.data.data.open_session.job : null);
    return job ? `${job.job_number} · ${job.name}` : `job #${jobId}`;
  };

  async function capture() {
    const capturedAt = nowIso();
    setBusy('Getting your location…');
    const location = toLocationPayload(await capturePunchLocation());
    setBusy('Saving…');
    return { capturedAt, location };
  }

  async function run(task: () => Promise<Notice>) {
    setNotice(null);
    try {
      setNotice(await task());
    } catch (error) {
      setNotice({ tone: 'danger', text: describeError(error) });
    } finally {
      setBusy(null);
    }
  }

  async function confirmClockIn(jobId: number): Promise<boolean> {
    const warnings = clockInWarnings({
      assignment: active.find((a) => a.job.id === jobId),
      job: jobsById.get(jobId),
      workDate: workDateFor(new Date()),
    });
    if (warnings.length === 0) return true;
    return confirm(
      'Clock in anyway?',
      `${warnings.join('\n')}\n\nThe server checks every punch and may refuse it.`,
      'Clock in',
    );
  }

  async function clockIn(jobId: number) {
    if (!(await confirmClockIn(jobId))) return;
    await run(async () => {
      const { capturedAt, location } = await capture();
      const [outcome] = await punch([
        newPunch({ action_type: 'clock_in', job_id: jobId, captured_at: capturedAt, location }),
      ]);
      return noticeForPunch(outcome!, label);
    });
  }

  async function clockOut(jobId: number) {
    await run(async () => {
      const { capturedAt, location } = await capture();
      const [outcome] = await punch([
        newPunch({ action_type: 'clock_out', job_id: jobId, captured_at: capturedAt, location }),
      ]);
      return noticeForPunch(outcome!, label);
    });
  }

  async function switchTo(fromJobId: number, toJobId: number) {
    const ok = await confirm(
      'Switch jobs?',
      `Clock out of ${label(fromJobId)} and clock in to ${label(toJobId)} now.`,
      'Switch',
    );
    if (!ok || !(await confirmClockIn(toJobId))) return;
    await run(async () => {
      const { capturedAt, location } = await capture();
      // One instant for both: the server processes the clock-out first (Q13).
      const outcomes = await punch([
        newPunch({
          action_type: 'clock_out',
          job_id: fromJobId,
          captured_at: capturedAt,
          location,
        }),
        newPunch({ action_type: 'clock_in', job_id: toJobId, captured_at: capturedAt, location }),
      ]);
      return noticeForSwitch([outcomes[0]!, outcomes[1]!], label);
    });
  }

  const open = view.open;
  const refreshing = assignments.isRefetching || status.isRefetching;

  return (
    <Screen
      refreshing={refreshing}
      onRefresh={() => {
        void assignments.refetch();
        void assignedJobs.refetch();
        void status.refetch();
      }}
    >
      <SyncStatus />
      <CacheStatus cached={assignments.data} />

      {notice ? (
        <Banner tone={notice.tone} testID="punch-notice">
          {notice.text}
        </Banner>
      ) : null}
      {notice?.clockBackIn && !open ? (
        <Button
          label={`Clock back in to ${notice.clockBackIn.label}`}
          variant="secondary"
          testID="clock-back-in"
          disabled={Boolean(busy)}
          onPress={() => void clockIn(notice.clockBackIn!.jobId)}
        />
      ) : null}

      <Card>
        {!ready ? (
          <QueryState isLoading error={null} />
        ) : open ? (
          <>
            <Heading>Clocked in</Heading>
            <Body>{label(open.jobId)}</Body>
            <Body muted>
              Since {open.since ? formatTime(open.since) : 'unknown'}
              {view.provisional ? ' · not sent yet' : ''}
            </Body>
            <Button
              label="Clock out"
              variant="danger"
              testID="clock-out"
              busy={Boolean(busy)}
              onPress={() => void clockOut(open.jobId)}
            />
          </>
        ) : (
          <>
            <Heading>Not clocked in</Heading>
            <Body muted>Choose a job below to clock in.</Body>
          </>
        )}
        {status.error && !status.data ? (
          <Body muted>Could not load your status: {describeError(status.error)}</Body>
        ) : null}
        {busy ? <Body muted>{busy}</Body> : null}
      </Card>

      <Card>
        <Heading>Your jobs</Heading>
        <QueryState
          isLoading={assignments.isPending}
          error={assignments.error && !assignments.data ? describeError(assignments.error) : null}
          empty={assignments.isSuccess && active.length === 0}
          emptyText="You are not assigned to any jobs. Ask your manager to assign you."
        />
        {active.map((assignment) => {
          const job = jobsById.get(assignment.job.id);
          const isCurrent = open?.jobId === assignment.job.id;
          const details = [
            job ? JOB_STATUS_LABELS[job.status] : null,
            assignment.start_date || assignment.end_date
              ? `${assignment.start_date ?? '…'} → ${assignment.end_date ?? '…'}`
              : null,
          ]
            .filter(Boolean)
            .join(' · ');
          return (
            <ListRow
              key={assignment.job.id}
              testID={`time-job-${assignment.job.id}`}
              title={`${assignment.job.job_number} · ${assignment.job.name}`}
              subtitle={details || undefined}
              right={
                isCurrent ? (
                  <Body muted>Current</Body>
                ) : (
                  <Button
                    compact
                    label={open ? 'Switch here' : 'Clock in'}
                    variant={open ? 'secondary' : 'primary'}
                    testID={`${open ? 'switch' : 'clock-in'}-${assignment.job.id}`}
                    disabled={Boolean(busy)}
                    onPress={() =>
                      void (open
                        ? switchTo(open.jobId, assignment.job.id)
                        : clockIn(assignment.job.id))
                    }
                  />
                )
              }
            />
          );
        })}
      </Card>
    </Screen>
  );
}

function uniqueByJob(assignments: Assignment[]): Assignment[] {
  const seen = new Set<number>();
  return assignments.filter((a) => {
    if (a.status !== 'active' || seen.has(a.job.id)) return false;
    seen.add(a.job.id);
    return true;
  });
}
