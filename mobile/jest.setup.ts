// Runtime configuration normally provided by mobile/.env.local.
process.env.EXPO_PUBLIC_API_URL = 'http://api.test/api/v1';

// The native SQLite module is unavailable under Jest. Database code is tested
// against Node's SQLite through src/test-utils/node-sqlite.ts instead.
jest.mock('expo-sqlite', () => ({
  useSQLiteContext: jest.fn(),
  SQLiteProvider: ({ children }: { children: unknown }) => children,
}));
