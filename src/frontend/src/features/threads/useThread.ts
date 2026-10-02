/**
 * A thread's data layer: the query, the send, and the panel's own writes.
 *
 * Mirrors `useMessages.ts` on purpose — the same ordering rule (the wire is
 * newest first, the DOM oldest first, reversed once in `select` after copying),
 * the same remove-then-upsert reconciliation of a send, the same optimistic
 * reaction — over a cache that holds one thread's root and replies.
 */

import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'

import {
  addReaction,
  deleteMessage,
  editMessage,
  getThread,
  removeReaction,
  type Message,
} from '../../lib/api/messaging'
import type { Socket } from '../../lib/realtime/socket'
import {
  applyReaction,
  emitSend,
  messageKeys,
  optimistic,
  predictReaction,
  replaceMessage,
  setMessageReactions,
} from '../channels/useMessages'
import type { Reaction } from '../../lib/api/messaging'
import {
  applyThreadReaction,
  removeThreadMessage,
  setThreadReactions,
  threadKeys,
  upsertThreadMessage,
} from './threadCache'

/**
 * One thread: its root, apart, and its replies **oldest first**.
 *
 * The root is read off the first page — it rides on every page and
 * `threadCache` replaces it on all of them, so the first is as good as any.
 * A cached thread shows at once on reopen and is refetched in the background.
 */
export function useThread(
  accessToken: string,
  workspaceId: string | null,
  channelId: string | undefined,
  rootId: string,
) {
  return useInfiniteQuery({
    queryKey: threadKeys.detail(workspaceId, channelId, rootId),
    queryFn: ({ pageParam }) => getThread(accessToken, rootId, pageParam as string | undefined),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.nextCursor ?? undefined,
    // Copy, then reverse — `Array.reverse` mutates, and this is the cache.
    select: (data) => ({
      root: data.pages[0].root,
      replies: [...data.pages].reverse().flatMap((page) => [...page.items].reverse()),
    }),
  })
}

/**
 * Reply over the socket, rendering the reply before the server has it.
 *
 * Reconciled exactly as `useSendMessage` does — drop the `temp:` row, then upsert
 * by real id, so the ack and the room's echo can land in either order and leave
 * one row. **No optimistic count bump on the root**: the server's
 * `thread_summary_changed` is the only writer of a count, and a guess here would
 * be applied on top of it.
 */
export function useSendReply(
  socket: Socket | null,
  workspaceId: string | null,
  channelId: string,
  rootId: string,
  userId: string,
) {
  const queryClient = useQueryClient()
  const key = threadKeys.detail(workspaceId, channelId, rootId)

  return useMutation<Message, Error, string, { pendingId: string }>({
    mutationFn: (body) => emitSend(socket, { channelId, body, threadRootId: rootId }),
    onMutate: (body) => {
      const pending = optimistic(channelId, userId, body, rootId)
      upsertThreadMessage(queryClient, key, pending)
      return { pendingId: pending.id }
    },
    onSuccess: (message, _body, context) => {
      if (context) removeThreadMessage(queryClient, key, context.pendingId)
      upsertThreadMessage(queryClient, key, message)
    },
    onError: (_error, _body, context) => {
      if (context) removeThreadMessage(queryClient, key, context.pendingId)
    },
  })
}

/**
 * Edit, delete and react from inside the panel.
 *
 * Each writes the thread's entry. A result for the **root** also goes to
 * history, through `replaceMessage` and never `upsertMessage`: the panel works
 * on roots nobody loaded into history, and adding one would make it the newest
 * message in the channel (decision 28).
 */
export function useThreadActions(
  accessToken: string,
  workspaceId: string | null,
  channelId: string,
  rootId: string,
  userId: string,
) {
  const queryClient = useQueryClient()
  const key = threadKeys.detail(workspaceId, channelId, rootId)
  const historyKey = messageKeys.list(workspaceId, channelId)

  function settle(message: Message) {
    upsertThreadMessage(queryClient, key, message)
    if (message.threadRootId === null) replaceMessage(queryClient, historyKey, message)
  }

  const edit = useMutation<Message, Error, { messageId: string; body: string; version: number }>({
    mutationFn: ({ messageId, body, version }) =>
      editMessage(accessToken, messageId, { body, version }),
    onSuccess: settle,
  })

  const remove = useMutation<Message, Error, string>({
    mutationFn: (messageId) => deleteMessage(accessToken, messageId),
    onSuccess: settle,
  })

  const toggleReaction = useMutation<
    Message,
    Error,
    { message: Message; emoji: string },
    { messageId: string; previous: Reaction[]; isRoot: boolean }
  >({
    mutationFn: ({ message, emoji }) =>
      message.reactions.some((r) => r.emoji === emoji && r.reacted)
        ? removeReaction(accessToken, message.id, emoji)
        : addReaction(accessToken, message.id, emoji),
    onMutate: ({ message, emoji }) => {
      const event = predictReaction(message, emoji, channelId, userId)
      applyThreadReaction(queryClient, key, event, userId)
      const isRoot = message.threadRootId === null
      if (isRoot) applyReaction(queryClient, historyKey, event, userId)
      return { messageId: message.id, previous: message.reactions, isRoot }
    },
    onSuccess: settle,
    onError: (_error, _variables, context) => {
      if (!context) return
      setThreadReactions(queryClient, key, context.messageId, context.previous)
      if (context.isRoot) {
        setMessageReactions(queryClient, historyKey, context.messageId, context.previous)
      }
    },
  })

  return { edit, remove, toggleReaction }
}
