# Workforce API

Base path: `/api/v1/`. Requires `Authorization: Bearer <access token>`.

| Method | Path | Admin | Manager | LeadHand | Employee |
| --- | --- | --- | --- | --- | --- |
| GET | `workforce/employees/` | ✓ | ✓ | 403 | 403 |

## List employees: `GET workforce/employees/`

A read-only list for staff pickers: assigning employees to jobs and
designating LeadHands (mobile decision M4). Guarded by the capability
`employees.view_any` (Managers and Admins).

**Pay data is never included.** The response holds identity and account
status only.

Filters:

- `search`: name or employee number, case-insensitive
- `role`: an account role (`admin`, `manager`, `leadhand`, `worker`), or
  `none` for employees without an app account
- `is_active`: `true` or `false`

Results are ordered by name and use the standard pagination.

```json
{"count": 1, "next": null, "previous": null, "results": [
  {"id": 7, "name": "Lee Lead", "employee_number": "E-7", "is_active": true,
   "has_account": true, "account": {"role": "leadhand", "is_active": true}}
]}
```

`account` is `null` for employees without an app account. An unknown `role`
filter value returns **400**.
