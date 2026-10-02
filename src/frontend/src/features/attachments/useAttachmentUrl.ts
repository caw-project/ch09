/**
 * Download URLs for a message's files, and when to ask for a fresh one (issue 4
 * R11, decisions 29, 36).
 *
 * A URL lives 900 s (`OBJECT_STORE_PRESIGN_TTL_SECONDS`) and is **stale at 780 s**,
 * 120 s early. Staleness matters at exactly three moments, and nowhere else:
 *
 * 1. **A mount that finds it stale** refetches, and shows no `src` until the new
 *    URL lands — a stale one may have expired, and an `<img>` that 403s is worse
 *    than a moment's wait.
 * 2. **A click** (`freshAttachmentUrl`) uses the cached URL only if it is fresh.
 * 3. **An `<img>` that fails to load** refetches once (`refetch`).
 *
 * A *mounted* image keeps its URL: the browser has already loaded it, and
 * refetching under it would change `src` for nothing. So the query refetches on no
 * focus, no reconnect and no interval — TanStack's defaults would do the first two.
 * The literal 780 000 sits beside a presign TTL that is configurable; if that
 * setting ever moves, so must this.
 */

import { useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { getAttachmentUrl } from '../../lib/api/messaging'

export const URL_STALE_MS = 780_000

export const attachmentUrlKeys = {
  one: (workspaceId: string | null, messageId: string, assetId: string) =>
    ['attachment-url', workspaceId, messageId, assetId] as const,
}

const fetchUrl = (accessToken: string, messageId: string, assetId: string) =>
  getAttachmentUrl(accessToken, messageId, assetId).then((answer) => answer.url)

/**
 * The URL to put in an `<img>`.
 *
 * `url` is the cached URL while mounted, stale or not; it is `null` only while a
 * mount that found it stale (or found nothing) is fetching. `enabled: false` is for
 * a message that is still pending — a `temp:` id would 404 at the server.
 */
export function useAttachmentUrl(
  accessToken: string,
  workspaceId: string | null,
  messageId: string,
  assetId: string,
  enabled = true,
) {
  const queryClient = useQueryClient()
  const queryKey = attachmentUrlKeys.one(workspaceId, messageId, assetId)

  // Judged once, at mount: whatever was cached then is the stale URL not to show.
  const [stale] = useState(() => {
    const cached = queryClient.getQueryCache().find({ queryKey })
    return cached?.state.data !== undefined && cached.isStaleByTime(URL_STALE_MS)
      ? cached.state.dataUpdatedAt
      : null
  })

  const query = useQuery({
    queryKey,
    queryFn: () => fetchUrl(accessToken, messageId, assetId),
    enabled,
    staleTime: URL_STALE_MS,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })

  const showingTheStaleOne = stale !== null && query.dataUpdatedAt === stale
  return {
    url: showingTheStaleOne ? null : (query.data ?? null),
    isError: query.isError,
    refetch: () => query.refetch(),
  }
}

/**
 * A URL that is fresh *now*, for a click: the cached one when it is not stale,
 * otherwise a fetched one. Shares the hook's cache, so a click after a mount costs
 * no second request.
 */
export function freshAttachmentUrl(
  queryClient: QueryClient,
  accessToken: string,
  workspaceId: string | null,
  messageId: string,
  assetId: string,
): Promise<string> {
  return queryClient.fetchQuery({
    queryKey: attachmentUrlKeys.one(workspaceId, messageId, assetId),
    queryFn: () => fetchUrl(accessToken, messageId, assetId),
    staleTime: URL_STALE_MS,
  })
}
