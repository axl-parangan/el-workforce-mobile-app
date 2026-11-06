import { QueryClient } from '@tanstack/react-query';

import { ApiError } from './errors';

/**
 * TanStack Query handles server *reads* and online-only mutations.
 * Offline-capable writes (punches) do not rely on mutation retries: they are
 * persisted to the SQLite outbox first and synced by src/offline/sync.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: (failureCount, error) => {
        // Client errors will not succeed on retry.
        if (error instanceof ApiError && error.status < 500) return false;
        return failureCount < 3;
      },
    },
    mutations: {
      retry: false,
    },
  },
});
