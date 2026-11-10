import { useQueryClient } from '@tanstack/react-query';
import { Stack, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { describeError } from '@/api/error-messages';
import { CacheStatus } from '@/components/cache-status';
import {
  Banner,
  Body,
  Button,
  Card,
  colors,
  Heading,
  QueryState,
  Screen,
  TextField,
} from '@/components/ui';
import { useAuth } from '@/features/auth/auth-provider';
import { useJob } from '@/features/jobs/hooks';
import { jobPermissions } from '@/features/jobs/permissions';
import { submitPunch } from '@/features/timekeeping/api';
import { SyncStatus } from '@/features/timekeeping/components/sync-status';
import { newPunch, timekeepingKeys, useCrew, usePunch } from '@/features/timekeeping/hooks';
import { toLocationPayload, type PunchPayload } from '@/features/timekeeping/punch-events';
import { submitOnlineOnly, type PunchOutcome } from '@/features/timekeeping/punch-service';
import type { BatchResult, Crew } from '@/features/timekeeping/schemas';
import { formatTime, nowIso } from '@/lib/company-time';
import { capturePunchLocation } from '@/lib/location';

type Member = Crew['crew'][number];
type Result =
  | { kind: 'batch'; batch: BatchResult }
  | { kind: 'message'; tone: 'info' | 'danger'; text: string };

/**
 * Group clock-in/out for one job (ADR 006). LeadHands may only use it on jobs
 * they manage, and their group punches work offline through the outbox.
 * Manager/Admin group punches are online-only (M7).
 */
export function CrewScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const jobId = Number(id);
  const { user } = useAuth();
  const job = useJob(jobId);
  const allowed = job.data ? jobPermissions(user, job.data.data) : null;

  return (
    <>
      <Stack.Screen options={{ title: job.data ? `Crew · ${job.data.data.job_number}` : 'Crew' }} />
      {job.isPending ? (
        <Screen>
          <QueryState isLoading error={null} />
        </Screen>
      ) : !allowed?.canRecordCrew ? (
        <Screen>
          <Banner tone="danger">
            {job.error && !job.data
              ? describeError(job.error)
              : 'Only the LeadHand who manages this job, a Manager or an Admin can record crew attendance.'}
          </Banner>
        </Screen>
      ) : (
        <CrewClock jobId={jobId} onlineOnly={allowed.crewPunchesOnlineOnly} />
      )}
    </>
  );
}

function CrewClock({ jobId, onlineOnly }: { jobId: number; onlineOnly: boolean }) {
  const queryClient = useQueryClient();
  const crew = useCrew(jobId);
  const punch = usePunch();
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  // M7: an online-only punch that failed to send is retried with the same event id.
  const [unsent, setUnsent] = useState<PunchPayload | null>(null);

  const members = crew.data?.data.crew ?? [];
  const picked = members.filter((m) => selected.has(m.employee.id));

  function toggle(employeeId: number) {
    setUnsent(null);
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(employeeId)) next.delete(employeeId);
      else next.add(employeeId);
      return next;
    });
  }

  function selectWhere(predicate: (m: Member) => boolean) {
    setUnsent(null);
    setSelected(new Set(members.filter(predicate).map((m) => m.employee.id)));
  }

  async function send(payload: PunchPayload) {
    setResult(null);
    setBusy('Saving…');
    try {
      if (onlineOnly) {
        const outcome = await submitOnlineOnly(submitPunch, payload);
        if (outcome.kind === 'offline') {
          setUnsent(payload);
          setResult({
            kind: 'message',
            tone: 'danger',
            text: `Not sent: ${outcome.message} Group punches by Managers and Admins need a connection. Try again when online.`,
          });
          return;
        }
        setUnsent(null);
        setResult(resultFor(outcome));
      } else {
        const [outcome] = await punch([payload]);
        setResult(resultFor(outcome!));
      }
      setSelected(new Set());
      await queryClient.invalidateQueries({ queryKey: timekeepingKeys.crew(jobId) });
    } catch (error) {
      setResult({ kind: 'message', tone: 'danger', text: describeError(error) });
    } finally {
      setBusy(null);
    }
  }

  async function record(action: PunchPayload['action_type']) {
    const capturedAt = nowIso();
    setBusy('Getting your location…');
    const location = toLocationPayload(await capturePunchLocation());
    await send(
      newPunch({
        action_type: action,
        job_id: jobId,
        captured_at: capturedAt,
        location,
        employee_ids: picked.map((m) => m.employee.id),
        ...(onlineOnly && reason.trim() ? { reason: reason.trim() } : {}),
      }),
    );
  }

  return (
    <Screen refreshing={crew.isRefetching} onRefresh={() => void crew.refetch()}>
      {onlineOnly ? null : <SyncStatus />}
      <CacheStatus cached={crew.data} />
      <QueryState
        isLoading={crew.isPending}
        error={crew.error && !crew.data ? describeError(crew.error) : null}
        empty={crew.isSuccess && members.length === 0}
        emptyText="No one is assigned to this job."
      />
      {members.length ? (
        <Card>
          <View style={styles.row}>
            <Button
              compact
              variant="secondary"
              label="Not clocked in"
              onPress={() => selectWhere((m) => !m.clocked_in)}
            />
            <Button
              compact
              variant="secondary"
              label="Clocked in here"
              onPress={() => selectWhere((m) => m.open_session?.job.id === jobId)}
            />
            <Button
              compact
              variant="secondary"
              label="None"
              onPress={() => selectWhere(() => false)}
            />
          </View>
          {members.map((member) => (
            <CrewRow
              key={member.employee.id}
              member={member}
              jobId={jobId}
              selected={selected.has(member.employee.id)}
              onToggle={() => toggle(member.employee.id)}
            />
          ))}
        </Card>
      ) : null}

      {onlineOnly ? (
        <>
          <TextField
            label="Reason (optional)"
            placeholder="e.g. Crew phone was dead"
            value={reason}
            onChangeText={(text) => {
              setUnsent(null);
              setReason(text);
            }}
            maxLength={500}
          />
          <Body muted>
            Office entries must be recorded within 15 minutes of the time they happen. Your location
            is stored but not checked against the site.
          </Body>
        </>
      ) : null}

      {busy ? <Body muted>{busy}</Body> : null}
      {unsent ? (
        <Button
          label="Try again"
          testID="crew-retry"
          busy={Boolean(busy)}
          onPress={() => void send(unsent)}
        />
      ) : (
        <>
          <Button
            label={`Clock in selected (${picked.length})`}
            testID="crew-clock-in"
            disabled={picked.length === 0}
            busy={Boolean(busy)}
            onPress={() => void record('clock_in')}
          />
          <Button
            label={`Clock out selected (${picked.length})`}
            variant="danger"
            testID="crew-clock-out"
            disabled={picked.length === 0}
            busy={Boolean(busy)}
            onPress={() => void record('clock_out')}
          />
        </>
      )}

      {result?.kind === 'message' ? (
        <Banner tone={result.tone} testID="crew-result">
          {result.text}
        </Banner>
      ) : null}
      {result?.kind === 'batch' ? <BatchResults batch={result.batch} /> : null}
    </Screen>
  );
}

