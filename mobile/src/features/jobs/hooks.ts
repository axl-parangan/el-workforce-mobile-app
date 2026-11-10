import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';

import { CacheKeys } from '@/offline/repositories/reference-cache';
import { useCachedQuery } from '@/offline/use-cached-query';

import {
  getJob,
  listAllAssignedJobs,
  listAllMyAssignments,
  listJobAssignments,
  listJobs,
} from './api';
import { assignmentSchema, jobSchema } from './schemas';

export const jobKeys = {
  all: ['jobs'] as const,
  assigned: ['jobs', 'assigned'] as const,
  list: (params: object) => ['jobs', 'list', params] as const,
  detail: (id: number) => ['jobs', 'detail', id] as const,
  assignments: (jobId: number, status: string) => ['jobs', jobId, 'assignments', status] as const,
  myAssignments: ['assignments', 'mine'] as const,
};

/** The caller's active assignments: the offline source of jobs they can clock in to. */
export function useMyAssignments() {
  return useCachedQuery({
    cacheKey: CacheKeys.myAssignments,
    queryKey: jobKeys.myAssignments,
    fetcher: listAllMyAssignments,
    schema: z.array(assignmentSchema),
  });
}

/** Jobs the caller is actively assigned to (any role), cached offline. */
export function useAssignedJobs() {
  return useCachedQuery({
    cacheKey: CacheKeys.assignedJobs,
    queryKey: jobKeys.assigned,
    fetcher: listAllAssignedJobs,
    schema: z.array(jobSchema),
  });
}

export function useJob(id: number) {
  return useCachedQuery({
    cacheKey: CacheKeys.job(id),
    queryKey: jobKeys.detail(id),
    fetcher: () => getJob(id),
    schema: jobSchema,
    enabled: Number.isInteger(id),
  });
}

/** Company-wide job search (Managers and Admins). Online only. */
export function useJobList(params: { search?: string; status?: string }, enabled: boolean) {
  return useQuery({
    queryKey: jobKeys.list(params),
    queryFn: () => listJobs({ ...params, page_size: 100 }),
    enabled,
  });
}

export function useJobAssignments(jobId: number, status: 'active' | 'all', enabled = true) {
  return useQuery({
    queryKey: jobKeys.assignments(jobId, status),
    queryFn: () => listJobAssignments(jobId, status),
    enabled,
  });
}
