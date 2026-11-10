import type { PendingEvent } from '@/offline/queue/pending-events';

import { describeDeviceEvent } from './device-event-row';

function event(overrides: Partial<PendingEvent>, payload: object = {}): PendingEvent {
  return {
    id: 'e1',
    type: 'punch',
    payload: {
      event_id: 'e1',
      action_type: 'clock_in',
      job_id: 3,
      captured_at: '2026-03-10T08:00:00-04:00',
      location: null,
      ...payload,
    },
    status: 'pending',
    attempts: 0,
    lastError: null,
    outcome: null,
    userId: 1,
    sequence: 1,
    createdAt: '2026-03-10T12:00:00Z',
    updatedAt: '2026-03-10T12:00:00Z',
    ...overrides,
  };
}

const label = (jobId: number) => `J-${jobId}`;

it('describes waiting, sent, partly refused and refused punches', () => {
  expect(describeDeviceEvent(event({}), label)).toEqual({
    title: 'Clock in · J-3 · Mar 10, 08:00',
    subtitle: 'Waiting to be sent',
  });
  expect(describeDeviceEvent(event({ attempts: 2, lastError: 'Offline' }), label).subtitle).toBe(
    'Waiting to be sent (tried 2×: Offline)',
  );
  expect(describeDeviceEvent(event({ status: 'synced' }), label).subtitle).toBe(
    'Sent and accepted',
  );
  expect(
    describeDeviceEvent(
      event(
        {
          status: 'synced',
          outcome: {
            code: 'partially_rejected',
            message: '1 of 2 accepted.',
            results: [
              {
                employeeId: 1,
                employee: 'Ana',
                status: 'accepted',
                code: 'clocked_in',
                message: '',
              },
              {
                employeeId: 2,
                employee: 'Bo',
                status: 'rejected',
                code: 'x',
                message: 'Not assigned.',
              },
            ],
          },
        },
        { employee_ids: [1, 2] },
      ),
      label,
    ),
  ).toEqual({
    title: 'Group clock in (2) · J-3 · Mar 10, 08:00',
    subtitle: 'Sent · 1 of 2 accepted. Refused: Bo (Not assigned.)',
  });
  expect(
    describeDeviceEvent(
      event({
        status: 'rejected',
        outcome: { code: 'no_open_session', message: 'No open session.' },
      }),
      label,
    ).subtitle,
  ).toBe('Refused: No open session.');
});
