import type { TabsScreenOptions } from 'expo-router/tabs';

import { colors } from './ui';

/**
 * Text-only tabs: the project has no icon dependency, and labels are clearer
 * for field crews than unlabelled icons.
 */
export const tabScreenOptions: TabsScreenOptions = {
  tabBarActiveTintColor: colors.primary,
  tabBarInactiveTintColor: colors.muted,
  tabBarIconStyle: { display: 'none' },
  tabBarLabelStyle: { fontSize: 14, fontWeight: '600' },
  tabBarItemStyle: { justifyContent: 'center' },
};
