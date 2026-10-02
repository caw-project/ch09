/**
 * Server state for message search, owned by TanStack Query (register D24).
 *
 * **The workspace id leads the key**, as it does everywhere (doc 06 §4): a token
 * is scoped to one workspace, so a switch reads a different entry and no old
 * results show.
 *
 * **A list on screen is a snapshot.** Focus and reconnect refetches are off, so a
 * result list never changes under the reader; the default `staleTime` of 0 means
 * a return to the page shows the cached list at once and refetches it — every
 * "Load more" page from fresh cursors, which is what R2's "refetches it" asks.
 *
 * Results are served newest first and shown in that order: unlike history there
 * is no reversal here.
 */

import { useInfiniteQuery } from '@tanstack/react-query'

import { searchMessages } from '../../lib/api/messaging'

export const searchKeys = {
  results: (workspaceId: string | null, q: string) => ['search', workspaceId, q] as const,
}

export function useSearch(accessToken: string, workspaceId: string | null, q: string) {
  return useInfiniteQuery({
    queryKey: searchKeys.results(workspaceId, q),
    queryFn: ({ pageParam }) => searchMessages(accessToken, q, pageParam),
    initialPageParam: undefined as string | undefined,
    // A short page with a cursor still has a next page: the server pages by
    // candidates, and hydration can drop some of them.
    getNextPageParam: (last) => last.nextCursor ?? undefined,
    enabled: q !== '',
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    select: (data) => data.pages.flatMap((page) => page.items),
  })
}
