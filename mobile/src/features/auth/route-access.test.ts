/**
 * Route groups are the first line of UX protection: a role group only
 * contains the screens that role may use (decision M2). The API enforces the
 * actual permissions.
 */
// eslint-disable-next-line @typescript-eslint/no-require-imports
const fs = require('node:fs') as {
  readdirSync: (path: string, options: { recursive: true }) => string[];
};

function routes(group: string): string[] {
  return fs
    .readdirSync(`${process.cwd()}/app/(${group})/${group}`, { recursive: true })
    .map((file) => file.replace(/\\/g, '/'))
    .filter((file) => file.endsWith('.tsx') && !file.endsWith('_layout.tsx'))
    .sort();
}

it('gives Employees only their own time, jobs, history and account', () => {
  expect(routes('worker')).toEqual([
    'account.tsx',
    'history/[id].tsx',
    'history/index.tsx',
    'index.tsx',
    'jobs/[id]/index.tsx',
    'jobs/index.tsx',
  ]);
});

it('gives LeadHands crew screens but not LeadHand designation', () => {
  const leadhand = routes('leadhand');
  expect(leadhand).toEqual(
    expect.arrayContaining([
      'jobs/[id]/crew.tsx',
      'jobs/[id]/assignments.tsx',
      'jobs/[id]/edit.tsx',
      'jobs/new.tsx',
      'attendance/index.tsx',
      'attendance/[id].tsx',
    ]),
  );
  expect(leadhand).not.toContain('jobs/[id]/lead-hand.tsx');
});

it.each(['manager', 'admin'])('gives %s every management screen', (group) => {
  expect(routes(group)).toEqual([...routes('leadhand'), 'jobs/[id]/lead-hand.tsx'].sort());
});
