# ADR 006: LeadHand group clock-in and clock-out

- Status: Accepted; implemented. Authorisation revised by ADR 011.
- Date: 2026-11-06 (revised 2026-11-10 for the Manager role)

## Context

A LeadHand can clock employees in and out of the jobs they lead, often
several at once. Some of those employees have no app account (ADR 007). A
LeadHand is also an employee and clocks in themselves. Each employee's
attendance must remain individually identifiable.

## Decision

1. **A group action is one `AttendanceBatch`** with one
   `AttendanceBatchItem` per selected employee. Each accepted item produces
   that employee's own `TimePunch` in that employee's own `WorkSession`.
   There is never a shared session.
2. **The batch records the actor and the location.** The actor is the
   LeadHand's user (`performed_by`). The location fix comes from the
   LeadHand's device and is assessed once for the whole batch (ADR 004).
3. **Validation is per employee.** Each item is checked separately:
   - the employee has an active assignment on the job, which is stored on the
     item
   - the employee is not already clocked in (for a clock-in), or has an open
     session (for a clock-out)

   Items are accepted or rejected individually, with a message. This gives
   **partial success**.
4. **Authorisation** (ADR 011). Group punches may be recorded by:
   - a **LeadHand**, for the crew of a job they **manage**: they are the
     job's `lead_hand` **and** hold an active assignment on it
   - an **Admin or Manager**, for any employee on any job. When they punch
     anyone other than themselves, the batch is an administrative entry
     (`source = admin_entry`): its location is stored but doesn't flag
     sessions, it may carry an optional reason, and it must be current.

   Employees can't record attendance for others. Authorisation uses the
   shared capability map and scope selectors.
5. **Offline.** The device queues the batch as one outbox event under its
   `idempotency_key` (ADR 002). Replaying the batch returns the original
   per-employee results. Employees who were rejected can be retried in a new
   batch.

## Consequences

- Individual correction is possible without affecting the rest of the group.
- The LeadHand's own punch is a normal single-item batch for their own
  Employee record. It needs an assignment on the job.
- Confirmed: a LeadHand can clock out an employee on a job they manage, even
  if the employee clocked in themselves or was clocked in by someone else.
