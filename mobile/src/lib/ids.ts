import { randomUUID } from 'expo-crypto';

/**
 * Generates an ID on the device for records created offline. The server uses
 * it as an idempotency key, so retrying a sync can never create duplicates.
 */
export function newClientId(): string {
  return randomUUID();
}
