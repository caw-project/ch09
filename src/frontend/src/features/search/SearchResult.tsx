/**
 * One search hit: where it was said, who said it, when, and the words.
 *
 * The whole row is a link to `/c/<channel>?message=<id>` — a real anchor, so a
 * middle-click and a reload both work — and the channel's jump does the rest. The
 * body is a React text child, never markup, and nothing is highlighted in it: the
 * server returns no match offsets. The date format is the browser's locale, not a
 * stored preference (register D28 is open).
 */

import { Link } from 'react-router-dom'

import type { Message } from '../../lib/api/messaging'

interface Props {
  message: Message
  /** `null` while the channel's name is unknown — shown as `#…`. */
  channelName: string | null
  authorName: string
}

function when(iso: string): string {
  return new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
}

export function SearchResult({ message, channelName, authorName }: Props) {
  return (
    <Link
      to={`/c/${message.channelId}?message=${message.id}`}
      data-testid="search-result"
      data-message-id={message.id}
      className="flex flex-col gap-0.5 rounded px-3 py-2 hover:bg-surface-sunken"
    >
      <span className="flex items-baseline gap-2 text-xs text-ink-muted">
        <span className="font-medium text-ink">{channelName === null ? '#…' : `#${channelName}`}</span>
        <span>{authorName}</span>
        <time dateTime={message.createdAt}>{when(message.createdAt)}</time>
        {message.editedAt && <span>(edited)</span>}
      </span>
      <p className="text-sm whitespace-pre-wrap text-ink">{message.body}</p>
    </Link>
  )
}
