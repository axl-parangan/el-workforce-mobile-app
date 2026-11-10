# API conventions

Base path: `/api/v1/`. The version is part of the URL and uses DRF
`NamespaceVersioning`. URL names are reversed as `v1:<app>:<name>`.

## Authentication

Send `Authorization: Bearer <access token>`. All endpoints require
authentication unless documented otherwise. See
[authentication](../development/authentication.md).

## Errors

Every error response uses the same envelope:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Invalid input.",
    "details": { "field": ["This field is required."] }
  }
}
```

| Status | Typical `code`                                   |
| ------ | ------------------------------------------------ |
| 400    | `validation_error`, or a domain-specific code from a service. Bad GPS data is never a 400: it is flagged on the punch. |
| 401    | `not_authenticated`, `token_not_valid`, `no_active_account`  |
| 403    | `permission_denied`                              |
| 404    | `not_found`                                      |
| 500    | `server_error`                                   |

Clients should branch on `code`, not `message`.

## Pagination

List endpoints return:

```json
{ "count": 120, "next": "…?page=3", "previous": "…?page=1", "results": [] }
```

Use `?page=` and `?page_size=` (maximum 100). High-volume append-only
collections may use cursor pagination instead. Their endpoint documentation
will say so.

## Data formats

- Datetimes are ISO 8601 with a timezone, for example
  `2026-11-06T07:30:00Z`. The server stores UTC. Work dates are derived in
  the company timezone (`America/Toronto` by default), never the device's.
- Decimals (money, hours, coordinates) are sent as **strings**, for example
  `"18.50"`.

## Endpoints

| Method | Path                         | Auth | Notes                       |
| ------ | ---------------------------- | ---- | --------------------------- |
| GET    | `/api/v1/health/`            | No   | Liveness, plus a database check |
| POST   | `/api/v1/auth/token/`        | No   | `{"email", "password"}` → token pair. Email is case-insensitive. |
| POST   | `/api/v1/auth/token/refresh/`| No   | Rotate tokens               |
| POST   | `/api/v1/auth/token/blacklist/` | No | Log out                    |
| GET    | `/api/v1/auth/me/`           | Yes  | Current user, role, `capabilities` and linked `employee` |

Domain endpoints:

- **Timekeeping**: clock-in and clock-out, group punches, offline sync,
  status, history, crew, and staff review. See
  [timekeeping.md](timekeeping.md).
- **Jobs and assignments**: jobs, LeadHand designation, bulk assignment, and
  the assignment lifecycle. See [jobs.md](jobs.md).
- **Workforce**: the read-only employee list for Managers and Admins. See
  [workforce.md](workforce.md).
- Payroll and team notes endpoints are not implemented yet.

A database constraint violation that reaches the API returns **409**
`conflict` instead of a 500.
