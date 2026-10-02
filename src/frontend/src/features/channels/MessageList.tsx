/**
 * A channel's history, oldest at the top, loading more as you scroll back.
 *
 * Two pieces of scroll behaviour that no design doc specifies and that every
 * chat app needs:
 *
 * **Anchoring on prepend.** Older messages are added *above* what the reader is
 * looking at, and the browser keeps `scrollTop` where it was — so the content
 * under the cursor jumps down by a page every time a page loads. The fix is to
 * record `scrollHeight` before the prepend and add the difference back in a
 * `useLayoutEffect`, before the browser paints.
 *
 * **Sticking to the bottom, but only if you were there.** A new message should
 * scroll into view for someone watching the live end of a conversation, and
 * must not yank someone who has scrolled up to read something. So the decision
 * is made *before* the render that adds the message, not after.
 */

import { Fragment, useEffect, useLayoutEffect, useRef, useState } from 'react'

import { ProblemBanner } from '../../components/ProblemBanner'
import type { Message } from '../../lib/api/messaging'
import { useSocket } from '../../lib/realtime/SocketProvider'
import { useChatStore } from '../../stores/chat'
import { MessageItem } from './MessageItem'
import { captureFor, findDivider, readTarget, type DividerCapture } from './readState'
import { useMarkRead } from './useMarkRead'
import { usePageAttention } from './usePageAttention'
import { useDeleteMessage, useEditMessage, useMessages, useToggleReaction } from './useMessages'
import { useWorkspaceMembers } from './useWorkspaceMembers'

interface Props {
  accessToken: string
  workspaceId: string | null
  channelId: string
  /** The signed-in user, so each row knows whose words it is showing. */
  userId: string
  /** The caller's role in this channel — `admin` may delete anyone's message. */
  myRole: string | null
  /** The channel detail's marker, as `ChannelView` holds it — captured once per visit. */
  lastReadId: string | null
  /** The detail query's `isFetching`: the capture waits for it to settle. */
  channelFetching: boolean
  /** Open a message's thread; absent and the rows offer no thread action. */
  onOpenThread?: (rootId: string) => void
}

/** Within this many pixels of the bottom counts as "watching the live end". */
export const STICK_THRESHOLD = 80
/** Within this many pixels of the top starts fetching the next page back. */
export const LOAD_THRESHOLD = 120

/** Nothing loaded yet — one array, so an effect that depends on it is not re-run each render. */
const NO_MESSAGES: Message[] = []

/**
 * Whether the viewport is at the live end. The gap below the viewport, not the
 * gap below the top edge: at the very bottom `scrollTop` stops a whole
 * `clientHeight` short of `scrollHeight`.
 */
function measure(element: HTMLElement): boolean {
  return element.scrollHeight - element.scrollTop - element.clientHeight < STICK_THRESHOLD
}

