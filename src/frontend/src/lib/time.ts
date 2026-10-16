/**
 * Times of day as the user's clock preference says (register D28).
 *
 * With no choice ("Automatic") these are the browser's own locale format, exactly
 * as before there was a preference. A choice sets `hourCycle` — `h12` or `h23` —
 * rather than `hour12`: `hour12: false` can print `24:05` just after midnight in
 * some ICU builds, while `h23` never does.
 */

import type { Clock } from './auth/api'

const HOUR_CYCLE = { '12h': 'h12', '24h': 'h23' } as const

function cycle(clock: Clock | undefined): { hourCycle?: 'h12' | 'h23' } {
  return clock ? { hourCycle: HOUR_CYCLE[clock] } : {}
}

/** `13:05` or `01:05 PM`: the time of day alone, as a message row shows it. */
export function timeOfDay(iso: string, clock?: Clock, locale?: string): string {
  return new Date(iso).toLocaleTimeString(locale ?? [], {
    hour: '2-digit',
    minute: '2-digit',
    ...cycle(clock),
  })
}

/** Date and time, as a search result shows it. */
export function dateAndTime(iso: string, clock?: Clock, locale?: string): string {
  return new Date(iso).toLocaleString(locale ?? [], {
    dateStyle: 'medium',
    timeStyle: 'short',
    ...cycle(clock),
  })
}
