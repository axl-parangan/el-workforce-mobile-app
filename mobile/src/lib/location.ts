import * as Location from 'expo-location';

/**
 * Location captured alongside a punch. A missing or poor fix never blocks a
 * punch: the server records it and flags the event for review (ADR 004).
 *
 * Coordinates are JS numbers on the device; the backend stores them as
 * DecimalField. Never do payroll or distance arithmetic for business
 * decisions on the device; the server is authoritative.
 */
export type PunchLocation =
  | {
      status: 'captured';
      latitude: number;
      longitude: number;
      /** Radius of 68% confidence, in metres. */
      accuracyMeters: number | null;
      /** When the OS obtained the fix (may be earlier than the punch). */
      capturedAt: string;
      /** Android reports mock-location providers; always false on iOS. */
      isMocked: boolean;
    }
  | {
      status: 'unavailable';
      reason: 'services_disabled' | 'permission_denied' | 'timeout' | 'error';
      detail?: string;
    };

const DEFAULT_TIMEOUT_MS = 15_000;

export async function capturePunchLocation(
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): Promise<PunchLocation> {
  try {
    if (!(await Location.hasServicesEnabledAsync())) {
      return { status: 'unavailable', reason: 'services_disabled' };
    }

    const permission = await Location.requestForegroundPermissionsAsync();
    if (permission.status !== Location.PermissionStatus.GRANTED) {
      return { status: 'unavailable', reason: 'permission_denied' };
    }

    let timer: ReturnType<typeof setTimeout> | undefined;
    const timeout = new Promise<null>((resolve) => {
      timer = setTimeout(() => resolve(null), timeoutMs);
    });
    const position = await Promise.race([
      Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High }),
      timeout,
    ]).finally(() => clearTimeout(timer));

    if (!position) return { status: 'unavailable', reason: 'timeout' };

    return {
      status: 'captured',
      latitude: position.coords.latitude,
      longitude: position.coords.longitude,
      accuracyMeters: position.coords.accuracy,
      capturedAt: new Date(position.timestamp).toISOString(),
      isMocked: position.mocked ?? false,
    };
  } catch (error) {
    return { status: 'unavailable', reason: 'error', detail: String(error) };
  }
}
