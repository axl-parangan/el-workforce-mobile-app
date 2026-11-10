import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';

import { describeError } from '@/api/error-messages';
import {
  Banner,
  Body,
  Button,
  Card,
  Heading,
  QueryState,
  Screen,
  Segmented,
  TextField,
} from '@/components/ui';
import { useAuth } from '@/features/auth/auth-provider';
import { Capability, useCan, useRolePath } from '@/features/auth/capabilities';
import { capturePunchLocation } from '@/lib/location';

import { createJob, updateJob } from '../api';
import { jobKeys, useJob } from '../hooks';
import {
  editableFields,
  EMPTY_JOB_FORM,
  formatCoordinate,
  formFromJob,
  validateJobForm,
  type JobField,
  type JobFormErrors,
  type JobFormValues,
} from '../job-form';
import { jobPermissions } from '../permissions';
import { JOB_STATUS_LABELS, jobStatusSchema, type Job } from '../schemas';

export function NewJobScreen() {
  const can = useCan();
  if (!can(Capability.jobsCreate)) {
    return (
      <Screen>
        <Banner tone="danger">You are not allowed to create jobs.</Banner>
      </Screen>
    );
  }
  return <JobForm mode="create" editsAllFields={can(Capability.jobsEditAny)} />;
}

export function EditJobScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { user } = useAuth();
  const job = useJob(Number(id));
  if (!job.data) {
    return (
      <Screen>
        <QueryState isLoading={job.isPending} error={job.error ? describeError(job.error) : null} />
      </Screen>
    );
  }
  const allowed = jobPermissions(user, job.data.data);
  if (!allowed.canEdit) {
    return (
      <Screen>
        <Banner tone="danger">
          Only Managers, Admins and the LeadHand who manages this job can edit it.
        </Banner>
      </Screen>
    );
  }
  return <JobForm mode="edit" job={job.data.data} editsAllFields={allowed.editsAllFields} />;
}

function JobForm({
  mode,
  job,
  editsAllFields,
}: {
  mode: 'create' | 'edit';
  job?: Job;
  editsAllFields: boolean;
}) {
  const router = useRouter();
  const to = useRolePath();
  const queryClient = useQueryClient();
  const fields = editableFields(mode, editsAllFields);
  const initial = job ? formFromJob(job) : EMPTY_JOB_FORM;
  const [values, setValues] = useState<JobFormValues>(initial);
  const [errors, setErrors] = useState<JobFormErrors>({});
  const [locating, setLocating] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: (input: ReturnType<typeof validateJobForm>['input']) =>
      job ? updateJob(job.id, input) : createJob(input),
    onSuccess: async (saved) => {
      // A LeadHand who creates a job is assigned to it, so refresh their lists too.
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: jobKeys.all }),
        queryClient.invalidateQueries({ queryKey: jobKeys.myAssignments }),
      ]);
      if (job) router.back();
      else router.replace(to(`/jobs/${saved.id}`));
    },
  });

  const has = (field: JobField) => fields.includes(field);
  const set = (field: JobField) => (value: string) =>
    setValues((current) => ({ ...current, [field]: value }));

  function submit() {
    setNotice(null);
    const result = validateJobForm(values, fields, job ? initial : undefined);
    setErrors(result.errors);
    if (Object.keys(result.errors).length) return;
    if (job && Object.keys(result.input).length === 0) {
      setNotice('Nothing has changed.');
      return;
    }
    save.mutate(result.input);
  }

  async function fillCurrentLocation() {
    setLocating(true);
    setNotice(null);
    const location = await capturePunchLocation();
    setLocating(false);
    if (location.status !== 'captured') {
      setNotice('Could not get your location. Check that location is on and allowed for this app.');
      return;
    }
    setValues((current) => ({
      ...current,
      latitude: formatCoordinate(location.latitude),
      longitude: formatCoordinate(location.longitude),
    }));
    if (location.accuracyMeters !== null && location.accuracyMeters > 30) {
      setNotice(
        `Location accuracy is about ${Math.round(location.accuracyMeters)} m. Check the coordinates.`,
      );
    }
  }

  return (
    <Screen>
      {save.error ? <Banner tone="danger">{describeError(save.error)}</Banner> : null}
      {notice ? <Banner tone="info">{notice}</Banner> : null}
      {!editsAllFields ? (
        <Body muted>
          {mode === 'create'
            ? 'You will be the LeadHand of this job. A Manager can set its status and site location.'
            : 'You can change the name, address and dates. A Manager can change the rest.'}
        </Body>
      ) : null}

      <Card>
        {has('job_number') ? (
          <TextField
            label="Job number"
            value={values.job_number}
            onChangeText={set('job_number')}
            autoCapitalize="characters"
            error={errors.job_number}
          />
        ) : (
          <Body>Job number: {values.job_number}</Body>
        )}
        <TextField
          label="Name"
          value={values.name}
          onChangeText={set('name')}
          error={errors.name}
        />
        <TextField label="Address" value={values.address} onChangeText={set('address')} />
        <TextField
          label="Start date (YYYY-MM-DD)"
          value={values.start_date}
          onChangeText={set('start_date')}
          placeholder="Optional"
          keyboardType="numbers-and-punctuation"
          error={errors.start_date}
        />
        <TextField
          label="End date (YYYY-MM-DD)"
          value={values.end_date}
          onChangeText={set('end_date')}
          placeholder="Optional"
          keyboardType="numbers-and-punctuation"
          error={errors.end_date}
        />
      </Card>

      {has('status') ? (
        <Card>
          <Heading>Status</Heading>
          <Segmented
            value={values.status}
            onChange={(status) => setValues((current) => ({ ...current, status }))}
            options={jobStatusSchema.options.map((status) => ({
              value: status,
              label: JOB_STATUS_LABELS[status],
            }))}
          />
          <Body muted>Only active jobs accept clock-ins.</Body>
        </Card>
      ) : null}

      {has('latitude') ? (
        <Card>
          <Heading>Site location (geofence)</Heading>
          <Body muted>
            Punches are checked against a circle around this point. Leave both empty for no
            geofence.
          </Body>
          <TextField
            label="Latitude"
            value={values.latitude}
            onChangeText={set('latitude')}
            keyboardType="numbers-and-punctuation"
            error={errors.latitude}
          />
          <TextField
            label="Longitude"
            value={values.longitude}
            onChangeText={set('longitude')}
            keyboardType="numbers-and-punctuation"
            error={errors.longitude}
          />
          <Button
            label="Use my current location"
            variant="secondary"
            busy={locating}
            testID="use-current-location"
            onPress={() => void fillCurrentLocation()}
          />
          <TextField
            label="Radius in metres"
            value={values.radius}
            onChangeText={set('radius')}
            placeholder="100 (default)"
            keyboardType="number-pad"
            error={errors.radius}
          />
        </Card>
      ) : null}

      <Button
        label={mode === 'create' ? 'Create job' : 'Save changes'}
        busy={save.isPending}
        testID="save-job"
        onPress={submit}
      />
    </Screen>
  );
}
