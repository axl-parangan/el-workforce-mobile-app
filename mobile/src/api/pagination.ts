import { z } from 'zod';

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
