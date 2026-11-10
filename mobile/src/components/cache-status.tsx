import { formatDateTime } from '@/lib/company-time';
import { isStale, type Cached } from '@/offline/cached-fetch';

import { Banner } from './ui';

/**
 * Explains where cached data came from. Offline data is shown with its age;
 * data older than 24 hours gets a warning but never blocks an action (M6).
 */
export function CacheStatus({ cached }: { cached: Cached<unknown> | undefined }) {
  if (!cached) return null;
  if (isStale(cached.fetchedAt)) {
    return (
      <Banner tone="warning" testID="cache-stale">
        This information was last updated {formatDateTime(cached.fetchedAt)} and may be out of date.
        Connect to the internet to refresh it. You can still clock in; the server checks every
        punch.
      </Banner>
    );
  }
  if (cached.fromCache) {
    return (
      <Banner tone="info" testID="cache-offline">
        Offline. Showing information saved {formatDateTime(cached.fetchedAt)}.
      </Banner>
    );
  }
  return null;
}
