/**
 * The three time formatters the UI shares — a message's time of day, a thread's
 * last reply, a search hit's date and time — and the user's clock preference
 * (register D28) applied to all of them in one place.
 *
 * `clock` is the stored preference: `'12h'`, `'24h'`, or absent for "Automatic",
 * which leaves the browser's locale to decide as it always did. It overrides the
 * locale in both directions, through `hourCycle`: `h12` and `h23` rather than
 * `hour12`, whose meaning for a locale that has no 12-hour form varies.
 *
 * Pure, so the formatters are tested without a component, and `locale` is a
 * parameter so a test is not at the mercy of the machine's own.
 */

import type { Clock } from './auth/api'

function hourCycle(clock: Clock | undefined): { hourCycle?: 'h12' | 'h23' } {
  if (clock === '12h') return { hourCycle: 'h12' }
  if (clock === '24h') return { hourCycle: 'h23' }
  return {}
}

/** `15:05` or `3:05 PM` — the time of day alone. */
export function formatTime(
  iso: string,
  clock?: Clock,
  locale: string | string[] = [],
): string {
  return new Date(iso).toLocaleTimeString(locale, {
    hour: '2-digit',
    minute: '2-digit',
    ...hourCycle(clock),
  })
}

/** The medium date and the short time, for a row that must say which day. */
export function formatDateTime(
  iso: string,
  clock?: Clock,
  locale: string | string[] = [],
): string {
  return new Date(iso).toLocaleString(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
    ...hourCycle(clock),
  })
}
