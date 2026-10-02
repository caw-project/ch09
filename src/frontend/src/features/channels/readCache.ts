/**
 * The cache side of reading: what a local read writes, how it is held against a
 * fetch that began before the server moved the marker, and what a receipt from
 * the user's other tab does.
 *
 * The list and the detail are both written because both are on screen — the
 * sidebar badge reads the list, the divider reads the detail — and the server's
 * count is the only count: a local read changes the cached copy of it, nothing
 * else (D24).
 */

import { hashKey, type InfiniteData, type QueryClient } from '@tanstack/react-query'

import type { Channel, ChannelPage, MessagePage } from '../../lib/api/messaging'
import { isAtOrPast } from './readState'
import { channelKeys } from './useChannels'
import { isPending, messageKeys } from './useMessages'

/** The further of the list entry's and the detail entry's `lastReadId`. */
export function cachedLastReadId(
  qc: QueryClient,
  workspaceId: string | null,
  channelId: string,
): string | null {
  const inList = qc
    .getQueryData<ChannelPage>(channelKeys.list(workspaceId))
    ?.items.find((channel) => channel.id === channelId)?.lastReadId
  const inDetail = qc.getQueryData<Channel>(channelKeys.detail(workspaceId, channelId))?.lastReadId

  if (inList && inDetail) return inList > inDetail ? inList : inDetail
  return inList ?? inDetail ?? null
}

/** A channel with the marker moved to `messageId` and no unread count — never backwards. */
function read(channel: Channel, messageId: string): Channel {
  if (channel.lastReadId != null && channel.lastReadId >= messageId) return channel
  return { ...channel, lastReadId: messageId, unreadCount: 0 }
}

/**
 * Move the marker in the list and the detail entries that are cached. Other
 * channels and absent entries are untouched — an absent entry is not invented.
 */
export function writeLocalRead(
  qc: QueryClient,
  workspaceId: string | null,
  channelId: string,
  messageId: string,
): void {
  qc.setQueryData<ChannelPage>(channelKeys.list(workspaceId), (page) =>
    page && {
      ...page,
      items: page.items.map((channel) =>
        channel.id === channelId ? read(channel, messageId) : channel,
      ),
    },
  )
  qc.setQueryData<Channel>(
    channelKeys.detail(workspaceId, channelId),
    (channel) => channel && read(channel, messageId),
  )
}

/**
 * Keep a local read on top of any fetch that was already in flight.
 *
 * Such a fetch read the channel before the server committed the marker, so when
 * it lands it would bring the old count back. This re-applies the write after
 * each one; the returned `release` stops it (on the ack, an error ack, or the
 * timeout).
 */
export function holdLocalRead(
  qc: QueryClient,
  workspaceId: string | null,
  channelId: string,
  messageId: string,
): () => void {
  const hashes = new Set([
    hashKey(channelKeys.list(workspaceId)),
    hashKey(channelKeys.detail(workspaceId, channelId)),
  ])

  // A fetch result dispatches `success` without `manual` (query.ts:578); our own
  // setQueryData carries `manual: true` (queryClient.ts:206) — so this never loops.
  return qc.getQueryCache().subscribe((event) => {
    if (event.type !== 'updated' || event.action.type !== 'success' || event.action.manual) return
    if (!hashes.has(event.query.queryHash)) return
    writeLocalRead(qc, workspaceId, channelId, messageId)
  })
}

export interface ReadReceiptEvent {
  channelId: string
  userId: string
  messageId: string
}

/**
 * Apply a `read_receipt_updated` from the user's own room (another tab read).
 *
 * When the receipt covers everything cached it is written directly: the count
 * for that channel is zero. A receipt older than the newest cached message
 * leaves a count only the server knows, so the list is refetched. A receipt for
 * another user is ignored.
 */
export function applyReadReceipt(
  qc: QueryClient,
  workspaceId: string | null,
  event: ReadReceiptEvent,
  myUserId: string,
): void {
  if (event.userId !== myUserId) return

  const cached = qc.getQueryData<InfiniteData<MessagePage>>(
    messageKeys.list(workspaceId, event.channelId),
  )
  // Pages and items are newest-first. A pending send sorts after every real id
  // and would make every receipt look old while a send is in flight.
  const newest = cached?.pages.flatMap((page) => page.items).find((m) => !isPending(m))

  if (newest && isAtOrPast(event.messageId, newest.id)) {
    writeLocalRead(qc, workspaceId, event.channelId, event.messageId)
    return
  }
  void qc.invalidateQueries({ queryKey: channelKeys.list(workspaceId) })
}
