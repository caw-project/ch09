/**
 * The thread caches, and the writers every cache path shares.
 *
 * **One infinite query per root**, nested under the channel's history key
 * (`['messages', ws, channelId, 'thread', rootId]`, plan decision 15). Nesting is
 * deliberate: the join ack refetches history by its exact key (so it never
 * cancels an older page in flight) and then invalidates `threadKeys.all`, the
 * channel's threads, which refetches only one a panel is observing — so a
 * reconnect recovers an open thread, and a closed one is left to refetch on reopen.
 *
 * The cache is the raw `InfiniteData<ThreadPage>`. Each page carries the root and
 * its own slice of replies, newest first; the order is reversed once, in
 * `useThread`'s `select`, exactly as history does it.
 *
 * Every writer **no-ops on an absent entry**, for the rule `useMessages.ts`
 * gives: writing into an empty key would invent a one-reply thread with no
 * cursor and the real one would never load. A new reply goes to the head of the
 * newest page and only there, so the cursor a page holds is never reset by a
 * live event.
 */

import type { InfiniteData, QueryClient } from '@tanstack/react-query'

import type { Message, ThreadPage } from '../../lib/api/messaging'
import {
  mergeReaction,
  messageKeys,
  replaceMessage,
  type ReactionEvent,
} from '../channels/useMessages'
import type { Reaction } from '../../lib/api/messaging'

export const threadKeys = {
  all: (workspaceId: string | null, channelId: string | undefined) =>
    ['messages', workspaceId, channelId, 'thread'] as const,
  detail: (workspaceId: string | null, channelId: string | undefined, rootId: string) =>
    ['messages', workspaceId, channelId, 'thread', rootId] as const,
}

type InfiniteThread = InfiniteData<ThreadPage>

/** What a `thread_summary_changed` broadcast carries (doc 02 §3.2). */
export interface ThreadSummaryEvent {
  channelId: string
  rootId: string
  /** The authoritative count of live replies — never a delta. */
  replyCount: number
  lastReplyAt: string | null
}

/**
 * Write a message into a thread's cache: the root where it is the root, a reply
 * where it already sits, a new reply at the head of the newest page.
 *
 * Applied twice is the same as applied once — the sender's own ack and echo, and
 * a refetch landing after both, all arrive for one reply.
 */
export function upsertThreadMessage(
  queryClient: QueryClient,
  key: readonly unknown[],
  message: Message,
): void {
  queryClient.setQueryData<InfiniteThread>(key, (cached) => {
    if (!cached || cached.pages.length === 0) return cached

    if (cached.pages[0].root.id === message.id) {
      return { ...cached, pages: cached.pages.map((page) => ({ ...page, root: message })) }
    }

    const existing = cached.pages.some((page) => page.items.some((m) => m.id === message.id))
    if (existing) {
      return {
        ...cached,
        pages: cached.pages.map((page) => ({
          ...page,
          items: page.items.map((m) => (m.id === message.id ? message : m)),
        })),
      }
    }

    const [newest, ...rest] = cached.pages
    return { ...cached, pages: [{ ...newest, items: [message, ...newest.items] }, ...rest] }
  })
}

/** Drop a row that was never real: a reply's optimistic placeholder the server refused. */
export function removeThreadMessage(
  queryClient: QueryClient,
  key: readonly unknown[],
  messageId: string,
): void {
  queryClient.setQueryData<InfiniteThread>(key, (cached) => {
    if (!cached) return cached
    return {
      ...cached,
      pages: cached.pages.map((page) => ({
        ...page,
        items: page.items.filter((m) => m.id !== messageId),
      })),
    }
  })
}

/** Replace one message's reactions outright — the root on every page, or a reply. */
export function setThreadReactions(
  queryClient: QueryClient,
  key: readonly unknown[],
  messageId: string,
  reactions: Reaction[],
): void {
  mapThreadMessage(queryClient, key, messageId, (m) => ({ ...m, reactions }))
}

/**
 * Apply a reaction event to the one message it names, in the thread's cache.
 *
 * The same idempotent set `applyReaction` is for history, with the same rule:
 * `reacted` belongs to the actor and nobody else.
 */
export function applyThreadReaction(
  queryClient: QueryClient,
  key: readonly unknown[],
  event: ReactionEvent,
  myUserId: string,
): void {
  mapThreadMessage(queryClient, key, event.messageId, (m) => ({
    ...m,
    reactions: mergeReaction(m.reactions, event, myUserId),
  }))
}

function mapThreadMessage(
  queryClient: QueryClient,
  key: readonly unknown[],
  messageId: string,
  change: (message: Message) => Message,
): void {
  queryClient.setQueryData<InfiniteThread>(key, (cached) => {
    if (!cached) return cached
    return {
      ...cached,
      pages: cached.pages.map((page) => ({
        ...page,
        root: page.root.id === messageId ? change(page.root) : page.root,
        items: page.items.map((m) => (m.id === messageId ? change(m) : m)),
      })),
    }
  })
}

/**
 * Set a root's reply count and last reply time, in history and in its open thread.
 *
 * **A set, never an add**: the count is whatever the server counted after its
 * own commit, so the ack, the echo and a refetch all agree. History's write is
 * `replaceMessage` — a root nobody loaded into history is not added to it
 * (decision 28) — and the thread's is its own entry, which an absent thread
 * leaves absent.
 */
export function applyThreadSummary(
  queryClient: QueryClient,
  workspaceId: string | null,
  event: ThreadSummaryEvent,
): void {
  const { replyCount, lastReplyAt } = event
  const historyKey = messageKeys.list(workspaceId, event.channelId)

  const inHistory = queryClient
    .getQueryData<InfiniteData<{ items: Message[] }>>(historyKey)
    ?.pages.flatMap((page) => page.items)
    .find((m) => m.id === event.rootId)
  if (inHistory) replaceMessage(queryClient, historyKey, { ...inHistory, replyCount, lastReplyAt })

  mapThreadMessage(
    queryClient,
    threadKeys.detail(workspaceId, event.channelId, event.rootId),
    event.rootId,
    (m) => ({ ...m, replyCount, lastReplyAt }),
  )
}
