/**
 * "2 replies", and when the last one came, under the message they answer.
 *
 * A button, because it is how a thread opens from the channel — and the only way
 * into a deleted root's thread. Renders nothing at zero: a message nobody has
 * answered shows no thread furniture. The time is `<time dateTime>` like every
 * other time in the UI, in the user's chosen clock or the browser's own locale
 * (register D28).
 */

import { timeOfDay } from '../../lib/time'
import { useClock } from '../settings/usePreferences'

interface Props {
  replyCount: number
  lastReplyAt: string | null
  onOpen: () => void
}

export function ThreadSummary({ replyCount, lastReplyAt, onOpen }: Props) {
  const clock = useClock()
  if (replyCount === 0) return null

  return (
    <button
      type="button"
      data-testid="thread-summary"
      data-reply-count={replyCount}
      onClick={onOpen}
      className="flex w-fit items-baseline gap-2 text-xs text-accent hover:underline"
    >
      {replyCount === 1 ? '1 reply' : `${replyCount} replies`}
      {lastReplyAt && (
        <span className="text-ink-muted">
          last reply <time dateTime={lastReplyAt}>{timeOfDay(lastReplyAt, clock)}</time>
        </span>
      )}
    </button>
  )
}
