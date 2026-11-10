/**
 * Company timezone helpers (decision M11, backend ADR 008).
 *
 * Work dates and displayed times always use the company timezone, never the
 * phone's. The server stays authoritative; these helpers only drive UI hints
 * and client-side pre-checks.
 */
export const COMPANY_TIME_ZONE = 'America/Toronto';

const dateFormatter = new Intl.DateTimeFormat('en-CA', {
  timeZone: COMPANY_TIME_ZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

const timeFormatter = new Intl.DateTimeFormat('en-CA', {
  timeZone: COMPANY_TIME_ZONE,
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

const dateTimeFormatter = new Intl.DateTimeFormat('en-CA', {
  timeZone: COMPANY_TIME_ZONE,
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

function parts(formatter: Intl.DateTimeFormat, instant: Date): Record<string, string> {
  return Object.fromEntries(formatter.formatToParts(instant).map((p) => [p.type, p.value]));
}

/** `YYYY-MM-DD` of ``instant`` in the company timezone. */
export function workDateFor(instant: Date): string {
  const { year, month, day } = parts(dateFormatter, instant);
  return `${year}-${month}-${day}`;
}

/** `HH:MM` in the company timezone. */
export function formatTime(iso: string): string {
  const { hour, minute } = parts(timeFormatter, new Date(iso));
  return `${hour === '24' ? '00' : hour}:${minute}`;
}

/** e.g. "Mar 10, 08:00" in the company timezone. */
export function formatDateTime(iso: string): string {
  return dateTimeFormatter.format(new Date(iso));
}

/** An ISO 8601 instant with an explicit UTC offset, as the API requires. */
export function nowIso(): string {
  return new Date().toISOString();
}

export function formatDuration(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${String(minutes).padStart(2, '0')}m`;
}
