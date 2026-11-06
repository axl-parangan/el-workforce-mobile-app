import { z } from 'zod';

/** Mirrors backend apps.accounts.models.Role. */
export const roleSchema = z.enum(['admin', 'leadhand', 'worker']);
export type Role = z.infer<typeof roleSchema>;

export const currentUserSchema = z.object({
  id: z.number().int(),
  email: z.email(),
  first_name: z.string(),
  last_name: z.string(),
  role: roleSchema,
});
export type CurrentUser = z.infer<typeof currentUserSchema>;

/** Login is email + password (ADR 007). */
export const credentialsSchema = z.object({
  email: z.email().transform((email) => email.trim().toLowerCase()),
  password: z.string().min(1),
});
export type Credentials = z.input<typeof credentialsSchema>;

export const tokenPairSchema = z.object({
  access: z.string(),
  refresh: z.string(),
});
