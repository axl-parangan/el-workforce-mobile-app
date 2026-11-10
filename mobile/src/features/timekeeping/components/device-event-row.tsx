import { ListRow } from '@/components/ui';
import { formatDateTime } from '@/lib/company-time';
import type { PendingEvent } from '@/offline/queue/pending-events';

import { punchPayloadSchema } from '../punch-events';

/** One punch as recorded on this phone, with where it stands. */
export function describeDeviceEvent(
  event: PendingEvent,
  jobLabel: (jobId: number) => string = (jobId) => `job #${jobId}`,
): { title: string; subtitle: string } {
  const parsed = punchPayloadSchema.safeParse(event.payload);
  if (!parsed.success) return { title: 'Unreadable punch', subtitle: event.lastError ?? '' };
  const payload = parsed.data;
  const action = payload.action_type === 'clock_in' ? 'Clock in' : 'Clock out';
  const group = payload.employee_ids
    ? `Group ${action.toLowerCase()} (${payload.employee_ids.length})`
    : action;
  const title = `${group} · ${jobLabel(payload.job_id)} · ${formatDateTime(payload.captured_at)}`;

  let subtitle: string;
  switch (event.status) {
    case 'pending':
    case 'syncing':
      subtitle =
        event.attempts > 0
          ? `Waiting to be sent (tried ${event.attempts}×${event.lastError ? `: ${event.lastError}` : ''})`
          : 'Waiting to be sent';
      break;
    case 'synced': {
      const rejected = event.outcome?.results?.filter((r) => r.status === 'rejected') ?? [];
      subtitle = rejected.length
        ? `Sent · ${event.outcome?.message} Refused: ${rejected
            .map((r) => `${r.employee} (${r.message})`)
            .join('; ')}`
        : 'Sent and accepted';
      break;
    }
    case 'rejected':
      subtitle = `Refused: ${event.outcome?.message ?? event.lastError ?? 'unknown reason'}`;
      break;
  }
  return { title, subtitle };
}

export function DeviceEventRow({
  event,
  jobLabel,
}: {
  event: PendingEvent;
  jobLabel?: (jobId: number) => string;
}) {
  const { title, subtitle } = describeDeviceEvent(event, jobLabel);
  return <ListRow testID={`device-event-${event.id}`} title={title} subtitle={subtitle} />;
}
