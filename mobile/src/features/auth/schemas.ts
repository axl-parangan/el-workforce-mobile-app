import { z } from 'zod';

/**
 * Mirrors backend apps.accounts.models.Role. `worker` is the stored value of the
 * role displayed as "Employee". A role this app version does not know (added
 * on the server later) becomes `unknown` instead of failing sign-in.
 */
export const KNOWN_ROLES = ['admin', 'manager', 'leadhand', 'worker'] as const;
export const roleSchema = z.enum([...KNOWN_ROLES, 'unknown']).catch('unknown');
export type Role = z.infer<typeof roleSchema>;

export const ROLE_LABELS: Record<Role, string> = {
  admin: 'Admin',
  manager: 'Manager',
  leadhand: 'LeadHand',
  worker: 'Employee',
  unknown: 'Unknown role',
};

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
