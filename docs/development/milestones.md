What I would do after this milestone
I'd follow this development sequence:
1. Timekeeping backend

   Individual attendance, group operations, offline batch synchronization, and GPS validation.
   Next
2. Jobs and assignments API

   Create jobs, assign employees, manage LeadHands, and retrieve assigned jobs.
3. Mobile authentication and timekeeping

   Connect Expo to the backend, implement local SQLite queue, and build the worker clock-in/out screens.
4. LeadHand mobile workflow

   Worker selection, group clock-in/out, and individual result handling.
5. Attendance review and payroll

   Review exceptions, approve sessions, and generate payroll runs from approved attendance.
One important recommendation: Don't let OpenCode consider the timekeeping milestone complete just because its tests pass. Before moving on, have it demonstrate this specific scenario end-to-end:

A worker clocks in offline at 8:00 AM, clocks out offline at 5:00 PM, reconnects at 6:00 PM, and both events synchronize exactly once, producing one correctly closed work session.

That is the most important proof that the architecture is working as intended.
