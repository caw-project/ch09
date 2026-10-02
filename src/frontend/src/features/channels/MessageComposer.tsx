/**
 * Where you type, and where you attach.
 *
 * The server owns the rules and this does not restate them. **No client-side
 * length check and no `maxlength`**, deliberately: a second copy of a limit is
 * a copy that drifts from the one guarding the database, and pre-validating
 * here would mean the over-long send never leaves the browser — so there would
 * be nothing to roll back and no error to render, which is exactly the
 * behaviour the slice exists to build. `CreateChannelDialog` made the same call
 * for channel names. (The *file* rules are different: they are checked here too,
 * before an upload starts, so the person reads which one refused — see
 * `attachments/rules.ts`.)
 *
 * **Sending goes over the socket, and renders before the server confirms.** The
 * message appears greyed the instant enter is pressed and settles when the ack
 * lands; a refusal takes it back out and puts the words — and the files — back in
 * this box (`useSendMessage`). `POST /channels/{id}/messages` stays alive as the
 * documented REST fallback — moving the composer off it does not delete the route.
 *
 * **Files are attached by the paperclip, a drop or a paste**, each becoming a chip
 * that uploads straight to storage while the person keeps typing. Send waits for
 * every chip to be `ready`, and for there to be no more than ten; a message may be
 * only files. Chips are client state, keyed by channel, so switching channels
 * loses neither text nor files.
 *
 * **The composer is disabled while the socket is down**, with the reason
 * visible. `emit` on a closed socket does not fail, it buffers, and the callback
 * never fires — so a dead input that says why beats a live one that silently
 * swallows what you type. There is no offline queue: it would need ordering,
 * durable storage and dedupe against a write with no idempotency key.
 *
 * Half-typed text is client state by definition, so it lives in Zustand and
 * survives switching channels and coming back. So does a refused send's error,
 * which is per channel: it belongs to the composer it came from.
 *
 * Enter sends and Shift+Enter breaks a line, which is what people expect from a
 * chat box and is why this is a `textarea`.
 */

import {
  type ClipboardEvent,
  type DragEvent,
  type FormEvent,
  type KeyboardEvent,
  useEffect,
  useRef,
  useState,
} from 'react'

import * as session from '../../lib/auth/session'
import { useSocket } from '../../lib/realtime/SocketProvider'
import { useAttachmentStore } from '../../stores/attachments'
import { useChatStore } from '../../stores/chat'
import { AttachmentChips } from '../attachments/AttachmentChips'
import { ALLOWED_TYPES, MAX_FILES, filesFromPaste } from '../attachments/rules'
import { addFiles } from '../attachments/uploads'
import { TypingIndicator } from './TypingIndicator'
import { useSendMessage } from './useMessages'
import { useTyping } from './useTyping'
import { useWorkspaceMembers } from './useWorkspaceMembers'

interface Props {
  accessToken: string
  workspaceId: string | null
  channelId: string
  channelName: string
  userId: string
}

const NO_CHIPS: never[] = []

