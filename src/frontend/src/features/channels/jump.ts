/**
 * The rule behind "open this search result in its channel": given what history
 * holds right now, what should the jump do next?
 *
 * Pure, so every precedence and both sides of the cap are provable without a
 * list, a clock or a fetch. `useMessageJump` runs it; this file only decides.
 */

import type { Message } from '../../lib/api/messaging'

/** The URL parameter that names the message to jump to. */
export const JUMP_PARAM = 'message'
/** The most pages a jump will have loaded in total — pages cached beforehand count. */
export const JUMP_PAGE_CAP = 10
/** How long the target stays highlighted once found. */
export const HIGHLIGHT_MS = 2000

export type JumpStep = 'wait' | 'found' | 'fetch' | 'give-up' | 'failed'

interface Input {
  target: string
  messages: readonly Message[]
  loadedPages: number
  hasNextPage: boolean
  /** History's `isFetching` — any fetch, a refetch included. */
  fetching: boolean
  /** History's `isError`. */
  failed: boolean
}

/**
 * Precedence: a failed fetch ends the jump; a fetch in flight makes it wait (a
 * refetch replaces the loaded pages, so looking now would race it); then the
 * target found; then the cap, inclusive; then more history; else nothing is
 * left to page back through, which is treated as the cap.
 */
export function nextJumpStep({
  target,
  messages,
  loadedPages,
  hasNextPage,
  fetching,
  failed,
}: Input): JumpStep {
  if (failed) return 'failed'
  if (fetching) return 'wait'
  if (messages.some((message) => message.id === target)) return 'found'
  if (loadedPages >= JUMP_PAGE_CAP) return 'give-up'
  return hasNextPage ? 'fetch' : 'give-up'
}
