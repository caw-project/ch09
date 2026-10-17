/**
 * The two time formats the UI shows, and what the clock preference does to them.
 *
 * `null` is "automatic": nothing is added to the options, so the output is the
 * browser's own locale format, as it was before there was a preference. A choice
 * adds `hourCycle`, never `hour12` — `hour12: false` can render midnight as
 * `24:05` in some ICU locales, `h23` cannot — and `hourCycle` is allowed beside
 * `timeStyle`, which `hour12` is not in every engine.
 */

import type { Clock } from './auth/api'

const HOUR_CYCLE: Record<Clock, 'h12' | 'h23'> = { '12h': 'h12', '24h': 'h23' }

function cycle(clock: Clock | null): { hourCycle?: 'h12' | 'h23' } {
  return clock ? { hourCycle: HOUR_CYCLE[clock] } : {}
}

/** `13:05` or `1:05 PM`: for a message row and a thread summary. */
export function timeOfDay(iso: string, clock: Clock | null): string {
  return new Date(iso).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    ...cycle(clock),
  })
}

/** Date and time: for a search result, where the message may be old. */
export function dateAndTime(iso: string, clock: Clock | null): string {
  return new Date(iso).toLocaleString([], {
    dateStyle: 'medium',
    timeStyle: 'short',
    ...cycle(clock),
  })
}
