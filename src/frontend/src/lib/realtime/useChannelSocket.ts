/**
 * One socket for the whole chat shell, and the inbound events it carries.
 *
 * Mounted in `ChatLayout`, not in `ChannelView` — one long-lived connection
 * (doc 06 §5.1), not one that is torn down and rebuilt on every navigation.
 *
 * Four rules run through this file, and each of them is a bug that would
 * otherwise be found in production rather than in a test.
 *
 * **The access token is the connection's identity, so it is the effect's
 * dependency.** It changes on renewal *and* on a workspace switch, so one key
 * satisfies both Conventions §5.4 (a connection keeps the workspace of the
 * token that opened it) and doc 06 §4 (a switch drops the socket) without a
 * second lifecycle hook that somebody has to remember.
 *
 * **A refused handshake stops; a dropped transport retries.** Socket.IO's
 * built-in backoff is right for a network blip and wrong for a token the server
 * has already rejected — that will be rejected identically forever, and the
 * retry loop hides the real problem behind a spinner. `connect_error` therefore
 * disconnects, and recovery comes from this effect re-running with a fresh
 * token, which is the only thing that could change the answer.
 *
 * **Every join refetches — after the server acknowledges it.** python-socketio
 * has no connection-state recovery: re-entering a room replays nothing, so
 * everything broadcast while the client was away is simply gone. The refetch is
 * the recovery mechanism and the join only resumes the live stream from that
 * point. The order matters: the server enters the room only once it has checked
 * the channel is visible, so a refetch sent alongside the join can finish first
 * and a message sent in between reaches neither. Refetching on the ack leaves
 * no gap, and the same ack is what `joinedChannelId` reports. The refetch never
 * cancels an older-page fetch in flight — `refetchHistory` waits for it and then
 * refetches — or a reader paging back, or a jump to a search result, would lose
 * the page it was waiting for.
 *
 * **An event for a channel with no cached history is dropped.**
 * `setQueryData` on an empty key stores whatever the updater returns, so a
 * handler that built a fresh page there would invent a complete one-message
 * history with no cursor — and the real history would never load. The helpers
 * in `useMessages.ts` no-op on an absent entry; handlers key on **the event's**
 * `channelId`, so a background channel that *is* cached still updates.
 *
 * **An event that lands during a history fetch is applied again when the fetch
 * does.** A fetch that resolves replaces the cached pages with what it read, and
 * it read the channel before the event's change existed — so without this, a
 * message arriving while the history loads or refetches vanishes until a reload.
 * The first load is the same case: the event is dropped against the empty entry,
 * then applied once the history is there to hold it.
 *
 * **Message events are routed by `threadRootId`.** A reply belongs to its
 * thread's cache (`threadCache.ts`) and never to history; a top-level event goes
 * to history and to the thread that message opens. The join-ack invalidations
 * below use the channel's key as a prefix, which also reaches an open thread's
 * nested key — so a reconnect refetches the panel with no code of its own.
 *
 * **Read state rides on the same connection.** Every connect refetches the
 * channel list (counts changed while nobody listened), and the user's own
 * `read_receipt_updated` — another tab read — clears the count here, written
 * directly when it covers everything cached and refetched when it does not.
 */