function resultFor(outcome: PunchOutcome): Result {
  switch (outcome.kind) {
    case 'accepted':
      return { kind: 'batch', batch: outcome.result };
    case 'rejected':
      return outcome.result
        ? { kind: 'batch', batch: outcome.result }
        : { kind: 'message', tone: 'danger', text: outcome.message };
    case 'queued':
      return {
        kind: 'message',
        tone: 'info',
        text: `Saved on this phone for ${outcome.payload.employee_ids?.length ?? 0} employee(s). It will be sent automatically when you are back online. Each employee's result then appears in History, On this phone.`,
      };
  }
}

function CrewRow({
  member,
  jobId,
  selected,
  onToggle,
}: {
  member: Member;
  jobId: number;
  selected: boolean;
  onToggle: () => void;
}) {
  const where = member.open_session
    ? member.open_session.job.id === jobId
      ? `Clocked in here since ${member.open_session.clock_in_at ? formatTime(member.open_session.clock_in_at) : '?'}`
      : `Clocked in at ${member.open_session.job.job_number}`
    : 'Not clocked in';
  return (
    <Pressable
      testID={`crew-${member.employee.id}`}
      accessibilityRole="checkbox"
      accessibilityState={{ checked: selected }}
      onPress={onToggle}
      style={styles.member}
    >
      <Text style={[styles.box, selected && styles.boxOn]}>{selected ? '✓' : ''}</Text>
      <View style={styles.memberText}>
        <Text style={styles.name}>
          {member.employee.name}
          {member.employee.has_account ? '' : ' (no app account)'}
        </Text>
        <Text style={styles.muted}>{where}</Text>
      </View>
    </Pressable>
  );
}

export function BatchResults({ batch }: { batch: BatchResult }) {
  const accepted = batch.results.filter((r) => r.status === 'accepted').length;
  return (
    <Card>
      <Heading>
        {batch.action_type === 'clock_in' ? 'Clock-in' : 'Clock-out'}: {accepted} of{' '}
        {batch.results.length} accepted
      </Heading>
      {batch.results.map((r) => (
        <Body key={r.employee.id}>
          {r.status === 'accepted' ? '✓' : '✕'} {r.employee.name}: {r.message}
        </Body>
      ))}
    </Card>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  member: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingVertical: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  box: {
    width: 26,
    height: 26,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: colors.primary,
    textAlign: 'center',
    color: '#fff',
    fontWeight: '700',
  },
  boxOn: { backgroundColor: colors.primary },
  memberText: { flex: 1, gap: 2 },
  name: { fontSize: 16, color: colors.text },
  muted: { fontSize: 14, color: colors.muted },
});
