/** Keys used with expo-secure-store. SecureStore keys may only contain [A-Za-z0-9._-]. */
export const SECURE_STORAGE_KEYS = {
  accessToken: 'auth.accessToken',
  refreshToken: 'auth.refreshToken',
  currentUser: 'auth.currentUser',
} as const;
