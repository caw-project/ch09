/**
 * The clock preference, for every place a time is drawn (issue gh-3 Req 7).
 *
 * `MessageItem`, `ThreadSummary` and `SearchResult` read it with `useClock()`
 * from the context `ClockProvider` fills. Context rather than props so a row deep
 * in a list needs no new argument, and a changed clock re-renders them from the
 * query cache with no refetch.
 *
 * `null` outside a provider, and before the preference has loaded: both mean
 * "automatic", the browser's own format, which is what every existing test of
 * those components renders. In its own file because a component file that also
 * exports a hook breaks fast refresh.
 */

import { createContext, useContext } from 'react'

import type { Clock } from '../../lib/auth/api'

export const ClockContext = createContext<Clock | null>(null)

export function useClock(): Clock | null {
  return useContext(ClockContext)
}
