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

`accounts.User.role` is one of `admin`, `leadhand` or `worker`, with
`worker` as the default. `createsuperuser` sets `admin`.

- A custom user model has been in place since the first migration.
- **Login is email and password** (ADR 007):
  - `USERNAME_FIELD = "email"`; there is no username field
  - emails are stored lowercase, with a case-insensitive unique constraint,
    so login is case-insensitive
  - accounts can be created without a password; they can't log in until a
    password is set
- A **User is not an Employee.** Employees are defined in the `workforce`
  app and optionally link one-to-one to a User. Employees without accounts
  can still have attendance recorded by a LeadHand. LeadHands and
  self-clocking workers must have accounts.
- `role` is the **application** role. Django's `is_staff` and
  `is_superuser` control only Django admin access.
- **Future login methods** (phone, employee number) are added as additional
  `AUTHENTICATION_BACKENDS`, plus a SimpleJWT serializer that accepts the
  identifier. Tokens and the mobile client stay the same. The employee number
  is never a secret or a password.

## Authorisation approach (intended)

Two layers:

1. **Coarse, role-based checks** on views, using `common/permissions.py`:
   `IsAdmin`, `IsLeadHand`, `IsLeadHandOrAdmin` and `IsWorker`. These only
   answer whether the user holds a role.
2. **Object- and relationship-level rules** in the owning app's services and
   selectors. For example:
   - a worker sees only their own attendance
   - a LeadHand may clock only workers assigned to the same job
   - a LeadHand may edit only jobs they are allowed to manage

   These rules depend on assignment data, so they belong next to the domain
   logic and are covered by service tests. They are not handled by DRF
   object permissions.

Every endpoint defaults to `IsAuthenticated`. Public endpoints such as
health and token must opt out explicitly.

Mobile route guards (`Stack.Protected` in `mobile/app/_layout.tsx`) are for
UX only. The API is the security boundary.
