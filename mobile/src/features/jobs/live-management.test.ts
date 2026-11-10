/**
 * Job and assignment management against a running backend, using the app's
 * own form logic, permission helper and response schemas. Skipped unless
 * LIVE_API_URL is set (see src/test-utils/live-api.ts).
 */
import { paginatedSchema } from '@/api/pagination';
import { currentUserSchema, type CurrentUser } from '@/features/auth/schemas';
import { crewSchema } from '@/features/timekeeping/schemas';
import { get, live, request, signIn, type Account } from '@/test-utils/live-api';

import { editableFields, EMPTY_JOB_FORM, formFromJob, validateJobForm } from './job-form';
import { jobPermissions } from './permissions';
import { assignmentSchema, assignResponseSchema, employeeOptionSchema, jobSchema } from './schemas';

live('job and assignment management against the live backend', () => {
  let manager: Account;
  let lead: Account;
  let worker: Account;
  const users: Record<string, CurrentUser> = {};
  const suffix = Math.random().toString(36).slice(2, 8).toUpperCase();

  beforeAll(async () => {
    manager = await signIn('demo.manager@example.com', 'Demo-manager-2026');
    lead = await signIn('demo.lead@example.com', 'Demo-lead-2026');
    worker = await signIn('demo.worker@example.com', 'Demo-worker-2026');
    for (const [name, account] of Object.entries({ manager, lead, worker })) {
      users[name] = currentUserSchema.parse(await get(account, '/auth/me/'));
    }
  });

  it('lists employees for Managers without pay data, and refuses others', async () => {
    const response = await request('GET', '/workforce/employees/?is_active=true', {
      token: manager.token,
    });
    expect(response.status).toBe(200);
    const page = paginatedSchema(employeeOptionSchema).parse(response.json);
    expect(page.results.length).toBeGreaterThan(0);
    expect(JSON.stringify(response.json)).not.toMatch(/rate|pay|salary/i);

    for (const account of [lead, worker]) {
      expect((await request('GET', '/workforce/employees/', { token: account.token })).status).toBe(
        403,
      );
    }
  });

  it('runs the Manager → LeadHand → Employee workflow', async () => {
    // Manager creates a job with every field, from the app's form logic.
    const create = validateJobForm(
      {
        ...EMPTY_JOB_FORM,
        job_number: `QA-${suffix}`,
        name: 'Mobile QA site',
        address: '1 Test St',
        status: 'active',
        latitude: '43.6426',
        longitude: '-79.3871',
        radius: '150',
      },
      editableFields('create', true),
    );
    expect(create.errors).toEqual({});
    const created = await request('POST', '/jobs/', { token: manager.token, body: create.input });
    expect(created.status).toBe(201);
    let job = jobSchema.parse(created.json);
    expect(job.geofence).toMatchObject({ configured: true, radius_meters: 150 });

    // Manager edits: only changed fields are sent.
    const initial = formFromJob(job);
    const edit = validateJobForm(
      { ...initial, name: 'Mobile QA site (renamed)' },
      editableFields('edit', true),
      initial,
    );
    expect(edit.input).toEqual({ name: 'Mobile QA site (renamed)' });
    job = jobSchema.parse(
      (await request('PATCH', `/jobs/${job.id}/`, { token: manager.token, body: edit.input })).json,
    );
    expect(job.name).toBe('Mobile QA site (renamed)');

    // Manager assigns the worker and designates the LeadHand.
    const assigned = assignResponseSchema.parse(
      (
        await request('POST', `/jobs/${job.id}/assignments/`, {
          token: manager.token,
          body: { employee_ids: [worker.employeeId], start_date: null, end_date: null },
        })
      ).json,
    );
    expect(assigned.results).toMatchObject([
      { employee_id: worker.employeeId, status: 'assigned' },
    ]);
    job = jobSchema.parse(
      (
        await request('PUT', `/jobs/${job.id}/lead-hand/`, {
          token: manager.token,
          body: { employee_id: lead.employeeId },
        })
      ).json,
    );
    expect(job.lead_hand?.employee_id).toBe(lead.employeeId);

    // The LeadHand now manages the job: crew actions, limited edits.
    const leadView = jobSchema.parse(await get(lead, `/jobs/${job.id}/`));
    const leadAllowed = jobPermissions(users.lead!, leadView);
    expect(leadAllowed).toMatchObject({
      canRecordCrew: true,
      canEdit: true,
      editsAllFields: false,
      canManageAssignments: false,
    });
    const crew = crewSchema.parse(await get(lead, `/timekeeping/jobs/${job.id}/crew/`));
    expect(crew.crew.map((m) => m.employee.id).sort()).toEqual(
      [lead.employeeId, worker.employeeId].sort(),
    );

    const leadEdit = validateJobForm(
      { ...formFromJob(leadView), address: '2 Test St', status: 'on_hold' },
      editableFields('edit', false),
      formFromJob(leadView),
    );
    expect(leadEdit.input).toEqual({ address: '2 Test St' }); // the form never sends status
    expect(
      (await request('PATCH', `/jobs/${job.id}/`, { token: lead.token, body: leadEdit.input }))
        .status,
    ).toBe(200);
    // The server enforces the same limit.
    const forbidden = await request('PATCH', `/jobs/${job.id}/`, {
      token: lead.token,
      body: { status: 'on_hold' },
    });
    expect(forbidden.status).toBe(403);
    expect(forbidden.json.error.code).toBe('field_not_editable');

    // The Employee sees the job, but no crew or assignments.
    const workerView = jobSchema.parse(await get(worker, `/jobs/${job.id}/`));
    expect(Object.values(jobPermissions(users.worker!, workerView)).some(Boolean)).toBe(false);
    expect(
      (await request('GET', `/jobs/${job.id}/assignments/`, { token: worker.token })).status,
    ).toBe(403);
    expect([403, 404]).toContain(
      (await request('GET', `/timekeeping/jobs/${job.id}/crew/`, { token: worker.token })).status,
    );

    // Manager ends the worker's assignment and cancels the LeadHand's (no sessions).
    const assignments = paginatedSchema(assignmentSchema).parse(
      await get(manager, `/jobs/${job.id}/assignments/`),
    );
    const workerAssignment = assignments.results.find((a) => a.employee.id === worker.employeeId)!;
    const leadAssignment = assignments.results.find((a) => a.employee.id === lead.employeeId)!;
    const ended = assignmentSchema.parse(
      (
        await request('POST', `/assignments/${workerAssignment.id}/end/`, {
          token: manager.token,
          body: {},
        })
      ).json,
    );
    expect(ended.status).toBe('ended');
    const cancelled = assignmentSchema.parse(
      (
        await request('POST', `/assignments/${leadAssignment.id}/cancel/`, {
          token: manager.token,
          body: {},
        })
      ).json,
    );
    expect(cancelled.status).toBe('cancelled');
    job = jobSchema.parse(await get(manager, `/jobs/${job.id}/`));
    expect(job.lead_hand).toBeNull();

    // Tidy up the dev database.
    await request('PATCH', `/jobs/${job.id}/`, {
      token: manager.token,
      body: { status: 'completed' },
    });
  });

  it('lets a LeadHand create a job with limited fields and lead it', async () => {
    const create = validateJobForm(
      { ...EMPTY_JOB_FORM, job_number: `QA-LH-${suffix}`, name: 'LeadHand QA site' },
      editableFields('create', false),
    );
    const response = await request('POST', '/jobs/', { token: lead.token, body: create.input });
    expect(response.status).toBe(201);
    const job = jobSchema.parse(response.json);
    expect(job.viewer).toMatchObject({ manages_job: true, is_lead_hand: true });

    // Tidy up: cancelling a job does not end its assignments (Q8), so cancel the LeadHand's too.
    await request('PATCH', `/jobs/${job.id}/`, {
      token: manager.token,
      body: { status: 'cancelled' },
    });
    const assignments = paginatedSchema(assignmentSchema).parse(
      await get(manager, `/jobs/${job.id}/assignments/`),
    );
    for (const assignment of assignments.results) {
      await request('POST', `/assignments/${assignment.id}/cancel/`, {
        token: manager.token,
        body: {},
      });
    }
  });
});
