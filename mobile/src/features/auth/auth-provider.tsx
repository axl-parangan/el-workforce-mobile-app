import { useQueryClient } from '@tanstack/react-query';
import { useSQLiteContext } from 'expo-sqlite';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

import { setSessionExpiredHandler } from '@/api/client';
import { tokenStorage } from '@/api/token-storage';
import { clearReferenceCache } from '@/offline/repositories/reference-cache';
import { setSessionOwner, syncService } from '@/offline/sync/sync-service';

import { blacklistRefreshToken, fetchCurrentUser, obtainTokens } from './api';
import { currentUserCache } from './current-user-cache';
import type { Credentials, CurrentUser } from './schemas';

type AuthState =
  | { status: 'loading'; user: null }
  | { status: 'signedOut'; user: null }
  | { status: 'signedIn'; user: CurrentUser };

type AuthContextValue = AuthState & {
  signIn: (credentials: Credentials) => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

const SIGNED_OUT: AuthState = { status: 'signedOut', user: null };

/**
 * Owns the session lifecycle and the sync owner.
 *
 * Pending punches belong to the account that recorded them. The sync owner is
 * set only while that account's tokens are stored, and every token change
 * first waits for an in-flight sync to finish, so events never travel with
 * another account's token. Sign-out and session expiry never touch the
 * outbox (M10: the Account screen warns before signing out with pending
 * punches); they only clear tokens, the cached profile and cached reference data.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const db = useSQLiteContext();
  const [state, setState] = useState<AuthState>({ status: 'loading', user: null });

  const clearSession = useCallback(async () => {
    setSessionOwner(null);
    await syncService.idle();
    await Promise.all([
      tokenStorage.clear(),
      currentUserCache.clear(),
      clearReferenceCache(db).catch(() => undefined),
    ]);
    queryClient.clear();
    setState(SIGNED_OUT);
  }, [db, queryClient]);

  useEffect(() => {
    setSessionExpiredHandler(() => void clearSession());
    return () => setSessionExpiredHandler(null);
  }, [clearSession]);

  // Restore the session at launch. Uses the cached profile so the app works offline.
  useEffect(() => {
    let cancelled = false;

    (async () => {
      const [tokens, cachedUser] = await Promise.all([tokenStorage.get(), currentUserCache.get()]);
      if (!tokens) {
        if (!cancelled) setState(SIGNED_OUT);
        return;
      }
      if (cachedUser && !cancelled) {
        // The cached profile and the tokens are stored and cleared together.
        setSessionOwner(cachedUser.id);
        setState({ status: 'signedIn', user: cachedUser });
      }

      try {
        const user = await fetchCurrentUser();
        await currentUserCache.set(user);
        if (!cancelled) {
          setSessionOwner(user.id);
          setState({ status: 'signedIn', user });
        }
      } catch {
        // With a cached profile, stay signed in (offline or a server hiccup).
        // A rejected refresh token is handled by the session-expired handler.
        if (!cachedUser && !cancelled) setState(SIGNED_OUT);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback<AuthContextValue['signIn']>(async (credentials) => {
    // No sync may run while the new account's tokens are being stored.
    setSessionOwner(null);
    await syncService.idle();
    const tokens = await obtainTokens(credentials);
    await tokenStorage.set(tokens);
    const user = await fetchCurrentUser();
    await currentUserCache.set(user);
    setSessionOwner(user.id);
    setState({ status: 'signedIn', user });
  }, []);

  const signOut = useCallback(async () => {
    setSessionOwner(null);
    await syncService.idle();
    const tokens = await tokenStorage.get();
    if (tokens) {
      // Best effort: the session is cleared locally even if the server is unreachable.
      await blacklistRefreshToken(tokens.refresh).catch(() => undefined);
    }
    await clearSession();
  }, [clearSession]);

  const value = useMemo(() => ({ ...state, signIn, signOut }), [state, signIn, signOut]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within <AuthProvider>');
  return context;
}
