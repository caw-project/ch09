/**
 * The pure rules of read state: what the badge says, which message a read
 * targets, and where the "New messages" divider sits.
 *
 * Message ids are UUIDv7, so string order is time order; `messages` are
 * oldest-first, as `useMessages`'s `select` returns them. A pending send
 * (`temp:` id) sorts after every real id and is not on the server yet, so it is
 * never a target, a ceiling or a divider.
 */

import type { Message } from '../../lib/api/messaging'
import type { State } from '../../lib/auth/session'
import { isPending } from './useMessages'

/** The most the badge shows as a number; above it, `99+`. */
export const BADGE_MAX = 99

export function badgeText(count: number): string {
  return count > BADGE_MAX ? `${BADGE_MAX}+` : String(count)
}

/** The accessible name of the badge — the number as displayed. */
export function badgeLabel(count: number): string {
  return `${badgeText(count)} unread message${count === 1 ? '' : 's'}`
}

/** Whether the marker already covers `messageId`. No marker covers nothing. */
export function isAtOrPast(marker: string | null | undefined, messageId: string): boolean {
  return marker != null && marker >= messageId
}

/** The newest confirmed message: own messages and tombstones included. */
export function readTarget(messages: readonly Message[]): string | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (!isPending(messages[i])) return messages[i].id
  }
  return null
}

/** What a visit remembers from when the channel opened. */
export interface DividerCapture {
  lastReadId: string | null
  /** The newest confirmed message then: anything later arrived during the visit. */
  ceilingId: string | null
}

export function captureFor(lastReadId: string | null, messages: readonly Message[]): DividerCapture {
  return { lastReadId, ceilingId: readTarget(messages) }
}

/**
 * The message the divider sits above, or null.
 *
 * Follows the server's unread rule — after the marker, by someone else, not
 * deleted — limited to messages that existed at capture. With no marker there is
 * no divider, and with older pages still unloaded the boundary may be off screen:
 * it counts as loaded only when a loaded message is at or before the marker, or
 * there is no older page.
 */
export function findDivider(
  messages: readonly Message[],
  capture: DividerCapture,
  userId: string,
  hasOlder: boolean,
): string | null {
  const { lastReadId, ceilingId } = capture
  if (lastReadId === null || ceilingId === null) return null

  const confirmed = messages.filter((message) => !isPending(message))
  const boundaryLoaded = !hasOlder || confirmed.some((message) => message.id <= lastReadId)
  if (!boundaryLoaded) return null

  const first = confirmed.find(
    (message) =>
      message.id > lastReadId &&
      message.id <= ceilingId &&
      message.authorId !== userId &&
      message.deletedAt === null,
  )
  return first?.id ?? null
}

/**
 * Whether a read for `workspaceId` is still wanted, judged on the live session.
 *
 * `loading` counts as live: no message list exists before sign-in.
 */
export function isLiveWorkspace(state: State, workspaceId: string | null): boolean {
  if (state.status === 'signedOut') return false
  if (state.status === 'loading') return true
  return state.session.activeWorkspaceId === workspaceId
}
