import { formatDuration, formatTime, workDateFor } from './company-time';

describe('company time (America/Toronto, M11)', () => {
  it('derives the work date in the company timezone, not UTC', () => {
    // 02:30 UTC on the 11th is 21:30 EST on the 10th in Toronto.
    expect(workDateFor(new Date('2026-11-11T02:30:00Z'))).toBe('2026-11-10');
    expect(workDateFor(new Date('2026-11-11T05:30:00Z'))).toBe('2026-11-11');
  });

  it('handles daylight saving time', () => {
    // Toronto is UTC-4 in July.
    expect(workDateFor(new Date('2026-07-01T03:30:00Z'))).toBe('2026-06-30');
    expect(formatTime('2026-07-01T12:00:00Z')).toBe('08:00');
  });

  it('formats times as HH:MM in the company timezone', () => {
    expect(formatTime('2026-03-10T08:05:00-04:00')).toBe('08:05');
    expect(formatTime('2026-11-10T05:00:00Z')).toBe('00:00');
  });

  it('formats durations', () => {
    expect(formatDuration(0)).toBe('0h 00m');
    expect(formatDuration(9 * 3600 + 5 * 60)).toBe('9h 05m');
  });
});
