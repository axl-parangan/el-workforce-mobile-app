# ADR 010: Clients are separate, view-only records (for now)

- Status: Accepted
- Date: 2026-11-06

## Context

The company does construction work for clients. Clients are not employees,
LeadHands or Admins. In the future, clients should be able to view pay
reports and other payroll-related information about their work.

## Decision

- `clients.Client` (name, active flag) is a **standalone table with no
  relationships** to jobs, users or payroll.
- It lives in its own `clients` app, because client access will grow into a
  separate domain.
- Clients have **no app access** in the initial version.

## Future direction (not implemented)

Client access to payroll reports will need:

1. **A link between jobs and clients.** Most likely a nullable
   `Job.client` FK, so reports can be scoped to a client's jobs.
2. **Client user accounts.** This means a new `client` role on `User`, plus
   a link from those users to their `Client`. Client users must never gain
   employee capabilities.
3. **Read-only, client-scoped selectors and endpoints** for reports.
   Authorisation is enforced in the selectors, so a client sees only their
   own jobs.

Deciding now that clients are separate keeps this extension additive: new
nullable columns and a new role, with no change to existing tables.

## Consequences

- Clients can be maintained in the Django admin today, but they don't affect
  any other data.
- Questions to settle before building client access:
  - Can a job have one client or several?
  - What exactly may a client see? Hours, costs, and individual worker names
    may be sensitive.
