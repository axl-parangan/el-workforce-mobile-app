import { useLocalSearchParams } from 'expo-router';

import { describeError } from '@/api/error-messages';
import { CacheStatus } from '@/components/cache-status';
import { QueryState, Screen } from '@/components/ui';

import { SessionDetails } from '../components/session-details';
import { useMySession } from '../hooks';

export function SessionDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const query = useMySession(Number(id));
  return (
    <Screen refreshing={query.isRefetching} onRefresh={() => void query.refetch()}>
      <CacheStatus cached={query.data} />
      <QueryState
        isLoading={query.isPending}
        error={query.error ? describeError(query.error) : null}
      />
      {query.data ? <SessionDetails session={query.data.data} /> : null}
    </Screen>
  );
}
