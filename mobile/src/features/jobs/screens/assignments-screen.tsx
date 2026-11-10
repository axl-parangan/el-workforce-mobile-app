import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Stack, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Alert } from 'react-native';

import { describeError } from '@/api/error-messages';
import {
  Banner,
  Body,
  Button,
  Card,
  Heading,
  ListRow,
  QueryState,
  Screen,
  Segmented,
  TextField,
} from '@/components/ui';
import { useAuth } from '@/features/auth/auth-provider';
import { formatDateTime } from '@/lib/company-time';

import { assignEmployees, cancelAssignment, endAssignment, updateAssignmentDates } from '../api';
import { EmployeePicker } from '../components/employee-picker';
import { useJob, useJobAssignments } from '../hooks';
import { jobPermissions } from '../permissions';
import type { AssignResponse, Assignment } from '../schemas';

const DATE = /^\d{4}-\d{2}-\d{2}$/;

function dateOrNull(value: string): string | null | 'invalid' {
  const trimmed = value.trim();
  if (!trimmed) return null;
  return DATE.test(trimmed) ? trimmed : 'invalid';
}

/**
 * Crew assignments for one job. Managers and Admins manage them; the
 * LeadHand who manages the job can view them (docs/api/jobs.md).
 */
export function AssignmentsScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const jobId = Number(id);
  const { user } = useAuth();
  const job = useJob(jobId);
  const allowed = job.data ? jobPermissions(user, job.data.data) : null;

  return (
    <>
      <Stack.Screen
        options={{ title: job.data ? `Assignments · ${job.data.data.job_number}` : 'Assignments' }}
      />
      {!job.data ? (
        <Screen>
          <QueryState
            isLoading={job.isPending}
            error={job.error ? describeError(job.error) : null}
          />
        </Screen>
      ) : !allowed?.canViewAssignments ? (
        <Screen>
          <Banner tone="danger">
            Only Managers, Admins and the LeadHand who manages this job can see its assignments.
          </Banner>
        </Screen>
      ) : (
        <Assignments jobId={jobId} manage={allowed.canManageAssignments} />
      )}
    </>
  );
}

function Assignments({ jobId, manage }: { jobId: number; manage: boolean }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<'active' | 'all'>('active');
  const [expanded, setExpanded] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const list = useJobAssignments(jobId, status);
  const assignments = list.data ?? [];

  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ['jobs', jobId] }),
      queryClient.invalidateQueries({ queryKey: ['jobs', 'detail', jobId] }),
      queryClient.invalidateQueries({ queryKey: ['timekeeping', 'crew', jobId] }),
    ]);

  return (
    <Screen refreshing={list.isRefetching} onRefresh={() => void list.refetch()}>
      <Segmented
        value={status}
        onChange={setStatus}
        options={[
          { value: 'active', label: 'Active' },
          { value: 'all', label: 'All, with history' },
        ]}
      />
      {manage ? (
        adding ? (
          <AddEmployees
            jobId={jobId}
            assignedIds={
              new Set(assignments.filter((a) => a.status === 'active').map((a) => a.employee.id))
            }
            onDone={async () => {
              setAdding(false);
              await refresh();
            }}
            onCancel={() => setAdding(false)}
          />
        ) : (
          <Button
            label="Assign employees"
            testID="add-assignments"
            onPress={() => setAdding(true)}
          />
        )
      ) : (
        <Body muted>Managers and Admins change assignments.</Body>
      )}
      <QueryState
        isLoading={list.isPending}
        error={list.error ? describeError(list.error) : null}
        empty={list.isSuccess && assignments.length === 0}
        emptyText={status === 'active' ? 'No one is assigned.' : 'No assignments yet.'}
      />
      {assignments.length ? (
        <Card>
          {assignments.map((assignment) => (
            <AssignmentItem
              key={assignment.id}
              assignment={assignment}
              manage={manage}
              expanded={expanded === assignment.id}
              onToggle={() => setExpanded(expanded === assignment.id ? null : assignment.id)}
              onChanged={refresh}
            />
          ))}
        </Card>
      ) : null}
    </Screen>
  );
}

function describeAssignment(a: Assignment): string {
  const dates =
    a.start_date || a.end_date ? `${a.start_date ?? '…'} → ${a.end_date ?? '…'}` : 'No dates';
  const status = a.status === 'active' ? 'Active' : a.status === 'ended' ? 'Ended' : 'Cancelled';
  return `${status} · ${dates}`;
}

function AssignmentItem({
  assignment,
  manage,
  expanded,
  onToggle,
  onChanged,
}: {
  assignment: Assignment;
  manage: boolean;
  expanded: boolean;
  onToggle: () => void;
  onChanged: () => Promise<unknown>;
}) {
  const editable = manage && assignment.status === 'active';
  const title = `${assignment.employee.name}${assignment.is_lead_hand ? ' · LeadHand' : ''}${
    assignment.employee.has_account ? '' : ' · no app account'
  }`;
  return (
    <>
      <ListRow
        testID={`assignment-${assignment.id}`}
        title={title}
        subtitle={describeAssignment(assignment)}
        onPress={editable ? onToggle : undefined}
      />
      {editable && expanded ? (
        <AssignmentActions assignment={assignment} onChanged={onChanged} />
      ) : null}
    </>
  );
}

