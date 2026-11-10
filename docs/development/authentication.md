# Authentication and roles

## Mechanism

- **djangorestframework-simplejwt.** Chosen because the mobile app needs
  stateless bearer tokens that work without cookies, and because SimpleJWT
  is the de-facto standard for DRF with refresh rotation and blacklisting
  built in.
- **Access token:** short-lived, 15 min by default
  (`JWT_ACCESS_TOKEN_LIFETIME_MINUTES`).
- **Refresh token:** 30 days by default (`JWT_REFRESH_TOKEN_LIFETIME_DAYS`).
  It is **rotated** on every refresh and the old one is **blacklisted**
  (`token_blacklist` app). Reusing an old refresh token fails.
- **Mobile storage:** tokens live in `expo-secure-store` (Keychain on iOS,
  Keystore-backed storage on Android), never in AsyncStorage or SQLite.
- The mobile API client (`mobile/src/api/client.ts`) attaches the access
  token and refreshes it once on a 401. Concurrent requests share a single
  refresh. If the refresh is rejected, the session ends; the offline outbox
  is kept.

### Endpoints (`/api/v1/auth/`)

| Method | Path               | Purpose                                         |
| ------ | ------------------ | ----------------------------------------------- |
| POST   | `token/`           | Exchange `{"email", "password"}` for access + refresh |
| POST   | `token/refresh/`   | Rotate tokens                                   |
| POST   | `token/blacklist/` | Log out (invalidate a refresh token)            |
| GET    | `me/`              | Current user, including `role`                  |

## Roles

`accounts.User.role` holds exactly one of these values (ADR 011):

| Role | Stored value | Notes |
| --- | --- | --- |
| Admin | `admin` | `createsuperuser` sets it |
| Manager | `manager` | Company-wide operations |
| LeadHand | `leadhand` | Employee plus crew duties on the jobs they manage |
| Employee | `worker` (the default) | Display label "Employee"; the stored value is unchanged |

- A custom user model has been in place since the first migration.
- **Login is email and password** (ADR 007):
  - `USERNAME_FIELD = "email"`; there is no username field
  - emails are stored lowercase, with a case-insensitive unique constraint,
    so login is case-insensitive
  - accounts start with an unusable password and can't log in until it is
    set through the password-set link (sending it waits for email delivery)
- A **User is not an Employee.** Employees are defined in the `workforce`
  app and optionally link one-to-one to a User. Employees without accounts
  can still have attendance recorded for them.
  - **Every account has an Employee record**, including Admins, Managers and
    LeadHands. `apps/accounts/services/accounts.py` guarantees this.
- **The role is read from the database on every request.** It is not stored
  in the token, so role and active-status changes apply immediately.
- **The Django admin is superuser-only.** Neither the role nor `is_staff`
  grants access.
- **Future login methods** (phone, employee number) are added as additional
  `AUTHENTICATION_BACKENDS`, plus a SimpleJWT serializer that accepts the
  identifier. Tokens and the mobile client stay the same. The employee number
  is never a secret or a password.

## Authorisation

There are two layers, and both are centralised.

1. **Capabilities.** `apps/accounts/authorization.py` maps each role to
   named abilities. Code asks `has_capability(user, Capability.X)`, and
   views use `common.permissions.requires(Capability.X, ...)`. **Nothing
   else compares role names**; `tests/test_authorization_centralized.py`
   enforces this.
2. **Scope.** `apps/jobs/selectors/scope.py` decides which jobs and crews a
   user may act on:
   - Managers and Admins: company-wide.
   - LeadHands: jobs where they are the `lead_hand` **and** hold an active
     assignment, plus those jobs' crews.
   - Employees: their own records only.

   Out-of-scope ids return 404.

**Account management.** Who may create or manage which accounts is decided
by `manageable_roles` and enforced in `apps/accounts/services/accounts.py`:

- Managers manage LeadHand and Employee accounts.
- Admins also manage Managers.
- Only superusers handle Admin accounts.
- No one manages their own account through the service.
- The service never sets staff or superuser flags.
- Roles are fixed when an account is created.

Every endpoint defaults to `IsAuthenticated`. Public endpoints such as
health and token must opt out explicitly.

Mobile route guards (`Stack.Protected` in `mobile/app/_layout.tsx`) are for
UX only. The API is the security boundary.
