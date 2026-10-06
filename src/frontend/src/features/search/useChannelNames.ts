/**
 * Channel titles for search results, which carry only a channel id: `#general`
 * for a channel, the other person's name for a direct message (`channelTitle`).
 *
 * Names come from the channel list the sidebar already holds. The list is the
 * first page of the user's channels, so a result can sit in a channel outside it:
 * those ids are looked up one by one through the channel's detail entry — shared
 * with `ChannelView`, and `staleTime: Infinity` so each distinct channel is asked
 * for once however often the page re-renders. A lookup waits for the list to
 * settle, or it would ask for details the list was about to supply. `retry: false`
 * makes a 404 settle at once; a pending or failed lookup reads `null`, and the row
 * shows a placeholder.
 */

import { useQueries } from '@tanstack/react-query'

import { getChannel } from '../../lib/api/messaging'
import { channelTitle } from '../channels/directMessages'
import { channelKeys, useChannels } from '../channels/useChannels'

export function useChannelNames(
  accessToken: string,
  workspaceId: string | null,
  channelIds: readonly string[],
  nameFor: (userId: string) => string,
): (channelId: string) => string | null {
  const list = useChannels(accessToken, workspaceId)
  const settled = list.isSuccess || list.isError

  const known = new Map(
    (list.data ?? []).map((channel) => [channel.id, channelTitle(channel, nameFor)]),
  )
  const missing = settled ? [...new Set(channelIds)].filter((id) => !known.has(id)) : []

  const details = useQueries({
    queries: missing.map((channelId) => ({
      queryKey: channelKeys.detail(workspaceId, channelId),
      queryFn: () => getChannel(accessToken, channelId),
      retry: false,
      staleTime: Infinity,
    })),
  })
  const fetched = new Map(
    missing.flatMap((id, index) => {
      const channel = details[index]?.data
      return channel === undefined ? [] : [[id, channelTitle(channel, nameFor)] as const]
    }),
  )

  return (channelId) => known.get(channelId) ?? fetched.get(channelId) ?? null
}
