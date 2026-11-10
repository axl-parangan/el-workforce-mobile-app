import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';

import { describeError } from '@/api/error-messages';
import { Banner, Body, Button, Card, Heading, QueryState, Screen } from '@/components/ui';
import { useAuth } from '@/features/auth/auth-provider';

import { designateLeadHand } from '../api';
import { EmployeePicker } from '../components/employee-picker';
import { jobKeys, useJob } from '../hooks';
import { jobPermissions } from '../permissions';
import type { EmployeeOption } from '../schemas';

/** Designate or clear a job's LeadHand (Managers and Admins). */
export function LeadHandScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const jobId = Number(id);
  const { user } = useAuth();
  const router = useRouter();
  const queryClient = useQueryClient();
  const job = useJob(jobId);
  const [choice, setChoice] = useState<EmployeeOption | null>(null);

  const mutation = useMutation({
    mutationFn: (employeeId: number | null) => designateLeadHand(jobId, employeeId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: jobKeys.all });
      router.back();
    },
  });

  if (!job.data) {
    return (
      <Screen>
        <QueryState isLoading={job.isPending} error={job.error ? describeError(job.error) : null} />
      </Screen>
    );
  }
  if (!jobPermissions(user, job.data.data).canDesignateLeadHand) {
    return (
      <Screen>
        <Banner tone="danger">Only Managers and Admins can change the LeadHand of a job.</Banner>
      </Screen>
    );
  }
  const current = job.data.data.lead_hand;

  return (
    <Screen>
      {mutation.error ? <Banner tone="danger">{describeError(mutation.error)}</Banner> : null}
      <Card>
        <Heading>Current LeadHand</Heading>
        <Body>{current?.name ?? 'None designated'}</Body>
        <Body muted>
          The new LeadHand is assigned to the job if they are not already. The previous LeadHand
          stays on the crew.
        </Body>
      </Card>
      <Card>
        <Heading>Choose a LeadHand</Heading>
        <EmployeePicker
          role="leadhand"
          selected={new Set(choice ? [choice.id] : [])}
          disabledIds={new Set(current ? [current.employee_id] : [])}
          disabledNote="Current LeadHand"
          onToggle={(employee) => setChoice(choice?.id === employee.id ? null : employee)}
        />
      </Card>
      <Button
        label={choice ? `Make ${choice.name} the LeadHand` : 'Choose someone above'}
        testID="designate-lead-hand"
        disabled={!choice}
        busy={mutation.isPending}
        onPress={() => choice && mutation.mutate(choice.id)}
      />
      {current ? (
        <Button
          label="Remove the LeadHand"
          variant="secondary"
          testID="clear-lead-hand"
          busy={mutation.isPending}
          onPress={() => mutation.mutate(null)}
        />
      ) : null}
    </Screen>
  );
}
