import * as SecureStore from 'expo-secure-store';

import { SECURE_STORAGE_KEYS } from '@/constants/storage-keys';

export type TokenPair = { access: string; refresh: string };

// SecureStore reads cross the native bridge, so keep a copy in memory.
// `undefined` means "not loaded yet"; `null` means "no session".
let cache: TokenPair | null | undefined;

export const tokenStorage = {
  async get(): Promise<TokenPair | null> {
    if (cache !== undefined) return cache;
    const [access, refresh] = await Promise.all([
      SecureStore.getItemAsync(SECURE_STORAGE_KEYS.accessToken),
      SecureStore.getItemAsync(SECURE_STORAGE_KEYS.refreshToken),
    ]);
    cache = access && refresh ? { access, refresh } : null;
    return cache;
  },

  async set(tokens: TokenPair): Promise<void> {
    await Promise.all([
      SecureStore.setItemAsync(SECURE_STORAGE_KEYS.accessToken, tokens.access),
      SecureStore.setItemAsync(SECURE_STORAGE_KEYS.refreshToken, tokens.refresh),
    ]);
    cache = tokens;
  },

  async clear(): Promise<void> {
    await Promise.all([
      SecureStore.deleteItemAsync(SECURE_STORAGE_KEYS.accessToken),
      SecureStore.deleteItemAsync(SECURE_STORAGE_KEYS.refreshToken),
    ]);
    cache = null;
  },
};
