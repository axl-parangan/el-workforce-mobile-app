# Mobile QA checklist: jobs, assignments and attendance

Manual checks on real devices (one Android, one iPhone) with a development
build pointed at a backend that has the demo data. Automated tests cover the
logic; this list covers what only a device can show: GPS, connectivity
changes, app lifecycle and layout.

**Accounts:** `demo.worker@example.com`, `demo.lead@example.com`,
`demo.manager@example.com`, `demo.admin@example.com`. These exist only in
the development database; there is no seed command yet. The LeadHand
manages `DEMO-1` and the worker is assigned to it.

**Turning the network off:** use airplane mode (with Wi-Fi off). Checking the
server afterwards: the staff attendance screen, or the Django admin.

## 1. Sign-in and navigation

- [ ] Wrong password shows "Email or password is incorrect."
- [ ] An email with a trailing space (from autocomplete) still signs in.
- [ ] Each role lands on its own tabs:
  - Employee: Time, Jobs, History, Account
  - LeadHand, Manager, Admin: Time, Jobs, Attendance, History, Account
- [ ] Kill and reopen the app while offline: still signed in, Time screen
  shows the cached jobs and status.

## 2. Employee attendance (online)

- [ ] Clock in to `DEMO-1`: the location prompt appears once; the notice
  says "Clocked in to DEMO-1 … at HH:MM" (company time).
- [ ] Deny location permission, clock in: it is still recorded (flagged for
  review on the server).
- [ ] Clock out: History shows one closed session with the right times.
- [ ] Clock in again the same day: a second session appears (multiple
  sessions per day).

## 3. Offline attendance and sync

- [ ] Airplane mode on. Clock in. The notice says "Saved on this phone"; the
  Time screen shows "Clocked in · not sent yet"; a yellow banner shows
  "1 punch saved on this phone will be sent automatically…".
- [ ] Still offline, clock out. Banner shows 2 punches.
- [ ] Airplane mode off. Within a few seconds (or after foregrounding the
  app) the banner disappears. History, My sessions shows **one** closed
  session with the offline times. History, On this phone shows both as
  "Sent and accepted".
- [ ] Repeat, but kill the app while offline after punching; reopen online.
  The punches sync once.
- [ ] Toggle airplane mode on and off quickly several times while punches
  are waiting. Still exactly one session (no duplicates).

## 4. Job switching

Needs a second job: as the Manager, create one (section 7) and assign the
demo worker to it.

- [ ] Clocked in at job A, press "Switch here" on job B, confirm. Notice
  says "Moved from A to B at HH:MM". Staff attendance shows A closed and B
  opened at the same minute.
- [ ] Offline: switch A → B, go online. Both punches sync, same result.
- [ ] As the Manager, put job B on hold. As the worker (online), switch
  A → B. The notice shows that the clock-in at B was refused and offers
  "Clock back in to A". Nothing changes until it is pressed; pressing it
  clocks in to A.

## 5. Shared phone (account ownership)

- [ ] Signed in as the worker, airplane mode on, clock in.
- [ ] Account, Sign out: a warning says 1 punch has not been sent and stays
  on this phone. Choose "Sign out".
- [ ] The sign-in screen says 1 punch is waiting for the account that
  recorded it.
- [ ] Airplane mode off. Sign in as the LeadHand. A blue banner says 1 punch
  from another account is waiting. On the server, the worker has **no** new
  punch.
- [ ] Sign out (no warning: the LeadHand has nothing pending). Sign in as
  the worker: the punch syncs; the banner disappears.

## 6. LeadHand crew

- [ ] As the LeadHand, open `DEMO-1`: buttons for Crew and group clock,
  Crew assignments, Attendance for this job, Edit job. No "Change LeadHand".
- [ ] Crew: select the worker, Clock in selected. Results list shows the
  worker accepted.
- [ ] Offline: select, Clock out selected. Message says it was saved; after
  going online, History, On this phone shows the group punch as sent.
- [ ] Open a job the LeadHand is assigned to but does not lead (assign them
  as the Manager): no crew or edit buttons.
- [ ] Edit job: only name, address and dates are shown.
- [ ] New job: create one; the LeadHand is shown as leading it.

## 7. Manager and Admin

- [ ] Jobs: search by number and name; status filter works.
- [ ] New job: fill in every field; "Use my current location" fills the
  coordinates; save opens the job with the site location shown.
- [ ] Edit: change only the name; the save succeeds.
- [ ] Assignments, Assign employees: search, select two, assign. Results
  show one line per employee; an already-assigned employee is greyed out.
- [ ] Change an assignment's dates, end one, cancel one (made in error). A
  cancel on an assignment with attendance shows "end it instead".
- [ ] Change LeadHand: only LeadHand accounts are listed. Designate, then
  remove.
- [ ] Crew group clock while online: works, with an optional reason. Offline:
  shows "need a connection" and "Try again"; after going online, "Try again"
  records it once.
- [ ] Attendance: Needs review lists flagged sessions; open one, approve
  with a reason. The Manager's own session shows "You cannot review your own
  timesheet."

## 8. Stale data and edge cases

- [ ] Set the phone's clock forward by two days while offline (or leave it
  offline for over 24 hours): Time and Jobs show "may be out of date", and
  clock-in still works.
- [ ] Assign the worker with a future start date: clock-in asks "Clock in
  anyway?" with the reason; Cancel records nothing.
- [ ] A user without an employee record sees "No employee record is linked".
- [ ] Large text (accessibility font size): Time and Crew screens remain
  usable; buttons are not clipped.
