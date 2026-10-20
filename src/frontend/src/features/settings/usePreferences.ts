/**
 * The user's preferences (register D28), held where all server state is held:
 * TanStack Query, under one key, `['preferences', 'me']`. Per user and global,
 * not per workspace — a different user is a full sign-in navigation and so a fresh
 * `QueryClient`.
 *
 * `useClock` is how a time on screen learns the clock. It observes the key with
 * `skipToken`, so it never fetches: one screen-level fetcher (`ChatLayout`, the
 * settings page) fills the cache and every formatter re-renders from it with no
 * prop threaded through `MessageList`, `ThreadPanel` or `SearchPage`.
 *
 * ## Choosing a clock is optimistic and serial
 *
 * A choice shows at the click and saves at once, but the saves go out one at a
 * time in click order (a shared mutation `scope`), so the server's last write is
 * the user's last choice. `onMutate` runs at the click even for a mutation waiting
 * its turn; the PATCH waits. Bookkeeping per `QueryClient` — a `WeakMap`, so it
 * outlives an unmount:
 *
 * - `inFlight`: saves started and not settled;
 * - `latest`: the sequence number of the latest choice;
 * - `confirmed`: the map the server last confirmed (the cached map when nothing
 *   was in flight at the click, then each successful response).
 *
 * Only the latest choice's response writes the cache, and only the latest choice's
 * failure restores `confirmed`. Saves settle in order, so when the latest settles,
 * `confirmed` is the server's last saved map: A ok + B fails ends on A, A fails +
 * B ok ends on B with no error, both failing ends on where the user started.
 * `isMutating` is not used for this: it counts the mutation inside its own callbacks.
 */

import {
  skipToken,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query'

import { preferences, updatePreferences, type Clock, type Preferences } from '../../lib/auth/api'

export const preferenceKeys = {
  mine: ['preferences', 'me'] as const,
}

interface Saves {
  inFlight: number
  latest: number
  confirmed: Preferences
}

const saves = new WeakMap<QueryClient, Saves>()

function savesFor(queryClient: QueryClient): Saves {
  let found = saves.get(queryClient)
  if (!found) {
    found = { inFlight: 0, latest: 0, confirmed: {} }
    saves.set(queryClient, found)
  }
  return found
}

/** Read the preferences from the server; `refetchOnMount: 'always'` for a page that shows them. */
export function usePreferences(accessToken: string, options?: { refetchOnMount?: 'always' }) {
  return useQuery({
    queryKey: preferenceKeys.mine,
    queryFn: () => preferences(accessToken),
    ...options,
  })
}

/** The stored clock, or `null` for Automatic. Observes the cache and never fetches. */
export function useClock(): Clock | null {
  const { data } = useQuery({ queryKey: preferenceKeys.mine, queryFn: skipToken })
  return (data as Preferences | undefined)?.clock ?? null
}

interface Context {
  seq: number
}

export function useUpdatePreferences(accessToken: string) {
  const queryClient = useQueryClient()

  return useMutation<Preferences, Error, { clock: Clock | null }, Context>({
    scope: { id: 'preferences' },
    mutationFn: (patch) => updatePreferences(accessToken, patch),
    onMutate: async (patch) => {
      const book = savesFor(queryClient)
      // Synchronously, before any await: a second click must see this one counted.
      if (book.inFlight === 0) {
        book.confirmed = queryClient.getQueryData<Preferences>(preferenceKeys.mine) ?? {}
      }
      book.inFlight++
      const seq = ++book.latest

      // A refetch answered before this save would land the old value over the choice.
      await queryClient.cancelQueries({ queryKey: preferenceKeys.mine })
      queryClient.setQueryData<Preferences>(preferenceKeys.mine, (current) => {
        const { clock: _previous, ...rest } = current ?? {}
        return patch.clock === null ? rest : { ...rest, clock: patch.clock }
      })
      return { seq }
    },
    onSuccess: (data, _patch, context) => {
      const book = savesFor(queryClient)
      book.confirmed = data
      if (context?.seq === book.latest) queryClient.setQueryData(preferenceKeys.mine, data)
    },
    onError: (_error, _patch, context) => {
      const book = savesFor(queryClient)
      if (context?.seq === book.latest) {
        queryClient.setQueryData(preferenceKeys.mine, book.confirmed)
      }
    },
    onSettled: () => {
      const book = savesFor(queryClient)
      book.inFlight = Math.max(0, book.inFlight - 1)
    },
  })
}