export function MessageComposer({
  accessToken,
  workspaceId,
  channelId,
  channelName,
  userId,
}: Props) {
  const draft = useChatStore((state) => state.drafts[channelId] ?? '')
  const setDraft = useChatStore((state) => state.setDraft)
  const clearDraft = useChatStore((state) => state.clearDraft)
  const connectionStatus = useChatStore((state) => state.connectionStatus)
  const sendError = useChatStore((state) => state.sendErrors[channelId])
  const chips = useAttachmentStore((state) => state.chips[channelId] ?? NO_CHIPS)
  const clearChips = useAttachmentStore((state) => state.clear)

  const socket = useSocket()
  const directory = useWorkspaceMembers(accessToken, workspaceId)
  const { typingUserIds, onKeystroke } = useTyping(socket, channelId, userId)
  const send = useSendMessage(socket, workspaceId, channelId, userId)

  // The latest token, read when each upload step starts: a long upload can
  // outlive the access token it began with — and the composer too, since a
  // channel switch unmounts it while the upload carries on. So the session is
  // asked, not this component's prop; the ref is the fallback for a session that
  // is not signed in (a test, or a sign-out mid-upload, which the 401 then ends).
  const token = useRef(accessToken)
  useEffect(() => {
    token.current = accessToken
  }, [accessToken])
  const picker = useRef<HTMLInputElement>(null)
  const [batchError, setBatchError] = useState<string | null>(null)

  const offline = connectionStatus !== 'connected'
  const over = Math.max(0, chips.length - MAX_FILES)
  const filesReady = chips.every((chip) => chip.status === 'ready')
  const hasSomething = draft !== '' || chips.length > 0
  const canSend = !offline && hasSomething && filesReady && over === 0

  function attach(files: File[]) {
    setBatchError(
      addFiles(channelId, files, () => {
        const state = session.snapshot()
        return state.status === 'signedIn' ? state.session.accessToken : token.current
      }),
    )
  }

  function submit(event?: FormEvent) {
    event?.preventDefault()
    if (!canSend) return

    // The draft and the chips are cleared straight away, because the message is
    // already on screen — and put back if the send is refused (`useSendMessage`),
    // so nothing typed or attached is lost.
    const body = draft
    const attachments = chips
    clearDraft(channelId)
    clearChips(channelId)
    send.mutate({ channelId, body, attachments })
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  function onPaste(event: ClipboardEvent<HTMLTextAreaElement>) {
    const files = filesFromPaste(event.clipboardData)
    // `null` is "let the browser paste": text, or nothing we would attach.
    if (files === null) return
    event.preventDefault()
    attach(files)
  }

  function onDrop(event: DragEvent<HTMLFormElement>) {
    if (event.dataTransfer.files.length === 0) return
    event.preventDefault()
    attach(Array.from(event.dataTransfer.files))
  }

  return (
    <div className="border-t border-border">
      <TypingIndicator names={typingUserIds.map((id) => directory.nameFor(id))} />

      <form
        onSubmit={submit}
        onDrop={onDrop}
        // Without this the browser treats a drop on the box as "open this file".
        onDragOver={(event) => event.preventDefault()}
        data-testid="message-composer"
        className="flex flex-col gap-2 p-4"
      >
        <AttachmentChips channelId={channelId} chips={chips} />

        <div className="flex items-end gap-2">
          <input
            ref={picker}
            type="file"
            multiple
            hidden
            data-testid="attach-files"
            aria-label="Attach files"
            accept={ALLOWED_TYPES.join(',')}
            onChange={(event) => {
              attach(Array.from(event.target.files ?? []))
              // So choosing the same file again fires `change` again.
              event.target.value = ''
            }}
          />
          <button
            type="button"
            aria-label="Choose files to attach"
            title="Attach files"
            disabled={offline}
            onClick={() => picker.current?.click()}
            className="rounded border border-border px-3 py-2 text-sm text-ink-muted disabled:opacity-60"
          >
            📎
          </button>
          <textarea
            data-testid="message-composer-input"
            value={draft}
            onChange={(event) => {
              setDraft(channelId, event.target.value)
              onKeystroke()
            }}
            onKeyDown={onKeyDown}
            onPaste={onPaste}
            rows={2}
            disabled={offline}
            aria-label={`Message #${channelName}`}
            placeholder={offline ? 'Reconnecting…' : `Message #${channelName}`}
            className="min-w-0 flex-1 resize-none rounded border border-border bg-surface px-3 py-2 text-sm text-ink disabled:opacity-60"
          />
          <button
            type="submit"
            data-testid="message-composer-send"
            disabled={!canSend}
            className="rounded bg-accent px-4 py-2 text-sm font-medium text-accent-ink disabled:opacity-60"
          >
            Send
          </button>
        </div>

        {offline && (
          <p data-testid="composer-offline" className="text-xs text-ink-muted">
            Not connected — messages cannot be sent until the connection is back.
          </p>
        )}

        {over > 0 && (
          <p className="text-sm text-danger">
            At most {MAX_FILES} files per message — remove {over}.
          </p>
        )}
        {batchError && <p className="text-sm text-danger">{batchError}</p>}

        {sendError && (
          <p data-testid="message-composer-error" role="alert" className="text-sm text-danger">
            {sendError}
          </p>
        )}
      </form>
    </div>
  )
}
