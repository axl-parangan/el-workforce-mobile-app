import { z } from 'zod';

const envSchema = z.object({
  apiUrl: z.url().transform((url) => url.replace(/\/+$/, '')),
});

// EXPO_PUBLIC_* variables are inlined at build time, so they must be read with
// static property access (no destructuring or dynamic keys).
const result = envSchema.safeParse({
  apiUrl: process.env.EXPO_PUBLIC_API_URL,
});

if (!result.success) {
  throw new Error(
    `Invalid mobile environment configuration. Copy mobile/.env.example to mobile/.env.local.\n${z.prettifyError(result.error)}`,
  );
}

export const env = result.data;
