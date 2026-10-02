/**
 * Where you type a reply.
 *
 * `MessageComposer`'s twin for a thread, with the same three rules: no
 * client-side length check (the server owns the limit); the draft is cleared at
 * once and put back if the send is refused; and it is disabled, with the reason
 * visible, while the socket is down.
 *
 * **The draft is the thread's, keyed by the root** (`threadDrafts`), apart from
 * the channel's own — so typing here can never become the text in the channel's
 * composer, and each open thread remembers what was half-typed in it (R14).
 *
 * No typing indicator: the issue leaves typing in threads out, and a
 * `typing` event names a channel, not a thread, so it would tell the whole
 * channel someone is typing a message they are not.
 */

import { type FormEvent, type KeyboardEvent } from 'react'

import { describeError, ProblemError } from '../../lib/api/client'
import { useSocket } from '../../lib/realtime/SocketProvider'
import { useChatStore } from '../../stores/chat'
import { useSendReply } from './useThread'

interface Props {
  workspaceId: string | null
  channelId: string
  rootId: string
  userId: string
}

export function ThreadComposer({ workspaceId, channelId, rootId, userId }: Props) {
  const draft = useChatStore((state) => state.threadDrafts[rootId] ?? '')
  const setThreadDraft = useChatStore((state) => state.setThreadDraft)
  const clearThreadDraft = useChatStore((state) => state.clearThreadDraft)
  const connectionStatus = useChatStore((state) => state.connectionStatus)

  const socket = useSocket()
  const send = useSendReply(socket, workspaceId, channelId, rootId, userId)

  const offline = connectionStatus !== 'connected'
  const problem = send.error instanceof ProblemError ? send.error : undefined
  const bodyError = problem?.fieldError('body')
  const otherError = send.error && !bodyError ? describeError(send.error) : undefined

  function submit(event?: FormEvent) {
    event?.preventDefault()
    if (!draft) return

    // Cleared straight away, because the reply is already on screen — and put
    // back if the send is refused, so nothing typed is lost.
    const text = draft
    clearThreadDraft(rootId)
    send.mutate(text, { onError: () => setThreadDraft(rootId, text) })
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <form
      onSubmit={submit}
      data-testid="thread-composer"
      className="flex flex-col gap-2 border-t border-border p-3"
    >
      <div className="flex items-end gap-2">
        <textarea
          data-testid="thread-composer-input"
          value={draft}
          onChange={(event) => setThreadDraft(rootId, event.target.value)}
          onKeyDown={onKeyDown}
          rows={2}
          disabled={offline}
          aria-label="Reply"
          placeholder={offline ? 'Reconnecting…' : 'Reply…'}
          className="min-w-0 flex-1 resize-none rounded border border-border bg-surface px-3 py-2 text-sm text-ink disabled:opacity-60"
        />
        <button
          type="submit"
          data-testid="thread-composer-send"
          disabled={offline}
          className="rounded bg-accent px-3 py-2 text-sm font-medium text-accent-ink disabled:opacity-60"
        >
          Send reply
        </button>
      </div>

      {offline && (
        <p className="text-xs text-ink-muted">
          Not connected — replies cannot be sent until the connection is back.
        </p>
      )}

      {(bodyError || otherError) && (
        <p role="alert" className="text-sm text-danger">
          {bodyError ?? otherError}
        </p>
      )}
    </form>
  )
}
