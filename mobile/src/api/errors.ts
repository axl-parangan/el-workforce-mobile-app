import { z } from 'zod';

/** Mirrors the backend error envelope (backend/common/exceptions.py). */
export const apiErrorEnvelopeSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    details: z.unknown().optional(),
  }),
});

/** The server responded with a non-2xx status. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

/**
 * The request never produced a response (offline, DNS failure, timeout).
 * Offline-capable operations treat this as "retry later", never as a rejection.
 */
export class NetworkError extends Error {
  constructor(message = 'Network request failed', options?: { cause?: unknown }) {
    super(message, options);
    this.name = 'NetworkError';
  }
}

/** The server responded successfully but the body did not match the expected schema. */
export class ResponseValidationError extends Error {
  readonly issues: z.core.$ZodIssue[];

  constructor(path: string, error: z.ZodError) {
    super(`Unexpected response shape from ${path}`);
    this.name = 'ResponseValidationError';
    this.issues = error.issues;
  }
}

export async function toApiError(response: Response): Promise<ApiError> {
  const body: unknown = await response.json().catch(() => null);
  const parsed = apiErrorEnvelopeSchema.safeParse(body);
  if (parsed.success) {
    const { code, message, details } = parsed.data.error;
    return new ApiError(response.status, code, message, details);
  }
  return new ApiError(response.status, 'unknown_error', `Request failed (${response.status})`);
}

/** An app-level problem whose message is written for the user. */
export class UserFacingError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'UserFacingError';
  }
}
