/**
 * Reads the clock preference once and offers it to everything below the shell
 * (issue gh-3 Req 7). Consumers use `useClock()` from `./useClock`.
 */

import type { ReactNode } from 'react'

import { ClockContext } from './useClock'
import { usePreferences } from './usePreferences'

interface Props {
  accessToken: string
  userId: string
  children: ReactNode
}

export function ClockProvider({ accessToken, userId, children }: Props) {
  const { data } = usePreferences(accessToken, userId)

  return <ClockContext.Provider value={data?.clock ?? null}>{children}</ClockContext.Provider>
}
