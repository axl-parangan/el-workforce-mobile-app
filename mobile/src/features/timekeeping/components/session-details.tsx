import { Body, Card, Heading } from '@/components/ui';
import { formatDateTime } from '@/lib/company-time';

import type { Session } from '../schemas';
import { REVIEW_LABELS, sessionTimes } from './session-row';

const SOURCE_LABELS: Record<string, string> = {
  mobile_online: 'phone (online)',
  mobile_offline_sync: 'phone (sent later)',
  admin_entry: 'office entry',
};

type Punch = NonNullable<Session['clock_in']>;

function PunchDetails({ title, punch }: { title: string; punch: Punch | null }) {
  if (!punch) {
    return (
      <Card>
        <Heading>{title}</Heading>
        <Body muted>Not recorded yet.</Body>
      </Card>
    );
  }
  const flags = punch.location.flags.join(', ');
  return (
    <Card>
      <Heading>{title}</Heading>
      <Body>{formatDateTime(punch.at)}</Body>
      <Body muted>
        Recorded from {SOURCE_LABELS[punch.source] ?? punch.source}
        {punch.performed_by ? ` by ${punch.performed_by.email}` : ''}. Received{' '}
        {formatDateTime(punch.received_at)}.
      </Body>
      <Body muted>
        Location: {punch.location.status.replace(/_/g, ' ')}
        {punch.location.distance_meters ? ` · ${punch.location.distance_meters} m from site` : ''}
        {flags ? ` · ${flags.replace(/_/g, ' ')}` : ''}
      </Body>
    </Card>
  );
}

export function SessionDetails({ session }: { session: Session }) {
  return (
    <>
      <Card>
        <Heading>
          {session.job.job_number} · {session.job.name}
        </Heading>
        <Body>{session.employee.name}</Body>
        <Body muted>{sessionTimes(session)}</Body>
        <Body>
          {session.session_status === 'open' ? 'Open' : 'Closed'} ·{' '}
          {REVIEW_LABELS[session.review_status] ?? session.review_status}
        </Body>
        {session.exception_flags.length ? (
          <Body muted>Flags: {session.exception_flags.join(', ').replace(/_/g, ' ')}</Body>
        ) : null}
      </Card>
      <PunchDetails title="Clock in" punch={session.clock_in} />
      <PunchDetails title="Clock out" punch={session.clock_out} />
    </>
  );
}
