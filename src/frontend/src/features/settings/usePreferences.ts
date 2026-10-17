/**
 * The signed-in user's preferences, and the one mutation that changes the clock
 * (issue gh-3 Req 6 and 7; register D28).
 *
 * Preferences belong to the person, not to a workspace, so the key carries the
 * user and no workspace: a workspace switch keeps them (D24's workspace rule is
 * for workspace data). Server state, so TanStack Query owns it and nothing here
 * is copied into a store.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { type Clock, type Preferences, preferences, updatePreferences } from '../../lib/auth/api'

export const preferenceKeys = {
  mine: (userId: string) => ['user-preferences', userId] as const,
}

export function usePreferences(accessToken: string, userId: string) {
  return useQuery({
    queryKey: preferenceKeys.mine(userId),
    queryFn: () => preferences(accessToken),
  })
}

/** `previous` with the clock set, or removed for `null` (automatic). */
function withClock(previous: Preferences | undefined, clock: Clock | null): Preferences {
  const { clock: _replaced, ...rest } = previous ?? {}
  return clock ? { ...rest, clock } : rest
}

/**
 * Choose a clock: the screen changes at once and the server hears of it after.
 *
 * - `onMutate` writes the choice to the cache, so every time on screen
 *   re-renders from it with no refetch.
 * - `onError` puts the snapshot back, and `onSuccess` writes the server's answer,
 *   **only if the cache still holds this mutation's choice**. A late failure or
 *   answer for an older choice must not undo a newer one.
 * - `scope` makes a second choice's request wait for the first to settle, so the
 *   server stores the choices in the order they were made; without it two PATCHes
 *   can arrive the other way round and leave the tab and the server disagreeing.
 *   Only the request waits — `onMutate` still runs at once, so the optimistic
 *   render is unchanged.
 */
export function useSetClock(accessToken: string, userId: string) {
  const queryClient = useQueryClient()
  const key = preferenceKeys.mine(userId)

  const holdsChoice = (clock: Clock | null) =>
    (queryClient.getQueryData<Preferences>(key)?.clock ?? null) === clock

  return useMutation({
    scope: { id: 'user-preferences' },
    mutationFn: (clock: Clock | null) => updatePreferences(accessToken, { clock }),
    onMutate: async (clock) => {
      // A read still in flight would land after this and put the old value back.
      await queryClient.cancelQueries({ queryKey: key })
      const previous = queryClient.getQueryData<Preferences>(key)
      queryClient.setQueryData(key, withClock(previous, clock))
      return { previous }
    },
    onError: (_error, clock, context) => {
      if (context && holdsChoice(clock)) queryClient.setQueryData(key, context.previous)
    },
    onSuccess: (stored, clock) => {
      if (holdsChoice(clock)) queryClient.setQueryData(key, stored)
    },
  })
}
