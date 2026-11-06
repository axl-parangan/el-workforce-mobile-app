import { apiRequest } from '@/api/client';

import { credentialsSchema, currentUserSchema, tokenPairSchema, type Credentials } from './schemas';

export function obtainTokens(credentials: Credentials) {
  return apiRequest('/auth/token/', {
    method: 'POST',
    body: credentialsSchema.parse(credentials),
    authenticated: false,
    schema: tokenPairSchema,
  });
}

export function fetchCurrentUser() {
  return apiRequest('/auth/me/', { schema: currentUserSchema });
}

export async function blacklistRefreshToken(refresh: string): Promise<void> {
  await apiRequest('/auth/token/blacklist/', {
    method: 'POST',
    body: { refresh },
    authenticated: false,
  });
}
