/**
 * The signed-in user's preferences, held in TanStack Query under one key
 * (register D28, D24) — never in the store.
 *
 * Three readers with three jobs:
 *
 * - `usePreferences` fetches. `ChatLayout` and the Settings page run it; nothing
 *   else needs to.
 * - `useClock` is what a time formatter calls. It subscribes to the query cache
 *   with `useSyncExternalStore` and reads the entry, and so *cannot* fetch: a
 *   second `useQuery` per message row would be a second observer on the same
 *   key, able to change its options and start requests from a row.
 * - `useSetClock` changes the clock, optimistically.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useSyncExternalStore } from 'react'

import {
  type Clock,
  type Preferences,
  preferences,
  updatePreferences,
} from '../../lib/auth/api'

export const preferenceKeys = {
  mine: () => ['preferences'] as const,
}

export function usePreferences(accessToken: string, options?: { refetchOnMount?: 'always' }) {
  return useQuery({
    queryKey: preferenceKeys.mine(),
    // Scoped to the user by the token, not by the key: a preference follows the
    // person across workspaces, so a switch must not refetch.
    queryFn: () => preferences(accessToken),
    refetchOnMount: options?.refetchOnMount,
  })
}

/** The chosen clock, or `undefined` for Automatic (and before anything has loaded). */
export function useClock(): Clock | undefined {
  const queryClient = useQueryClient()
  return useSyncExternalStore(
    (onChange) => queryClient.getQueryCache().subscribe(onChange),
    () => queryClient.getQueryData<Preferences>(preferenceKeys.mine())?.clock,
  )
}

function withClock(current: Preferences | undefined, clock: Clock | null): Preferences {
  const next: Preferences = { ...current }
  if (clock) next.clock = clock
  else delete next.clock
  return next
}

/**
 * Choose a clock; `null` is Automatic.
 *
 * - The choice shows at once. `onMutate` first cancels a read already on its way,
 *   which would otherwise land with the old value and flip the screen back.
 * - Mutations share a scope, so their requests run in the order they were made
 *   while each `onMutate` still applies immediately; the server sees the choices
 *   in order and a slow earlier response cannot leave an older choice showing.
 * - Only the latest mutation's outcome counts. An earlier one failing behind a
 *   later choice is ignored; if the latest fails, the value from before the whole
 *   burst comes back.
 * - When the latest settles the entry is invalidated, so what the screen shows is
 *   checked against what the server committed.
 */
export function useSetClock(accessToken: string) {
  const queryClient = useQueryClient()
  // Per hook instance, read from callbacks that outlive the component.
  const burst = useRef({ latest: 0, before: undefined as Preferences | undefined, pending: 0 })

  return useMutation<Preferences, Error, Clock | null, { id: number }>({
    scope: { id: 'preferences' },
    mutationFn: (clock) => updatePreferences(accessToken, { clock }),
    onMutate: async (clock) => {
      const state = burst.current
      // Synchronously, before any await, so a second choice made in the same
      // tick numbers itself after this one and sees the burst already begun.
      const id = ++state.latest
      if (state.pending === 0) {
        state.before = queryClient.getQueryData<Preferences>(preferenceKeys.mine())
      }
      state.pending += 1

      await queryClient.cancelQueries({ queryKey: preferenceKeys.mine() })
      queryClient.setQueryData<Preferences>(preferenceKeys.mine(), (current) =>
        withClock(current, clock),
      )
      return { id }
    },
    onSuccess: (saved, _clock, context) => {
      if (context.id === burst.current.latest) {
        queryClient.setQueryData<Preferences>(preferenceKeys.mine(), saved)
      }
    },
    onError: (_error, _clock, context) => {
      const state = burst.current
      if (context?.id === state.latest) {
        queryClient.setQueryData<Preferences>(preferenceKeys.mine(), state.before ?? {})
      }
    },
    onSettled: (_saved, _error, _clock, context) => {
      burst.current.pending -= 1
      if (context?.id === burst.current.latest) {
        void queryClient.invalidateQueries({ queryKey: preferenceKeys.mine() })
      }
    },
  })
}
