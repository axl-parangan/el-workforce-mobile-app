import { Tabs } from 'expo-router';

import { tabScreenOptions } from '@/components/navigation';

/** LeadHand home. Each tab with sub-pages owns a stack and its headers. */
export default function LeadhandTabsLayout() {
  return (
    <Tabs screenOptions={tabScreenOptions}>
      <Tabs.Screen name="index" options={{ title: 'Time', headerShown: true }} />
      <Tabs.Screen name="jobs" options={{ title: 'Jobs', headerShown: false }} />
      <Tabs.Screen name="attendance" options={{ title: 'Attendance', headerShown: false }} />
      <Tabs.Screen name="history" options={{ title: 'History', headerShown: false }} />
      <Tabs.Screen name="account" options={{ title: 'Account', headerShown: true }} />
    </Tabs>
  );
}