function AssignmentActions({
  assignment,
  onChanged,
}: {
  assignment: Assignment;
  onChanged: () => Promise<unknown>;
}) {
  const [start, setStart] = useState(assignment.start_date ?? '');
  const [end, setEnd] = useState(assignment.end_date ?? '');
  const [message, setMessage] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (action: () => Promise<unknown>) => action(),
    onSuccess: () => onChanged(),
    onError: (error) => setMessage(describeError(error)),
  });

  function saveDates() {
    const start_date = dateOrNull(start);
    const end_date = dateOrNull(end);
    if (start_date === 'invalid' || end_date === 'invalid') {
      setMessage('Use the format YYYY-MM-DD for dates.');
      return;
    }
    setMessage(null);
    mutation.mutate(() => updateAssignmentDates(assignment.id, { start_date, end_date }));
  }

  function confirmThen(title: string, text: string, action: () => Promise<unknown>) {
    Alert.alert(title, text, [
      { text: 'Back', style: 'cancel' },
      { text: title, style: 'destructive', onPress: () => mutation.mutate(action) },
    ]);
  }

  return (
    <Card>
      {message ? <Banner tone="danger">{message}</Banner> : null}
      <TextField
        label="Start date (YYYY-MM-DD)"
        value={start}
        onChangeText={setStart}
        placeholder="None"
      />
      <TextField
        label="End date (YYYY-MM-DD)"
        value={end}
        onChangeText={setEnd}
        placeholder="None (a future date schedules the end)"
      />
      <Button
        label="Save dates"
        variant="secondary"
        busy={mutation.isPending}
        onPress={saveDates}
      />
      <Button
        label="End assignment today"
        variant="danger"
        testID={`end-${assignment.id}`}
        busy={mutation.isPending}
        onPress={() =>
          confirmThen(
            'End assignment',
            `${assignment.employee.name} will no longer be able to clock in to this job. Their attendance is kept${
              assignment.is_lead_hand ? ', and they stop being its LeadHand' : ''
            }. If they are clocked in, they can still clock out.`,
            () => endAssignment(assignment.id),
          )
        }
      />
      <Button
        label="Cancel assignment (made in error)"
        variant="secondary"
        testID={`cancel-${assignment.id}`}
        busy={mutation.isPending}
        onPress={() =>
          confirmThen(
            'Cancel assignment',
            'Only possible if they have no attendance on this job. Otherwise, end the assignment instead.',
            () => cancelAssignment(assignment.id),
          )
        }
      />
      <Body muted>
        Assigned {formatDateTime(assignment.assigned_at)}
        {assignment.assigned_by ? ` by ${assignment.assigned_by.name}` : ''}.
      </Body>
    </Card>
  );
}

function AddEmployees({
  jobId,
  assignedIds,
  onDone,
  onCancel,
}: {
  jobId: number;
  assignedIds: Set<number>;
  onDone: () => Promise<void>;
  onCancel: () => void;
}) {
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<AssignResponse | null>(null);

  const mutation = useMutation({
    mutationFn: (body: Parameters<typeof assignEmployees>[1]) => assignEmployees(jobId, body),
    onSuccess: (result) => {
      setResponse(result);
      setSelected(new Set());
    },
    onError: (e) => setError(describeError(e)),
  });

  function submit() {
    const start_date = dateOrNull(start);
    const end_date = dateOrNull(end);
    if (start_date === 'invalid' || end_date === 'invalid') {
      setError('Use the format YYYY-MM-DD for dates.');
      return;
    }
    setError(null);
    mutation.mutate({ employee_ids: [...selected], start_date, end_date });
  }

  if (response) {
    return (
      <Card>
        <Heading>Assignment results</Heading>
        {response.results.map((r) => (
          <Body key={r.employee_id}>
            {r.status === 'assigned' ? '✓' : '✕'}{' '}
            {r.assignment?.employee.name ?? `Employee #${r.employee_id}`}: {r.message}
          </Body>
        ))}
        <Button label="Done" onPress={() => void onDone()} />
      </Card>
    );
  }

  return (
    <Card>
      <Heading>Assign employees</Heading>
      {error ? <Banner tone="danger">{error}</Banner> : null}
      <EmployeePicker
        selected={selected}
        disabledIds={assignedIds}
        onToggle={(employee) =>
          setSelected((current) => {
            const next = new Set(current);
            if (next.has(employee.id)) next.delete(employee.id);
            else next.add(employee.id);
            return next;
          })
        }
      />
      <TextField
        label="Start date (YYYY-MM-DD)"
        value={start}
        onChangeText={setStart}
        placeholder="Optional"
      />
      <TextField
        label="End date (YYYY-MM-DD)"
        value={end}
        onChangeText={setEnd}
        placeholder="Optional"
      />
      <Button
        label={`Assign ${selected.size} employee${selected.size === 1 ? '' : 's'}`}
        testID="assign-submit"
        disabled={selected.size === 0}
        busy={mutation.isPending}
        onPress={submit}
      />
      <Button label="Cancel" variant="secondary" onPress={onCancel} />
    </Card>
  );
}
