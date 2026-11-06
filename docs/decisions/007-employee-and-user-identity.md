# ADR 007: Employees, user accounts, and email login

- Status: Accepted
- Date: 2026-11-06

## Context

Not every worker uses the app. Some workers are only clocked in and out by a
LeadHand. Attendance and payroll must still be recorded for them. Login
credentials and employment records have different lifecycles: someone can be
hired before they get an account, or lose app access while staying employed.

## Decision

### Employee vs User

- **`workforce.Employee`** represents a person employed by the company. Every
  worker and every LeadHand has one. It is defined with the ERD.
- **`accounts.User`** represents a login identity and its application role
  (`admin`, `leadhand` or `worker`).
- The relationship is an **optional one-to-one link** from Employee to User:
  - an employee can exist without a user account
  - an employee has at most one user account, and a user account links to at
    most one employee
  - **LeadHands must** have a user account
  - **workers who clock themselves in or out must** have a user account
  - workers without accounts have their attendance recorded by an authorised
    LeadHand
- Timekeeping and payroll records refer to the **Employee** as their subject.
  The **User** appears only as the actor, meaning who recorded or approved
  something (ADR 003, ADR 006).

### Login

- **Email and password**, implemented as `USERNAME_FIELD = "email"`. The
  `username` field is removed.
- Email is unique and **case-insensitive**:
  - it is stored lowercase
  - a database unique constraint on `Lower(email)` blocks case variants
  - login looks up the normalised address
- Passwords are hashed by Django's default hasher (PBKDF2). Accounts created
  without a password get an unusable password until one is set.
- Tokens use SimpleJWT, unchanged.
- The **employee number** is a separate, non-secret identifier stored on
  Employee. It is never a credential.

### Extensibility

Phone-number or employee-number login can be added later as an additional
Django authentication backend, plus a SimpleJWT token serializer that
accepts the new identifier. The user model's identity, the token format and
the mobile token handling do not change.

## Consequences

- Role-based access control applies to Users. Business rules about who can
  be clocked in apply to Employees and their job assignments.
- Admin accounts may or may not have an Employee record.
- `createsuperuser` prompts for an email address.
- Changing the login method changed the initial `accounts` migration. This
  was possible only because nothing had been deployed. From now on, schema
  changes need new migrations.
