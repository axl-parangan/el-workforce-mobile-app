import type { ConfigContext, ExpoConfig } from 'expo/config';

/**
 * APP_VARIANT selects the build flavour so development, staging and production
 * builds can be installed side by side. It is read at build time only.
 * Runtime configuration (e.g. the API URL) uses EXPO_PUBLIC_* variables instead.
 */
type AppVariant = 'development' | 'staging' | 'production';

const variant = (process.env.APP_VARIANT ?? 'development') as AppVariant;

// TODO: replace with the company's reverse-DNS identifier before the first store build.
const BASE_IDENTIFIER = 'com.example.constructionworkforce';

const VARIANTS: Record<AppVariant, { name: string; identifier: string }> = {
  development: { name: 'Workforce (Dev)', identifier: `${BASE_IDENTIFIER}.dev` },
  staging: { name: 'Workforce (Staging)', identifier: `${BASE_IDENTIFIER}.staging` },
  production: { name: 'Workforce', identifier: BASE_IDENTIFIER },
};

const LOCATION_PERMISSION_MESSAGE =
  'Your location is recorded when you clock in or out so attendance can be verified against the job site.';

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: VARIANTS[variant].name,
  slug: 'construction-workforce',
  scheme: 'constructionworkforce',
  version: '0.1.0',
  orientation: 'portrait',
  icon: './assets/icon.png',
  userInterfaceStyle: 'light',
  ios: {
    supportsTablet: true,
    bundleIdentifier: VARIANTS[variant].identifier,
  },
  android: {
    package: VARIANTS[variant].identifier,
    adaptiveIcon: {
      backgroundColor: '#E6F4FE',
      foregroundImage: './assets/android-icon-foreground.png',
      backgroundImage: './assets/android-icon-background.png',
      monochromeImage: './assets/android-icon-monochrome.png',
    },
    predictiveBackGestureEnabled: false,
  },
  web: {
    favicon: './assets/favicon.png',
  },
  plugins: [
    'expo-router',
    'expo-status-bar',
    'expo-sqlite',
    'expo-secure-store',
    [
      'expo-location',
      {
        // Foreground ("when in use") location only. Background tracking is out of scope.
        locationWhenInUsePermission: LOCATION_PERMISSION_MESSAGE,
        locationAlwaysAndWhenInUsePermission: false,
        locationAlwaysPermission: false,
        motionUsagePermission: false,
      },
    ],
  ],
  experiments: {
    typedRoutes: true,
  },
  extra: {
    appVariant: variant,
  },
});
