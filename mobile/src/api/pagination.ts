import { z } from 'zod';

import { apiRequest } from './client';

/** Schema for the backend's StandardPagination response shape. */
export function paginatedSchema<T extends z.ZodType>(item: T) {
  return z.object({
    count: z.number().int().nonnegative(),
    next: z.string().nullable(),
    previous: z.string().nullable(),
    results: z.array(item),
  });
}

export type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

export function withQuery(path: string, params: Record<string, unknown> = {}): string {
  const query = Object.entries(params)
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
    .join('&');
  return query ? `${path}?${query}` : path;
}

/**
 * Every page of a list endpoint (page size 100, the API maximum). Used for the
 * small per-user lists the app caches offline.
 */
export async function fetchAllPages<T extends z.ZodType>(
  path: string,
  item: T,
  params: Record<string, unknown> = {},
  maxPages = 20,
): Promise<z.infer<T>[]> {
  const schema = paginatedSchema(item);
  const results: z.infer<T>[] = [];
  for (let page = 1; page <= maxPages; page += 1) {
    const body = await apiRequest(withQuery(path, { ...params, page, page_size: 100 }), {
      schema,
    });
    results.push(...(body.results as z.infer<T>[]));
    if (!body.next) break;
  }
  return results;
}
