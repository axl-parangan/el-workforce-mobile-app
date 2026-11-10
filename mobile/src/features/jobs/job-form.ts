import type { Job, JobInput, JobStatus } from './schemas';

export type JobFormValues = {
  job_number: string;
  name: string;
  address: string;
  start_date: string;
  end_date: string;
  status: JobStatus;
  latitude: string;
  longitude: string;
  radius: string;
};

export type JobField = keyof JobFormValues;
export type JobFormErrors = Partial<Record<JobField, string>>;

export const EMPTY_JOB_FORM: JobFormValues = {
  job_number: '',
  name: '',
  address: '',
  start_date: '',
  end_date: '',
  status: 'planned',
  latitude: '',
  longitude: '',
  radius: '',
};

/**
 * Fields the form shows (docs/api/jobs.md, Q3). LeadHands may set the job
 * number only when creating, and never status or geofence.
 */
export function editableFields(mode: 'create' | 'edit', editsAllFields: boolean): JobField[] {
  if (editsAllFields) {
    return [
      'job_number',
      'name',
      'address',
      'start_date',
      'end_date',
      'status',
      'latitude',
      'longitude',
      'radius',
    ];
  }
  const limited: JobField[] = ['name', 'address', 'start_date', 'end_date'];
  return mode === 'create' ? ['job_number', ...limited] : limited;
}

export function formFromJob(job: Job): JobFormValues {
  return {
    job_number: job.job_number,
    name: job.name,
    address: job.address,
    start_date: job.start_date ?? '',
    end_date: job.end_date ?? '',
    status: job.status,
    latitude: job.geofence.latitude ?? '',
    longitude: job.geofence.longitude ?? '',
    radius: job.geofence.radius_meters?.toString() ?? '',
  };
}

const DATE = /^\d{4}-\d{2}-\d{2}$/;

function validDate(value: string): boolean {
  if (!DATE.test(value)) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().startsWith(value);
}

function coordinate(value: string, limit: number): number | null {
  if (!/^-?\d+(\.\d+)?$/.test(value.trim())) return null;
  const number = Number(value);
  return Math.abs(number) <= limit ? number : null;
}

/** Same coordinate form the API returns (six decimals). */
export function formatCoordinate(value: number): string {
  return value.toFixed(6);
}

/**
 * Validates the form and builds the request body. For edits, only fields that
 * changed from `initial` are sent. The server re-validates everything.
 */
export function validateJobForm(
  values: JobFormValues,
  fields: JobField[],
  initial?: JobFormValues,
): { input: JobInput; errors: JobFormErrors } {
  const errors: JobFormErrors = {};
  const has = (field: JobField) => fields.includes(field);
  const input: JobInput = {};

  if (has('job_number')) {
    if (!values.job_number.trim()) errors.job_number = 'Enter a job number.';
    input.job_number = values.job_number.trim();
  }
  if (has('name')) {
    if (!values.name.trim()) errors.name = 'Enter a name.';
    input.name = values.name.trim();
  }
  if (has('address')) input.address = values.address.trim();

  for (const field of ['start_date', 'end_date'] as const) {
    if (!has(field)) continue;
    const value = values[field].trim();
    if (value && !validDate(value)) errors[field] = 'Use the format YYYY-MM-DD.';
    input[field] = value || null;
  }
  if (input.start_date && input.end_date && !errors.end_date && input.end_date < input.start_date) {
    errors.end_date = 'The end date cannot be before the start date.';
  }

  if (has('status')) input.status = values.status;

  if (has('latitude') && has('longitude')) {
    const lat = values.latitude.trim();
    const lng = values.longitude.trim();
    if (!lat && !lng) {
      input.latitude = null;
      input.longitude = null;
    } else if (!lat || !lng) {
      errors[lat ? 'longitude' : 'latitude'] = 'Enter both latitude and longitude, or neither.';
    } else {
      const latitude = coordinate(lat, 90);
      const longitude = coordinate(lng, 180);
      if (latitude === null) errors.latitude = 'Latitude must be a number between -90 and 90.';
      if (longitude === null) errors.longitude = 'Longitude must be a number between -180 and 180.';
      if (latitude !== null && longitude !== null) {
        input.latitude = formatCoordinate(latitude);
        input.longitude = formatCoordinate(longitude);
      }
    }
  }
  if (has('radius')) {
    const radius = values.radius.trim();
    if (radius && (!/^\d+$/.test(radius) || Number(radius) < 1)) {
      errors.radius = 'The radius must be a whole number of metres, at least 1.';
    }
    input.geofence_radius_meters = radius ? Number(radius) : null;
  }

  if (initial) {
    const full = { ...input };
    const before = validateJobForm(initial, fields).input;
    for (const key of Object.keys(input) as (keyof JobInput)[]) {
      if (input[key] === before[key]) delete input[key];
    }
    // Coordinates travel as a pair, so the server never sees half a location.
    if ('latitude' in input || 'longitude' in input) {
      input.latitude = full.latitude;
      input.longitude = full.longitude;
    }
  }
  return { input, errors };
}
