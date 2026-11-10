# ADR 009: Team notes are job-based shared notes

- Status: **Partly superseded** (2026-11-10, see the update below); services pending
- Date: 2026-11-06 (revised: worker note creation is a company setting)

## Context

LeadHands and workers need to share job-related information inside the app:
updates, work instructions, site reminders, material or equipment status,
and issues on site.

## Decision

`team_notes` is a **simple shared notice system attached to jobs**. It is not
a messaging platform.

### Data

- Every note belongs to **one job**.
- It records its **author** (User), **creation time** and **last
  modification time**, and who last modified it.
- Notes are **soft deleted**: deleted-at and deleted-by are recorded, and the
  note is hidden rather than removed.

### Permissions

| Action | LeadHand (on jobs they manage) | Worker (on jobs they are assigned to) | Admin |
| --- | --- | --- | --- |
| View | yes | yes | yes |
| Create | yes | only if `workers_can_create_notes` is on | yes |
| Edit / delete own notes | yes | yes, if they were allowed to create | yes |
| Edit / delete others' notes (moderation) | yes | no | yes |

- **`workers_can_create_notes`** is a **company-level setting**, editable by
  the Admin. It defaults to **`false`**. It lives in a database-backed
  company settings record rather than an environment variable, so it can be
  changed without a deployment.
- **Assumption:** if the setting is later turned off, workers keep the
  ability to edit and delete their own existing notes. "Subject to company
  permissions" can be tightened later by adding more boolean settings
  (additive columns).
- "Jobs they manage" means jobs where `Job.lead_hand` is the LeadHand's
  employee record.
- Implemented as `team_notes.JobNote` and `company.CompanySettings`. See
  `docs/development/data-model.md`.

### Out of scope

- real-time chat
- private or group messaging
- attachments
- push notifications
- edit history (only the last modification is kept)

## Consequences

- Access checks reuse job assignments. They live in `team_notes` services and
  selectors.
- Notes are fetched through normal paginated API requests, with no
  websockets.
- Whether notes can be read or created offline is not yet decided. The
  outbox (ADR 002) can support offline creation later without schema
  changes, provided notes carry a client-generated UUID.

## Update (2026-11-10): decisions that supersede parts of this ADR

These were confirmed with the role restructuring. They will be implemented in
the team-notes milestone; nothing has changed in code yet.

- **Everyone can create team notes.** The `workers_can_create_notes`
  company setting is no longer needed. The column stays until the notes
  milestone decides whether to drop it, which would need its own migration.
- **Authors cannot edit or delete their notes.** The soft-delete and
  "updated by" fields remain for moderation, which is still to be defined.
- **Notes get a category** showing urgency. This needs a new column.
- **Notes can be read and created offline.** This needs a client-generated
  UUID on notes (ADR 002 outbox).
- **Manager note permissions** are deferred (decision D21).
