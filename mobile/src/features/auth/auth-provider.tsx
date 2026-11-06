import { useQueryClient } from '@tanstack/react-query';
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
 * Owns the session lifecycle. Deliberately never touches the offline outbox:
 * unsynced punches must survive sign-out and session expiry.
 * TODO: decide the UX when signing out with unsynced events (block, warn, or allow).
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [state, setState] = useState<AuthState>({ status: 'loading', user: null });

  const clearSession = useCallback(async () => {
    await Promise.all([tokenStorage.clear(), currentUserCache.clear()]);
    queryClient.clear();
    setState(SIGNED_OUT);
  }, [queryClient]);

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
      if (cachedUser && !cancelled) setState({ status: 'signedIn', user: cachedUser });

      try {
        const user = await fetchCurrentUser();
        await currentUserCache.set(user);
        if (!cancelled) setState({ status: 'signedIn', user });
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
    const tokens = await obtainTokens(credentials);
    await tokenStorage.set(tokens);
    const user = await fetchCurrentUser();
    await currentUserCache.set(user);
    setState({ status: 'signedIn', user });
  }, []);

  const signOut = useCallback(async () => {
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
