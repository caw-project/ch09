/**
 * The two ways a time is drawn, and the clock preference that picks the hour cycle
 * (register D28; issue gh-3, Req 7).
 *
 * Every time on screen goes through one of these, so a stored `clock` reaches
 * messages, thread summaries and search results alike. With no clock stored
 * ("Automatic") the browser's own locale decides, as it always did.
 *
 * `hourCycle` and never `hour12`: `hour12: true` means `h11` in `ja-JP` (a midnight
 * that reads 0:07 PM), and `hour12: false` rendered "24:05" in older Chrome. ECMA-402
 * allows `hourCycle` beside `timeStyle`; it forbids only the component fields.
 */

import type { Clock } from './auth/api'

type ClockSetting = Clock | null | undefined

const HOUR_CYCLE: Record<Clock, 'h12' | 'h23'> = { '12h': 'h12', '24h': 'h23' }

function cycle(clock: ClockSetting): { hourCycle?: 'h12' | 'h23' } {
  return clock ? { hourCycle: HOUR_CYCLE[clock] } : {}
}

/** `15:07` or `3:07 PM`: the time of day alone, for a row that sits under a date. */
export function timeOfDay(iso: string, clock: ClockSetting): string {
  return new Date(iso).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    ...cycle(clock),
  })
}

/** The date and the time, for a row that stands alone (a search result). */
export function dateAndTime(iso: string, clock: ClockSetting): string {
  return new Date(iso).toLocaleString([], {
    dateStyle: 'medium',
    timeStyle: 'short',
    ...cycle(clock),
  })
}
