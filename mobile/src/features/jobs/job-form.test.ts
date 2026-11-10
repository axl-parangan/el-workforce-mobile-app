import { makeJob } from '@/test-utils/fixtures';

import { editableFields, EMPTY_JOB_FORM, formFromJob, validateJobForm } from './job-form';

describe('editableFields', () => {
  it('limits LeadHands to name, address and dates, plus the job number on create (Q3)', () => {
    expect(editableFields('create', false)).toEqual([
      'job_number',
      'name',
      'address',
      'start_date',
      'end_date',
    ]);
    expect(editableFields('edit', false)).toEqual(['name', 'address', 'start_date', 'end_date']);
  });

  it('gives Managers and Admins every field', () => {
    expect(editableFields('edit', true)).toEqual(
      expect.arrayContaining(['job_number', 'status', 'latitude', 'longitude', 'radius']),
    );
  });
});

describe('validateJobForm', () => {
  const all = editableFields('create', true);

  it('builds a create request', () => {
    const { input, errors } = validateJobForm(
      {
        ...EMPTY_JOB_FORM,
        job_number: ' J-9 ',
        name: 'Tower',
        start_date: '2026-12-01',
        latitude: '43.6426',
        longitude: '-79.3871',
        radius: '150',
        status: 'active',
      },
      all,
    );
    expect(errors).toEqual({});
    expect(input).toEqual({
      job_number: 'J-9',
      name: 'Tower',
      address: '',
      start_date: '2026-12-01',
      end_date: null,
      status: 'active',
      latitude: '43.642600',
      longitude: '-79.387100',
      geofence_radius_meters: 150,
    });
  });

  it('never sends fields a LeadHand may not set', () => {
    const { input } = validateJobForm(
      { ...EMPTY_JOB_FORM, job_number: 'J-9', name: 'Tower', latitude: '1', longitude: '1' },
      editableFields('create', false),
    );
    expect(Object.keys(input).sort()).toEqual(
      ['address', 'end_date', 'job_number', 'name', 'start_date'].sort(),
    );
  });

  it('reports field errors', () => {
    const { errors } = validateJobForm(
      {
        ...EMPTY_JOB_FORM,
        start_date: '2026-12-10',
        end_date: '2026-12-01',
        latitude: '91',
        longitude: '',
        radius: '0',
      },
      all,
    );
    expect(errors).toEqual({
      job_number: 'Enter a job number.',
      name: 'Enter a name.',
      end_date: 'The end date cannot be before the start date.',
      longitude: 'Enter both latitude and longitude, or neither.',
      radius: 'The radius must be a whole number of metres, at least 1.',
    });
    expect(
      validateJobForm({ ...EMPTY_JOB_FORM, start_date: '2026-02-30' }, all).errors.start_date,
    ).toBe('Use the format YYYY-MM-DD.');
    expect(
      validateJobForm({ ...EMPTY_JOB_FORM, latitude: '91', longitude: '200' }, all).errors,
    ).toMatchObject({
      latitude: 'Latitude must be a number between -90 and 90.',
      longitude: 'Longitude must be a number between -180 and 180.',
    });
  });

  it('sends only changed fields when editing', () => {
    const job = makeJob({
      geofence: {
        configured: true,
        latitude: '43.642600',
        longitude: '-79.387100',
        radius_meters: null,
      },
    });
    const initial = formFromJob(job);
    const { input } = validateJobForm(
      { ...initial, name: 'Renamed', end_date: '2027-01-01' },
      editableFields('edit', true),
      initial,
    );
    expect(input).toEqual({ name: 'Renamed', end_date: '2027-01-01' });
  });

  it('clears the geofence when both coordinates are removed', () => {
    const job = makeJob({
      geofence: {
        configured: true,
        latitude: '43.642600',
        longitude: '-79.387100',
        radius_meters: 50,
      },
    });
    const initial = formFromJob(job);
    const { input } = validateJobForm(
      { ...initial, latitude: '', longitude: '', radius: '' },
      editableFields('edit', true),
      initial,
    );
    expect(input).toEqual({ latitude: null, longitude: null, geofence_radius_meters: null });
  });

  it('sends both coordinates when only one changed', () => {
    const job = makeJob({
      geofence: {
        configured: true,
        latitude: '43.642600',
        longitude: '-79.387100',
        radius_meters: null,
      },
    });
    const initial = formFromJob(job);
    const { input } = validateJobForm(
      { ...initial, latitude: '43.7' },
      editableFields('edit', true),
      initial,
    );
    expect(input).toEqual({ latitude: '43.700000', longitude: '-79.387100' });
  });
});
