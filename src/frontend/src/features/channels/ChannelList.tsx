/**
 * The channel sidebar.
 *
 * Shows every channel the caller may know about — public channels in the
 * workspace whether or not they have joined, plus private ones they belong to.
 * The server decides that and the order; this renders what it returns.
 *
 * A channel with unread messages gets a bold name and a count pill, except the
 * one being read right now (`readingChannelId`): its count is about to be
 * cleared by that very read, and flashing it between a refetch and the ack would
 * be noise. The moment the page stops being watched the badge is back.
 */

import { NavLink } from 'react-router-dom'

import { useChatStore } from '../../stores/chat'
import { badgeLabel, badgeText } from './readState'
import { useChannelListRefresh, useChannels } from './useChannels'

interface Props {
  accessToken: string
  workspaceId: string | null
}

export function ChannelList({ accessToken, workspaceId }: Props) {
  const { data: channels, isPending, error } = useChannels(accessToken, workspaceId)
  const readingChannelId = useChatStore((state) => state.readingChannelId)
  useChannelListRefresh(workspaceId)

  if (isPending) {
    return (
      <p data-testid="channel-list-loading" className="p-3 text-sm text-ink-muted">
        Loading channels…
      </p>
    )
  }

  // TanStack keeps `data` when a refetch fails but still sets `error`, so
  // testing `error` alone would replace a list the user is using with a banner.
  if (channels === undefined) {
    return (
      <p data-testid="channel-list-error" role="alert" className="p-3 text-sm text-danger">
        {error?.message}
      </p>
    )
  }

  if (channels.length === 0) {
    return (
      <p data-testid="channel-list-empty" className="p-3 text-sm text-ink-muted">
        No channels yet. Create the first one.
      </p>
    )
  }

  return (
    <ul data-testid="channel-list" className="flex flex-col gap-0.5 p-2">
      {channels.map((channel) => {
        const unread = channel.unreadCount > 0 && channel.id !== readingChannelId
        return (
          <li key={channel.id}>
            <NavLink
              to={`/c/${channel.id}`}
              data-testid="channel-list-item"
              data-channel-name={channel.name}
              className={({ isActive }) =>
                [
                  'flex items-center justify-between gap-2 rounded px-2 py-1 text-sm',
                  isActive ? 'bg-accent text-accent-ink' : 'text-ink hover:bg-surface-sunken',
                ].join(' ')
              }
            >
              <span>
                <span aria-hidden="true" className="opacity-60">
                  #
                </span>{' '}
                <span className={unread ? 'font-semibold' : undefined}>{channel.name}</span>
              </span>
              {unread && (
                <span
                  data-testid="channel-unread-badge"
                  data-count={badgeText(channel.unreadCount)}
                  aria-label={badgeLabel(channel.unreadCount)}
                  className="rounded-full bg-danger px-1.5 text-xs font-semibold text-white"
                >
                  {badgeText(channel.unreadCount)}
                </span>
              )}
            </NavLink>
          </li>
        )
      })}
    </ul>
  )
}
