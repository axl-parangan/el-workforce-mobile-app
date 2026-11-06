import { useNetworkState } from 'expo-network';

export type NetworkStatus = {
  /** `undefined` until the first native reading arrives. */
  isOnline: boolean | undefined;
};

/**
 * Connectivity for UI hints (e.g. an "offline" banner).
 * Do not gate offline-capable actions on this: always write locally first.
 */
export function useNetworkStatus(): NetworkStatus {
  const { isConnected, isInternetReachable } = useNetworkState();
  if (isConnected === undefined) return { isOnline: undefined };
  return { isOnline: isConnected && isInternetReachable !== false };
}
