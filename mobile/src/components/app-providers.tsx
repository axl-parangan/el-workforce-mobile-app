import { QueryClientProvider } from '@tanstack/react-query';
import { SQLiteProvider } from 'expo-sqlite';
import { useEffect, type ReactNode } from 'react';

import { queryClient } from '@/api/query-client';
import { AuthProvider } from '@/features/auth/auth-provider';
import { registerReactQueryNativeListeners } from '@/lib/react-query-native';
import { DATABASE_NAME, initializeDatabase } from '@/offline/database/database';
import { SyncProvider } from '@/offline/sync/sync-provider';

export function AppProviders({ children }: { children: ReactNode }) {
  useEffect(() => registerReactQueryNativeListeners(), []);

  return (
    <QueryClientProvider client={queryClient}>
      <SQLiteProvider databaseName={DATABASE_NAME} onInit={initializeDatabase}>
        <AuthProvider>
          <SyncProvider>{children}</SyncProvider>
        </AuthProvider>
      </SQLiteProvider>
    </QueryClientProvider>
  );
}
