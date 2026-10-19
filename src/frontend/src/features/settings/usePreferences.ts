/**
 * The user's preferences (register D28), as server state.
 *
 * TanStack Query owns them (D24) — never the Zustand store — under one key,
 * `['preferences']`, that is neither per workspace nor per user: a preference
 * belongs to the person, so a workspace switch must not touch it. One
 * `QueryClient` never spans two users, since sign-in is always a full-page
 * navigation. Five minutes of staleness matches the directory, which is how
 * another tab sees a change "on its next refetch".
 *
 * Three hooks, three jobs:
 *
 * - `usePreferences` fetches. `ChatLayout` mounts it once so the clock is known
 *   before any time is drawn, and the Settings page mounts it `fresh`.
 * - `useUpdateClock` saves a choice.
 * - `useClock` only *reads*, so a message row, a thread summary and a search hit
 *   — rendered by the hundred — never send a request of their own.
 */

import {
  type QueryClient,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { useSyncExternalStore } from 'react'

import * as api from '../../lib/auth/api'
import type { Clock, Preferences } from '../../lib/auth/api'

export const preferencesKeys = {
  mine: () => ['preferences'] as const,
}

const STALE_MS = 5 * 60 * 1000

export function usePreferences(token: string | null, options: { fresh?: boolean } = {}) {
  return useQuery({
    queryKey: preferencesKeys.mine(),
    queryFn: () => api.preferences(token as string),
    enabled: token !== null,
    staleTime: STALE_MS,
    // `fresh`: a visit to the page asks the server again however fresh the cache
    // looks, so it never shows another tab's older answer as current.
    refetchOnMount: options.fresh ? 'always' : true,
    refetchOnWindowFocus: true,
    refetchOnReconnect: true,
  })
}

function withClock(previous: Preferences | undefined, clock: Clock | null): Preferences {
  const { clock: _dropped, ...rest } = previous ?? {}
  return clock === null ? rest : { ...rest, clock }
}

const cachedClock = (queryClient: QueryClient) =>
  queryClient.getQueryData<Preferences>(preferencesKeys.mine())?.clock

/**
 * Save the clock: `null` is "Automatic" and removes the key.
 *
 * The choice shows at once (`onMutate`) and the server has the last word:
 *
 * - `cancelQueries` first, so a refetch already in flight cannot land the old
 *   value over the choice.
 * - The PATCHes run one at a time (`scope`), in the order chosen. `onMutate`
 *   runs before that wait, so a later choice is already in the cache when an
 *   earlier one fails — which is why a failure puts its snapshot back **only if
 *   the cache still holds that choice**.
 * - The last mutation to settle invalidates, so the server's value wins over
 *   anything that started mid-save, and over a revert to a choice that was never
 *   saved (two failures in a row). `onSettled` runs while the settling mutation
 *   is still `pending`, so "only this one left" is a count of one. Cost: one GET
 *   after a burst of choices.
 */
export function useUpdateClock(token: string | null) {
  const queryClient = useQueryClient()
  const key = preferencesKeys.mine()

  return useMutation<
    Preferences,
    Error,
    Clock | null,
    { previous: Preferences | undefined; choice: Clock | null }
  >({
    mutationKey: key,
    scope: { id: 'preferences' },
    mutationFn: (clock) => api.updatePreferences(token as string, { clock }),
    onMutate: async (choice) => {
      await queryClient.cancelQueries({ queryKey: key })
      const previous = queryClient.getQueryData<Preferences>(key)
      queryClient.setQueryData<Preferences>(key, withClock(previous, choice))
      return { previous, choice }
    },
    onError: (_error, _choice, context) => {
      if (!context) return
      if ((cachedClock(queryClient) ?? null) !== context.choice) return
      queryClient.setQueryData<Preferences>(key, context.previous ?? {})
    },
    onSettled: () => {
      if (queryClient.isMutating({ mutationKey: key }) === 1) {
        void queryClient.invalidateQueries({ queryKey: key })
      }
    },
  })
}

/**
 * The chosen clock, or `undefined` for Automatic — read from the cache and
 * nothing else.
 *
 * Not a `useQuery`: an observer writes its options onto the one shared Query, so
 * a reader with no token to fetch with would leave `skipToken` or a dead
 * `queryFn` behind for the next invalidation to run. A cache subscription has no
 * options to leave (a departure from the plan's `skipToken`, recorded in the
 * green report).
 */
export function useClock(): Clock | undefined {
  const queryClient = useQueryClient()
  return useSyncExternalStore(
    (onChange) => queryClient.getQueryCache().subscribe(onChange),
    () => cachedClock(queryClient),
  )
}
