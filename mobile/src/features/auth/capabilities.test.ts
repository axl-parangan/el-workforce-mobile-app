import { Capability, can, rolePath } from './capabilities';
import { currentUserSchema, type CurrentUser } from './schemas';

function user(overrides: Partial<CurrentUser> = {}): CurrentUser {
  return {
    id: 1,
    email: 'lee@example.com',
    first_name: '',
    last_name: '',
    role: 'leadhand',
    capabilities: ['attendance.record_self', 'attendance.record_crew'],
    employee: { id: 7, name: 'Lee Lead' },
    ...overrides,
  };
}

describe('can', () => {
  it('reads capabilities issued by the server', () => {
    expect(can(user(), Capability.attendanceRecordCrew)).toBe(true);
    expect(can(user(), Capability.attendanceReview)).toBe(false);
  });

  it('is true when any of several capabilities is held', () => {
    expect(can(user(), Capability.attendanceRecordAny, Capability.attendanceRecordCrew)).toBe(true);
  });

  it('is false without a user', () => {
    expect(can(null, Capability.attendanceRecordSelf)).toBe(false);
  });

  it('never infers capabilities from the role name', () => {
    expect(can(user({ role: 'admin', capabilities: [] }), Capability.jobsViewAny)).toBe(false);
  });
});

describe('rolePath', () => {
  it('prefixes paths with the role group (M2)', () => {
    expect(rolePath('worker', '/jobs/3')).toBe('/worker/jobs/3');
    expect(rolePath('leadhand')).toBe('/leadhand');
    expect(rolePath('manager', '/attendance')).toBe('/manager/attendance');
    expect(rolePath('admin', '/history')).toBe('/admin/history');
  });

  it('has no prefix for an unknown role', () => {
    expect(rolePath('unknown', '/jobs')).toBe('/jobs');
  });
});

describe('currentUserSchema', () => {
  const base = { id: 1, email: 'a@example.com', first_name: '', last_name: '', role: 'worker' };

  it('parses the /auth/me/ response', () => {
    const parsed = currentUserSchema.parse({
      ...base,
      capabilities: ['jobs.view_assigned'],
      employee: { id: 3, name: 'Wendy' },
    });
    expect(parsed.capabilities).toEqual(['jobs.view_assigned']);
    expect(parsed.employee).toEqual({ id: 3, name: 'Wendy' });
  });

  it('accepts a profile cached before capabilities existed', () => {
    const parsed = currentUserSchema.parse(base);
    expect(parsed.capabilities).toEqual([]);
    expect(parsed.employee).toBeNull();
  });

  it('maps an unknown role instead of failing sign-in', () => {
    expect(currentUserSchema.parse({ ...base, role: 'owner' }).role).toBe('unknown');
  });
});
