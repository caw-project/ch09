/** The unread count pill a sidebar row carries — shared by channels and direct messages. */

import { badgeLabel, badgeText } from './readState'

export function UnreadBadge({ count }: { count: number }) {
  return (
    <span
      data-testid="channel-unread-badge"
      data-count={badgeText(count)}
      aria-label={badgeLabel(count)}
      className="rounded-full bg-danger px-1.5 text-xs font-semibold text-white"
    >
      {badgeText(count)}
    </span>
  )
}
