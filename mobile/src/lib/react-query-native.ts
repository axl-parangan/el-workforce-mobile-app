import { focusManager, onlineManager } from '@tanstack/react-query';
import * as Network from 'expo-network';
import { AppState, Platform } from 'react-native';

/**
 * Connects TanStack Query to React Native: queries pause while offline and
 * refetch when the app returns to the foreground. Returns a cleanup function.
 */
export function registerReactQueryNativeListeners(): () => void {
  onlineManager.setEventListener((setOnline) => {
    const subscription = Network.addNetworkStateListener((state) => {
      setOnline(Boolean(state.isConnected));
    });
    return () => subscription.remove();
  });

  const appStateSubscription = AppState.addEventListener('change', (status) => {
    if (Platform.OS !== 'web') focusManager.setFocused(status === 'active');
  });

  return () => appStateSubscription.remove();
}
