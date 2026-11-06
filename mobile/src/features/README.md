# Features

Each folder owns one domain area of the app. Add files only when they are
needed:

```text
features/<feature>/
├── api.ts          # calls to apiRequest() for this feature
├── schemas.ts      # Zod schemas + inferred types for API payloads
├── hooks/          # TanStack Query hooks (useAssignedJobs, …), local-db hooks
├── components/     # UI used only by this feature
└── screens/        # full screens, re-exported by routes in app/
```

- Route files in `app/` stay thin and re-export screens from here.
- Shared UI goes in `src/components/`, and shared hooks in `src/hooks/`.
- Offline-capable writes go through `src/offline/` (outbox), not straight to
  `apiRequest`.
- Query keys are defined next to the hooks that use them, as
  `['<feature>', ...]`.
