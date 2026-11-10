import { compareByProcessingOrder, toLocationPayload, type PunchPayload } from './punch-events';

function punch(action: PunchPayload['action_type'], at: string): PunchPayload {
  return {
    event_id: `${action}-${at}`,
    action_type: action,
    job_id: 1,
    captured_at: at,
    location: null,
  };
}

describe('compareByProcessingOrder (server rule Q13)', () => {
  it('orders by device time, then clock-outs first, then queue order', () => {
    const events = [
      { payload: punch('clock_in', '2026-03-10T10:30:00-04:00'), sequence: 2 },
      { payload: punch('clock_out', '2026-03-10T10:30:00-04:00'), sequence: 3 },
      { payload: punch('clock_in', '2026-03-10T08:00:00-04:00'), sequence: 5 },
      { payload: punch('clock_in', '2026-03-10T14:30:00Z'), sequence: 1 },
    ];
    const ordered = [...events].sort(compareByProcessingOrder).map((e) => e.sequence);
    // 10:30-04:00 equals 14:30Z: clock-out first, then the two clock-ins by sequence.
    expect(ordered).toEqual([5, 3, 1, 2]);
  });
});

describe('toLocationPayload', () => {
  it('maps a captured fix and drops unavailable ones', () => {
    expect(
      toLocationPayload({
        status: 'captured',
        latitude: 43.6,
        longitude: -79.3,
        accuracyMeters: 8,
        capturedAt: '2026-03-10T12:00:00Z',
        isMocked: false,
      }),
    ).toEqual({ latitude: 43.6, longitude: -79.3, accuracy_meters: 8 });
    expect(toLocationPayload({ status: 'unavailable', reason: 'permission_denied' })).toBeNull();
  });
});
