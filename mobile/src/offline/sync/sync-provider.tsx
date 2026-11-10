import { useQueryClient } from '@tanstack/react-query';
import * as Network from 'expo-network';
import { useSQLiteContext } from 'expo-sqlite';
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { AppState } from 'react-native';

import { useAuth } from '@/features/auth/auth-provider';

import type { SyncReport } from './sync-runner';
import { setSyncDatabase, syncService } from './sync-service';

type SyncContextValue = {
  /** Starts (or joins) a sync of the signed-in account's outbox. */
  requestSync: () => Promise<SyncReport>;
  syncing: boolean;
  lastReport: SyncReport | null;
};

const SyncContext = createContext<SyncContextValue | null>(null);

/** Query keys that depend on the outbox or on what the server has accepted. */
export const outboxQueryKey = ['outbox'] as const;

/**
 * Sync triggers: sign-in (or app launch while signed in), network regained,
 * app returning to the foreground, and after a punch is queued.
 */
export function SyncProvider({ children }: { children: ReactNode }) {
  const db = useSQLiteContext();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const userId = user?.id;
  const [syncing, setSyncing] = useState(false);
  const [lastReport, setLastReport] = useState<SyncReport | null>(null);

  useEffect(() => {
    setSyncDatabase(db);
    return () => setSyncDatabase(null);
  }, [db]);

  const requestSync = useCallback(async () => {
    setSyncing(true);
    try {
      return await syncService.request();
    } finally {
      setSyncing(syncService.isRunning());
    }
  }, []);

  useEffect(
    () =>
      syncService.subscribe((report) => {
        setLastReport(report);
        void queryClient.invalidateQueries({ queryKey: outboxQueryKey });
        if (report.synced + report.rejected > 0) {
          void queryClient.invalidateQueries({ queryKey: ['timekeeping'] });
        }
      }),
    [queryClient],
  );

  // Automatic triggers run in the background; only "Send now" shows a busy state.
  useEffect(() => {
    if (userId === undefined) return;
    void syncService.request();

    const network = Network.addNetworkStateListener((state) => {
      if (state.isConnected && state.isInternetReachable !== false) void syncService.request();
    });
    const appState = AppState.addEventListener('change', (status) => {
      if (status === 'active') void syncService.request();
    });
    return () => {
      network.remove();
      appState.remove();
    };
  }, [userId]);

  return (
    <SyncContext.Provider value={{ requestSync, syncing, lastReport }}>
      {children}
    </SyncContext.Provider>
  );
}

export function useSync(): SyncContextValue {
  const context = useContext(SyncContext);
  if (!context) throw new Error('useSync must be used within <SyncProvider>');
  return context;
}
