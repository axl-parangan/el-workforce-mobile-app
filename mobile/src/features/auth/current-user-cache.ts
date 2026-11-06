import * as SecureStore from 'expo-secure-store';

import { SECURE_STORAGE_KEYS } from '@/constants/storage-keys';

import { currentUserSchema, type CurrentUser } from './schemas';

/**
 * The last known profile, so a signed-in user can open the app and punch
 * while offline. The server remains the source of truth and is re-queried
 * whenever it is reachable.
 */
export const currentUserCache = {
  async get(): Promise<CurrentUser | null> {
    const raw = await SecureStore.getItemAsync(SECURE_STORAGE_KEYS.currentUser);
    if (!raw) return null;
    const parsed = currentUserSchema.safeParse(JSON.parse(raw));
    return parsed.success ? parsed.data : null;
  },

  async set(user: CurrentUser): Promise<void> {
    await SecureStore.setItemAsync(SECURE_STORAGE_KEYS.currentUser, JSON.stringify(user));
  },

  async clear(): Promise<void> {
    await SecureStore.deleteItemAsync(SECURE_STORAGE_KEYS.currentUser);
  },
};
