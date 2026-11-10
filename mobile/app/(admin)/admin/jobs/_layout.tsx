import { Stack } from 'expo-router';

export default function JobsLayout() {
  return (
    <Stack>
      <Stack.Screen name="index" options={{ title: 'Jobs' }} />
      <Stack.Screen name="[id]/index" options={{ title: 'Job' }} />
      <Stack.Screen name="new" options={{ title: 'New job' }} />
      <Stack.Screen name="[id]/edit" options={{ title: 'Edit job' }} />
      <Stack.Screen name="[id]/crew" options={{ title: 'Crew' }} />
      <Stack.Screen name="[id]/assignments" options={{ title: 'Assignments' }} />
      <Stack.Screen name="[id]/lead-hand" options={{ title: 'LeadHand' }} />
    </Stack>
  );
}
