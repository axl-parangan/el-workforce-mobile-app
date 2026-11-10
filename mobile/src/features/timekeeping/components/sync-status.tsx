import { Banner, Body, Button } from '@/components/ui';
import { useNetworkStatus } from '@/hooks/use-network-status';
import { useOutboxCounts } from '@/offline/hooks';
import { useSync } from '@/offline/sync/sync-provider';

function punches(n: number) {
  return n === 1 ? '1 punch' : `${n} punches`;
}

/**
 * Where the device's punches stand. Punches recorded by another account are
 * shown separately: they only sync when that account signs in again.
 */
export function SyncStatus({ showWhenClear = false }: { showWhenClear?: boolean }) {
  const counts = useOutboxCounts();
  const { requestSync, syncing, lastReport } = useSync();
  const { isOnline } = useNetworkStatus();
  const { unsynced = 0, recentlyRejected = 0, otherAccounts = 0 } = counts.data ?? {};

  return (
    <>
      {unsynced > 0 ? (
        <Banner tone="warning" testID="sync-pending">
          {punches(unsynced)} saved on this phone{' '}
          {isOnline === false
            ? 'will be sent automatically when you are back online.'
            : 'waiting to be sent.'}
        </Banner>
      ) : null}
      {unsynced > 0 ? (
        <Button
          label="Send now"
          variant="secondary"
          busy={syncing}
          testID="sync-now"
          onPress={() => void requestSync()}
        />
      ) : null}
      {unsynced > 0 && lastReport?.error ? <Body muted>{lastReport.error}</Body> : null}
      {otherAccounts > 0 ? (
        <Banner tone="info" testID="sync-other-accounts">
          {punches(otherAccounts)} recorded on this phone by another account{' '}
          {otherAccounts === 1 ? 'is' : 'are'} waiting for that account. They are sent only when the
          original account signs in again, never with yours, and they are not deleted.
        </Banner>
      ) : null}
      {recentlyRejected > 0 ? (
        <Banner tone="danger" testID="sync-rejected">
          {punches(recentlyRejected)} refused by the server in the last 24 hours. See History, On
          this phone.
        </Banner>
      ) : null}
      {showWhenClear && counts.isSuccess && unsynced + otherAccounts === 0 ? (
        <Banner tone="success" testID="sync-clear">
          All punches on this phone have been sent.
        </Banner>
      ) : null}
    </>
  );
}
