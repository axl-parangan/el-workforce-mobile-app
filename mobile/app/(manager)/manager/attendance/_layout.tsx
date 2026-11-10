import { Stack } from 'expo-router';

export default function AttendanceLayout() {
  return (
    <Stack>
      <Stack.Screen name="index" options={{ title: 'Attendance' }} />
      <Stack.Screen name="[id]" options={{ title: 'Session' }} />
    </Stack>
  );
}
