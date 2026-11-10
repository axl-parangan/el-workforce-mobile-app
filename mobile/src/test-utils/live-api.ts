/**
 * Helpers for tests against a running backend (skipped unless LIVE_API_URL is
 * set). jest-expo replaces global fetch with Expo's native-backed one, so
 * requests use Node's http module.
 */
export const API = process.env.LIVE_API_URL;
export const live = API ? describe : describe.skip;

export type Account = { userId: number; employeeId: number; token: string };

type NodeResponse = {
  statusCode?: number;
  on: (event: string, listener: (chunk?: unknown) => void) => void;
};
type NodeRequest = {
  on: (event: 'error', listener: (error: Error) => void) => void;
  write: (data: string) => void;
  end: () => void;
};
// eslint-disable-next-line @typescript-eslint/no-require-imports
const http = require('node:http') as {
  request: (
    url: string,
    options: { method: string; headers: Record<string, string | number> },
    callback: (res: NodeResponse) => void,
  ) => NodeRequest;
};

export function request(
  method: 'GET' | 'POST' | 'PUT' | 'PATCH',
  path: string,
  { token, body }: { token?: string; body?: unknown } = {},
): Promise<{ status: number; json: any }> {
  const payload = body === undefined ? undefined : JSON.stringify(body);
  return new Promise((resolve, reject) => {
    const req = http.request(
      `${API}${path}`,
      {
        method,
        headers: {
          'Content-Type': 'application/json',
          // Django's development server does not accept chunked request bodies.
          ...(payload ? { 'Content-Length': new TextEncoder().encode(payload).length } : {}),
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      },
      (res) => {
        let data = '';
        res.on('data', (chunk) => (data += String(chunk)));
        res.on('end', () =>
          resolve({ status: res.statusCode ?? 0, json: data ? JSON.parse(data) : null }),
        );
      },
    );
    req.on('error', reject);
    if (payload) req.write(payload);
    req.end();
  });
}

export async function signIn(email: string, password: string): Promise<Account> {
  const tokens = (await request('POST', '/auth/token/', { body: { email, password } })).json;
  const me = (await request('GET', '/auth/me/', { token: tokens.access })).json;
  if (!me.employee) throw new Error(`sign-in failed: ${JSON.stringify({ tokens, me })}`);
  return { userId: me.id, employeeId: me.employee.id, token: tokens.access };
}

export async function get(account: Account, path: string) {
  return (await request('GET', path, { token: account.token })).json;
}