import { hashKey, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'

import type { Message } from '../api/messaging'
import { applyReadReceipt, type ReadReceiptEvent } from '../../features/channels/readCache'
import { channelKeys } from '../../features/channels/useChannels'
import {
  applyReaction,
  messageKeys,
  replaceMessage,
  refetchHistory,
  upsertMessage,
  type ReactionEvent,
} from '../../features/channels/useMessages'
import {
  applyThreadReaction,
  applyThreadSummary,
  threadKeys,
  upsertThreadMessage,
  type ThreadSummaryEvent,
} from '../../features/threads/threadCache'
import { useChatStore } from '../../stores/chat'
import { connect, type Socket } from './socket'

interface JoinAck {
  ok: boolean
}

/** Ask to join a channel's room, and call `onJoined` only if the server did. */
function joinChannel(socket: Socket, channelId: string, onJoined: () => void): void {
  socket.emit('join_channel', channelId, (ack?: JoinAck) => {
    if (ack?.ok) onJoined()
  })
}

/**
 * Apply a message event once more, when a history fetch already in flight lands.
 *
 * That fetch read the channel before this event's change existed, and a fetch
 * that resolves *replaces* the cached pages — so a message written into the
 * cache while it was in flight is overwritten, and one that arrived during a
 * first load (with nothing cached to write into) was never kept at all. Either
 * way it is gone until a reload. Re-applying is safe: `upsertMessage` replaces
 * by id, and the event is never older than what that fetch returned.
 */
function reapplyAfterFetch(queryClient: QueryClient, key: readonly unknown[], apply: () => void) {
  const hash = hashKey(key)
  const unsubscribe = queryClient.getQueryCache().subscribe((event) => {
    if (event.type !== 'updated' || event.query.queryHash !== hash) return
    if (event.query.state.fetchStatus !== 'idle') return

    unsubscribe()
    if (event.query.state.status === 'success') apply()
  })
}

export function useChannelSocket(
  accessToken: string,
  workspaceId: string | null,
  channelId: string | null,
  userId: string,
): Socket | null {
  const queryClient = useQueryClient()
  const setConnectionStatus = useChatStore((state) => state.setConnectionStatus)
  const setJoinedChannel = useChatStore((state) => state.setJoinedChannel)
  const [socket, setSocket] = useState<Socket | null>(null)

  // The handlers below are registered once, on mount, and would otherwise close
  // over whichever channel was open at that moment. A ref is what lets the
  // `connect` handler re-join the channel the user is looking at *now*.
  const activeChannel = useRef(channelId)
  activeChannel.current = channelId

  useEffect(() => {
    setConnectionStatus('connecting')
    const live = connect(accessToken)
    setSocket(live)

    function onConnect() {
      setConnectionStatus('connected')
      // Counts change while no one is listening; a connection is the moment to
      // ask again, whichever channel is open.
      void queryClient.invalidateQueries({ queryKey: channelKeys.list(workspaceId) })

      const current = activeChannel.current
      if (!current) return

      joinChannel(live, current, () => {
        if (activeChannel.current === current) setJoinedChannel(current)
        // Whatever was said while this client was away went to a room it was
        // not in. Re-joining does not replay it; refetching does.
        refetchHistory(queryClient, messageKeys.list(workspaceId, current))
        void queryClient.invalidateQueries({ queryKey: threadKeys.all(workspaceId, current) })
      })
    }

    function onDisconnect() {
      setConnectionStatus('disconnected')
      setJoinedChannel(null)
    }

    function onConnectError() {
      // The server said no. Retrying says the same thing forever.
      live.disconnect()
      setConnectionStatus('disconnected')
      setJoinedChannel(null)
    }

    /** Apply now, and again for each of these caches that is mid-fetch. */
    function applyAndReapply(keys: (readonly unknown[])[], apply: () => void) {
      apply()
      for (const key of keys) {
        if (queryClient.isFetching({ queryKey: key, exact: true }) > 0) {
          reapplyAfterFetch(queryClient, key, apply)
        }
      }
    }

    /**
     * Route a message event by `threadRootId` (R3, decision 28).
     *
     * A reply goes to its thread's cache and **never** into history. A top-level
     * message goes to history — a new row only from `message_received` (`adds`),
     * while an edit or delete merely replaces a row already there — and also
     * replaces the root in the thread it opens, which is absent unless a panel
     * has it cached.
     */
    function routeMessage(message: Message, adds: boolean) {
      if (message.threadRootId !== null) {
        const key = threadKeys.detail(workspaceId, message.channelId, message.threadRootId)
        applyAndReapply([key], () => upsertThreadMessage(queryClient, key, message))
        return
      }

      const key = messageKeys.list(workspaceId, message.channelId)
      const ownThread = threadKeys.detail(workspaceId, message.channelId, message.id)
      applyAndReapply([key, ownThread], () => {
        if (adds) upsertMessage(queryClient, key, message)
        else replaceMessage(queryClient, key, message)
        upsertThreadMessage(queryClient, ownThread, message)
      })
    }

    function onReaction(event: ReactionEvent) {
      const key = messageKeys.list(workspaceId, event.channelId)
      if (event.threadRootId) {
        const thread = threadKeys.detail(workspaceId, event.channelId, event.threadRootId)
        applyAndReapply([thread], () => applyThreadReaction(queryClient, thread, event, userId))
        return
      }

      // A reaction on a root: its history row, and the panel's copy of it.
      const ownThread = threadKeys.detail(workspaceId, event.channelId, event.messageId)
      applyAndReapply([key, ownThread], () => {
        applyReaction(queryClient, key, event, userId)
        applyThreadReaction(queryClient, ownThread, event, userId)
      })
    }

    live.on('connect', onConnect)
    live.on('disconnect', onDisconnect)
    live.on('connect_error', onConnectError)
    // All three events carry the full `Message`, including the delete — a
    // client holding only an id could not render the tombstone.
    live.on('message_received', (message: Message) => routeMessage(message, true))
    live.on('message_edited', (message: Message) => routeMessage(message, false))
    live.on('message_deleted', (message: Message) => routeMessage(message, false))
    // A root's authoritative reply count: set, never added to.
    // Re-applied after a fetch in flight like every other live event: that fetch
    // may have read the root before the reply committed.
    live.on('thread_summary_changed', (event: ThreadSummaryEvent) =>
      applyAndReapply(
        [
          messageKeys.list(workspaceId, event.channelId),
          threadKeys.detail(workspaceId, event.channelId, event.rootId),
        ],
        () => applyThreadSummary(queryClient, workspaceId, event),
      ),
    )
    // Its own handler, because it carries facts rather than a `Message`: the
    // DTO's `reacted` is computed for one caller and cannot be broadcast.
    live.on('reaction_changed', onReaction)
    // A direct message has its first message: it is about to be listed. Refetch
    // rather than write — the list is the server's, ordered and filtered by it.
    // `invalidateQueries` cancels a fetch in flight when the list has data, so a
    // poll that started before the commit cannot land without the DM. With no data
    // yet (the first load) TanStack joins the fetch in flight instead, and that
    // one may predate the message too — so ask again when it settles.
    live.on('channel_added', () => {
      const key = channelKeys.list(workspaceId)
      void queryClient.invalidateQueries({ queryKey: key })
      if (
        queryClient.getQueryData(key) === undefined &&
        queryClient.isFetching({ queryKey: key, exact: true }) > 0
      ) {
        reapplyAfterFetch(queryClient, key, () => {
          void queryClient.invalidateQueries({ queryKey: key })
        })
      }
    })
    // The user's own marker moved elsewhere (another tab): clear the count here.
    live.on('read_receipt_updated', (event: ReadReceiptEvent) =>
      applyReadReceipt(queryClient, workspaceId, event, userId),
    )

    return () => {
      live.close()
      setSocket(null)
      setConnectionStatus('disconnected')
      setJoinedChannel(null)
    }
  }, [accessToken, workspaceId, userId, queryClient, setConnectionStatus, setJoinedChannel])

  // Joining and leaving follow the open channel, and are separate from the
  // connection's own lifecycle: navigating between channels must not reconnect.
  useEffect(() => {
    if (!socket || !channelId) return

    if (socket.connected) {
      joinChannel(socket, channelId, () => {
        if (activeChannel.current === channelId) setJoinedChannel(channelId)
        // The history loaded as the channel opened, while this join was in
        // flight — a message sent in that window is in neither.
        refetchHistory(queryClient, messageKeys.list(workspaceId, channelId))
        void queryClient.invalidateQueries({ queryKey: threadKeys.all(workspaceId, channelId) })
      })
    }
    return () => {
      setJoinedChannel(null)
      if (socket.connected) socket.emit('leave_channel', channelId)
    }
  }, [socket, channelId, workspaceId, queryClient, setJoinedChannel])

  return socket
}
