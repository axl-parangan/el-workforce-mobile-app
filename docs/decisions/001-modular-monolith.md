# ADR 001: Modular monolith backend

- Status: Accepted
- Date: 2026-11-06

## Context

The backend serves one mobile app and an admin interface for a single
construction company. The domains (accounts, workforce, jobs, timekeeping,
payroll, team notes) are closely related. Payroll reads timekeeping data,
timekeeping depends on job assignments, and many operations must be
transactionally consistent, for example accepting a batch of punches.

## Decision

Build a single Django project, one deployable and one PostgreSQL database,
and organise it by domain:

```text
backend/apps/<domain>/
├── models/      # persistence only
├── services/    # writes + business rules (plain functions, transactions)
├── selectors/   # reusable read/query logic
├── api/         # DRF serializers, thin views, urls
└── tests/
backend/common/  # domain-agnostic: error envelope, pagination, role permissions
```

Rules:

1. **Views are thin.** They parse input with a serializer, call one service
   or selector, and serialise the result.
2. **Business rules live in services.** Services take explicit arguments and
   raise `common.exceptions.ApplicationError` on rule violations. They do
   not import DRF request objects.
3. **Selectors hold reusable queries.** Use them when more than one caller
   needs the same query.
4. **Cross-domain access goes through the other app's services and
   selectors**, not through its `api/` package or by duplicating its
   queries. Foreign keys between apps are fine.
5. **No speculative abstractions.** There are no generic repositories or base
   service classes. Add a layer only when two concrete uses need it.

Excluded at this stage: microservices, Celery/Redis, message brokers, and
Kubernetes.

## Consequences

- Strong consistency through ordinary database transactions.
- One codebase to test, deploy and reason about.
- Domain boundaries are a convention, enforced by code review rather than
  network calls. If a domain ever needs extracting, the services and
  selectors layer is the seam to cut along.
- Background work, such as heavy payroll exports, will need a decision
  later. Start with synchronous code or management commands and add a task
  queue only when a measured need appears.
