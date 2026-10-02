/**
 * The sender of `mark_read`: one throttle per socket, the local write that goes
 * with each emit, and what leaving a channel does to a read still waiting.
 *
 * **No queue and no retry.** A read that cannot be sent (disconnected, already
 * covered by the cached marker, another workspace) is not sent, and nothing
 * sends it later by itself — the caller asks again when something changes. The
 * marker is forward-only on the server, so a later read covers an earlier one.
 *
 * **The local write is held until the ack.** `send` writes the caches as it
 * emits so the badge clears at once, then holds that write against any fetch
 * that began before the server committed. Whatever the ack says — ok, a
 * problem, or the timeout — only releases the hold; it never rolls back.
 */

import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'

import { snapshot } from '../../lib/auth/session'
import type { Socket } from '../../lib/realtime/socket'
import { cachedLastReadId, holdLocalRead, writeLocalRead } from './readCache'
import { isAtOrPast, isLiveWorkspace } from './readState'
import { createReadThrottle, type ReadThrottle } from './readThrottle'

/** How long to wait for the server's ack before releasing the hold. */
export const MARK_READ_TIMEOUT_MS = 5000

export function useMarkRead(
  socket: Socket | null,
  workspaceId: string | null,
  channelId: string,
): { request: (messageId: string) => void; connected: boolean; flush: () => void } {
  const queryClient = useQueryClient()
  const throttle = useRef<ReadThrottle | null>(null)
  const [connected, setConnected] = useState(socket?.connected ?? false)

  useEffect(() => {
    setConnected(socket?.connected ?? false)
    if (!socket) return
    const up = () => setConnected(true)
    const down = () => setConnected(false)
    socket.on('connect', up)
    socket.on('disconnect', down)
    return () => {
      socket.off('connect', up)
      socket.off('disconnect', down)
    }
  }, [socket])

  // Declared before the throttle effect so that on unmount this cleanup runs
  // first: the held read is flushed while the throttle is still alive. It is
  // keyed on the channel alone — a socket change must drop a held read, not
  // send it down a connection that is going away.
  useEffect(() => {
    return () => throttle.current?.flush(channelId)
  }, [channelId])

  useEffect(() => {
    if (!socket) return
    const holds = new Map<string, () => void>()

    // Read live at call time, never from the last render: a workspace switch
    // sets the session before React renders, and the unmount's flush can run
    // while the old socket is still connected (plan decision 30).
    function send(forChannel: string, messageId: string): boolean {
      if (!socket?.connected || !isLiveWorkspace(snapshot(), workspaceId)) return false
      if (isAtOrPast(cachedLastReadId(queryClient, workspaceId, forChannel), messageId)) {
        return false
      }

      writeLocalRead(queryClient, workspaceId, forChannel, messageId)
      holds.get(forChannel)?.()
      const release = holdLocalRead(queryClient, workspaceId, forChannel, messageId)
      holds.set(forChannel, release)
      socket
        .timeout(MARK_READ_TIMEOUT_MS)
        .emit('mark_read', { channelId: forChannel, messageId }, () => release())
      return true
    }

    const live = createReadThrottle(send)
    throttle.current = live
    return () => {
      live.dispose()
      // Holds are NOT released here. This cleanup also runs on unmount, and the
      // list remounts on every channel switch: a read still waiting for its ack
      // must keep its hold, or the switch's list fetch can bring the badge back.
      // Each hold ends by its own ack, error ack or timeout; on a socket change
      // socket.io-client calls every pending ack with an error when it closes.
      holds.clear()
      if (throttle.current === live) throttle.current = null
    }
  }, [socket, workspaceId, queryClient])

  const request = useCallback(
    (messageId: string) => throttle.current?.request(channelId, messageId),
    [channelId],
  )

  // Sends this channel's held read now. A jump starting on the open channel calls
  // it: that read was earned before the jump, and waiting out its window would
  // send it during the jump.
  const flush = useCallback(() => throttle.current?.flush(channelId), [channelId])

  return { request, connected, flush }
}
