import type { StaffSession } from '@/features/timekeeping/schemas';
import { makeUser } from '@/test-utils/fixtures';

import { reviewBlocker } from './staff-session-screen';

function session(employeeId: number, status: 'open' | 'closed' = 'closed') {
  return { employee: { id: employeeId, name: 'X' }, session_status: status } as StaffSession;
}

it('lets Managers and Admins review other people’s closed sessions', () => {
  expect(reviewBlocker(makeUser('manager'), session(999))).toBeNull();
  expect(reviewBlocker(makeUser('admin'), session(999))).toBeNull();
});

it('never offers review of your own timesheet', () => {
  const manager = makeUser('manager');
  expect(reviewBlocker(manager, session(manager.employee!.id))).toMatch(/your own timesheet/);
});

it('does not offer review to LeadHands, or for open sessions', () => {
  expect(reviewBlocker(makeUser('leadhand'), session(999))).toMatch(/Managers and Admins/);
  expect(reviewBlocker(makeUser('manager'), session(999, 'open'))).toMatch(/once they close/);
});
