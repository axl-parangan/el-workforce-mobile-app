import { makeJob, makeUser } from '@/test-utils/fixtures';

import { jobPermissions } from './permissions';

const managed = makeJob({}, { manages_job: true, is_lead_hand: true });
const notManaged = makeJob({}, { manages_job: false });

it('gives Employees no crew, assignment or editing actions', () => {
  const allowed = jobPermissions(makeUser('worker'), managed);
  expect(Object.values(allowed).some(Boolean)).toBe(false);
});

it('gives LeadHands crew actions only on jobs they manage', () => {
  const lead = makeUser('leadhand');
  expect(jobPermissions(lead, managed)).toEqual({
    canEdit: true,
    editsAllFields: false,
    canRecordCrew: true,
    crewPunchesOnlineOnly: false,
    canViewAssignments: true,
    canManageAssignments: false,
    canDesignateLeadHand: false,
    canViewAttendance: true,
  });
  const elsewhere = jobPermissions(lead, notManaged);
  expect(elsewhere.canEdit || elsewhere.canRecordCrew || elsewhere.canViewAssignments).toBe(false);
  expect(elsewhere.canViewAttendance).toBe(false);
});

it.each(['manager', 'admin'] as const)('gives %s company-wide management', (role) => {
  expect(jobPermissions(makeUser(role), notManaged)).toEqual({
    canEdit: true,
    editsAllFields: true,
    canRecordCrew: true,
    crewPunchesOnlineOnly: true,
    canViewAssignments: true,
    canManageAssignments: true,
    canDesignateLeadHand: true,
    canViewAttendance: true,
  });
});
