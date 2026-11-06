import { z } from 'zod';

import { env } from '@/lib/env';

import { NetworkError, ResponseValidationError, toApiError } from './errors';
import { tokenStorage, type TokenPair } from './token-storage';

type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

export type RequestOptions = {
  method?: HttpMethod;
  /** Serialised as JSON. */
  body?: unknown;
  /** Attach the bearer token and transparently refresh it once on 401. Default: true. */
  authenticated?: boolean;
  signal?: AbortSignal;
  timeoutMs?: number;
};

const DEFAULT_TIMEOUT_MS = 15_000;

const refreshResponseSchema = z.object({
  access: z.string(),
  // Present because the backend rotates refresh tokens.
  refresh: z.string().optional(),
});

let onSessionExpired: (() => void) | null = null;

/**
 * Registers a callback invoked when the refresh token is rejected.
 * The auth layer uses it to return to sign-in. It must never touch the
 * offline queue: unsynced punches survive an expired session.
 */
export function setSessionExpiredHandler(handler: (() => void) | null): void {
  onSessionExpired = handler;
}

async function send(
  path: string,
  { method = 'GET', body, signal, timeoutMs = DEFAULT_TIMEOUT_MS }: RequestOptions,
  accessToken?: string,
): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  const abortFromCaller = () => controller.abort();
  signal?.addEventListener('abort', abortFromCaller);

  const headers: Record<string, string> = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

  try {
    return await fetch(`${env.apiUrl}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new NetworkError(`Could not reach the server (${method} ${path})`, { cause: error });
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener('abort', abortFromCaller);
  }
}

// Concurrent 401s share a single refresh request.
let refreshInFlight: Promise<TokenPair | null> | null = null;

function refreshTokens(): Promise<TokenPair | null> {
  refreshInFlight ??= (async () => {
    const current = await tokenStorage.get();
    if (!current) return null;

    const response = await send('/auth/token/refresh/', {
      method: 'POST',
      body: { refresh: current.refresh },
    });
    if (response.status === 401) {
      await tokenStorage.clear();
      return null;
    }
    if (!response.ok) throw await toApiError(response);

    const data = refreshResponseSchema.parse(await response.json());
    const next = { access: data.access, refresh: data.refresh ?? current.refresh };
    await tokenStorage.set(next);
    return next;
  })().finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

/**
 * Performs a JSON request against the versioned API (`path` is relative to
 * EXPO_PUBLIC_API_URL, e.g. `/auth/me/`).
 *
 * Throws:
 * - `NetworkError` when the server could not be reached (retry later).
 * - `ApiError` for non-2xx responses, parsed from the backend error envelope.
 * - `ResponseValidationError` when `schema` is given and the body does not match.
 */
export async function apiRequest<T>(
  path: string,
  options: RequestOptions & { schema: z.ZodType<T> },
): Promise<T>;
export async function apiRequest(path: string, options?: RequestOptions): Promise<unknown>;
export async function apiRequest<T>(
  path: string,
  options: RequestOptions & { schema?: z.ZodType<T> } = {},
): Promise<T | unknown> {
  const { authenticated = true, schema } = options;

  const tokens = authenticated ? await tokenStorage.get() : null;
  let response = await send(path, options, tokens?.access);

  if (response.status === 401 && authenticated && tokens) {
    const refreshed = await refreshTokens();
    if (!refreshed) {
      onSessionExpired?.();
      throw await toApiError(response);
    }
    response = await send(path, options, refreshed.access);
  }

  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return undefined;

  const json: unknown = await response.json();
  if (!schema) return json;

  const parsed = schema.safeParse(json);
  if (!parsed.success) throw new ResponseValidationError(path, parsed.error);
  return parsed.data;
}