export function MessageList({
  accessToken,
  workspaceId,
  channelId,
  userId,
  myRole,
  lastReadId,
  channelFetching,
  onOpenThread,
}: Props) {
  const scroller = useRef<HTMLDivElement>(null)
  const heightBeforePrepend = useRef<number | null>(null)
  const wasAtBottom = useRef(true)
  const previousCount = useRef(0)
  // Measured, never assumed: a fresh list is not "at the bottom" until its own
  // scroll to the newest message has been measured.
  const [atBottom, setAtBottom] = useState(false)
  const [capture, setCapture] = useState<DividerCapture | null>(null)
  const [pinnedDivider, setPinnedDivider] = useState<string | null>(null)

  const socket = useSocket()
  const attending = usePageAttention()
  const { request, connected } = useMarkRead(socket, workspaceId, channelId)
  const setReadingChannel = useChatStore((state) => state.setReadingChannel)

  const directory = useWorkspaceMembers(accessToken, workspaceId)
  const {
    data,
    isPending,
    isFetching,
    isSuccess,
    error,
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
  } = useMessages(accessToken, workspaceId, channelId)
  // One mutation for the whole list rather than one per row: an edit is a
  // modal act — nobody edits two messages at once — and hanging the hooks off
  // each `MessageItem` would mean a mutation object per rendered message.
  const edit = useEditMessage(accessToken, workspaceId, channelId)
  const remove = useDeleteMessage(accessToken, workspaceId, channelId)
  const toggleReaction = useToggleReaction(accessToken, workspaceId, channelId, userId)

  const messages: Message[] = data ?? NO_MESSAGES

  // The divider's anchor is taken once per visit (the list is remounted per
  // channel), at the first render where both the detail and the history have
  // settled. A cached channel is refetched on return, so this waits for the
  // refetches and takes today's marker, not the stale cached one.
  useEffect(() => {
    if (capture !== null || channelFetching || !isSuccess || isFetching) return
    setCapture(captureFor(lastReadId, messages))
  }, [capture, channelFetching, isSuccess, isFetching, lastReadId, messages])

  // Once found, the divider's message is pinned for the visit: the marker moves
  // as the user reads, and a deleted message stops qualifying.
  const found = capture ? findDivider(messages, capture, userId, Boolean(hasNextPage)) : null
  useEffect(() => {
    if (pinnedDivider === null && found !== null) setPinnedDivider(found)
  }, [pinnedDivider, found])
  const dividerId = pinnedDivider ?? found

  const beingRead = attending && atBottom
  useEffect(() => {
    setReadingChannel(beingRead ? channelId : null)
    return () => setReadingChannel(null)
  }, [beingRead, channelId, setReadingChannel])

  // Ask for a read whenever every condition holds, and again when any changes —
  // a new newest message, the connection coming back. The sender decides whether
  // there is anything to send. Not before the capture: the read would move the
  // marker the divider is about to be taken from.
  const target = readTarget(messages)
  useEffect(() => {
    if (beingRead && capture !== null && connected && target !== null) request(target)
  }, [beingRead, capture, connected, target, request])

  function onScroll() {
    const element = scroller.current
    if (!element) return

    const bottom = measure(element)
    wasAtBottom.current = bottom
    setAtBottom(bottom)

    if (element.scrollTop < LOAD_THRESHOLD && hasNextPage && !isFetchingNextPage) {
      // Remember where the content started so the prepend can be undone.
      heightBeforePrepend.current = element.scrollHeight
      void fetchNextPage()
    }
  }

  useLayoutEffect(() => {
    const element = scroller.current
    if (!element) return

    const before = heightBeforePrepend.current
    if (before !== null && element.scrollHeight !== before) {
      element.scrollTop += element.scrollHeight - before
      heightBeforePrepend.current = null
      previousCount.current = messages.length
    } else {
      const grew = messages.length > previousCount.current
      previousCount.current = messages.length
      if (grew && wasAtBottom.current) {
        element.scrollTop = element.scrollHeight
      }
    }

    // Measure after any programmatic scroll: that is what says whether the
    // reader is, now, at the live end. `isPending` is a dependency because the
    // scroller does not exist until the history arrives, even when it is empty.
    setAtBottom(measure(element))
  }, [messages.length, isPending])

  if (isPending) {
    return (
      <p data-testid="message-list-loading" className="p-6 text-sm text-ink-muted">
        Loading messages…
      </p>
    )
  }

  if (error) {
    return (
      <p data-testid="message-list-error" role="alert" className="p-6 text-sm text-danger">
        {error.message}
      </p>
    )
  }

  return (
    <div
      ref={scroller}
      onScroll={onScroll}
      data-testid="message-list"
      className="flex-1 overflow-y-auto"
    >
      {isFetchingNextPage && (
        <p data-testid="message-list-older" className="p-2 text-center text-xs text-ink-muted">
          Loading older messages…
        </p>
      )}

      {messages.length === 0 ? (
        <p data-testid="message-list-empty" className="p-6 text-sm text-ink-muted">
          Nothing here yet. Say something.
        </p>
      ) : (
        messages.map((message) => (
          <Fragment key={message.id}>
            {message.id === dividerId && (
              <div
                role="separator"
                aria-label="New messages"
                data-testid="new-messages-divider"
                className="flex items-center gap-2 px-4 py-1 text-xs font-semibold text-danger"
              >
                <span aria-hidden="true" className="h-px flex-1 bg-current opacity-40" />
                New messages
                <span aria-hidden="true" className="h-px flex-1 bg-current opacity-40" />
              </div>
            )}
            <MessageItem
              message={message}
              authorName={directory.nameFor(message.authorId)}
              userId={userId}
              myRole={myRole}
              editError={edit.variables?.messageId === message.id ? edit.error : undefined}
              editPending={edit.isPending && edit.variables?.messageId === message.id}
              onEdit={(body, version) => edit.mutate({ messageId: message.id, body, version })}
              onDelete={() => remove.mutate(message.id)}
              onToggleReaction={(emoji) => toggleReaction.mutate({ message, emoji })}
              onOpenThread={onOpenThread && (() => onOpenThread(message.id))}
            />
          </Fragment>
        ))
      )}

      {/* A refused delete has no field to sit against and no editor open to
          show it in, so it belongs here rather than on the row. */}
      <ProblemBanner error={remove.error} />
    </div>
  )
}
