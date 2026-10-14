/**
 * Server state for channels, owned by TanStack Query (register D24).
 *
 * **The workspace id is part of every key.** An access token is scoped to one
 * workspace (Conventions §5.4), so a cached channel list belongs to that
 * workspace and to no other. Doc 06 §4 asks for the cache to be cleared on a
 * switch; keying by workspace gets the same guarantee without a lifecycle hook
 * that could be forgotten — the new workspace simply reads a different entry,
 * and switching back does not refetch what is still valid.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'

import {
  archiveChannel,
  createChannel,
  listChannels,
  openDirectMessage,
  updateChannel,
  type Channel,
  type ChannelKind,
} from '../../lib/api/messaging'

export const channelKeys = {
  list: (workspaceId: string | null) => ['channels', workspaceId] as const,
  detail: (workspaceId: string | null, channelId: string | undefined) =>
    ['channel', workspaceId, channelId] as const,
}

/**
 * How often the sidebar refetches, so unread counts for channels the user is
 * not looking at stay current. Polling, not push (see the ADR on unread state).
 * `refetchIntervalInBackground` stays false: TanStack skips a tick while the
 * tab is hidden, which is the "none while hidden" the counts need.
 */
export const CHANNEL_POLL_MS = 30_000

export function useChannels(accessToken: string, workspaceId: string | null) {
  return useQuery({
    queryKey: channelKeys.list(workspaceId),
    queryFn: () => listChannels(accessToken),
    select: (page) => page.items,
    refetchInterval: CHANNEL_POLL_MS,
    // Off, because `useChannelListRefresh` answers a return to the tab itself:
    // TanStack hears `visibilitychange` only, so a window that regained focus
    // would not refetch, and leaving both on would cancel and restart a fetch
    // that a tab return starts twice.
    refetchOnWindowFocus: false,
  })
}

/**
 * Refetch the channel list once when the user comes back — the window gains
 * focus, or the tab becomes visible. A return fires both events; with
 * `cancelRefetch: false` the second joins the fetch already in flight.
 */
export function useChannelListRefresh(workspaceId: string | null): void {
  const queryClient = useQueryClient()

  useEffect(() => {
    function refetch() {
      void queryClient.refetchQueries(
        { queryKey: channelKeys.list(workspaceId) },
        { cancelRefetch: false },
      )
    }
    function onVisibility() {
      if (document.visibilityState === 'visible') refetch()
    }

    window.addEventListener('focus', refetch)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      window.removeEventListener('focus', refetch)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [queryClient, workspaceId])
}

export function useCreateChannel(accessToken: string, workspaceId: string | null) {
  const queryClient = useQueryClient()

  return useMutation<Channel, Error, { name: string; kind: ChannelKind }>({
    mutationFn: (body) => createChannel(accessToken, body),
    onSuccess: async () => {
      // Refetch rather than push the new channel into the cached array: the
      // list is ordered by name, and re-sorting it here would be a second
      // implementation of the server's ordering waiting to disagree with it.
      await queryClient.invalidateQueries({ queryKey: channelKeys.list(workspaceId) })
    },
  })
}

/**
 * Open the caller's direct message with someone: get or create, and the channel
 * comes back either way.
 *
 * The variables carry the workspace the open started in. The call can outlive a
 * workspace switch, and the list is keyed by workspace, so the invalidation goes
 * to the list the DM belongs to and no other; the caller compares the same id
 * with the current workspace before it navigates (decision 19). An empty DM is
 * not listed yet, so the invalidation changes nothing visible until a message is
 * sent — it keeps the cache honest for a DM that already had one.
 */
export function useOpenDirectMessage(accessToken: string) {
  const queryClient = useQueryClient()

  return useMutation<Channel, Error, { userId: string; workspaceId: string | null }>({
    mutationFn: ({ userId }) => openDirectMessage(accessToken, userId),
    onSuccess: async (channel, variables) => {
      await queryClient.invalidateQueries({ queryKey: channelKeys.list(variables.workspaceId) })
      return channel
    },
  })
}

/**
 * Rename a channel, or set its topic.
 *
 * Both the list and the detail entry are invalidated: the sidebar shows the
 * name and is ordered by it, and the open channel's header shows it too. A
 * rename that refreshed only one of them leaves the other reading the old name
 * until something else happens to refetch it.
 */
export function useRenameChannel(
  accessToken: string,
  workspaceId: string | null,
  channelId: string,
) {
  const queryClient = useQueryClient()

  return useMutation<Channel, Error, { version: number; name?: string; topic?: string | null }>({
    mutationFn: (body) => updateChannel(accessToken, channelId, body),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: channelKeys.list(workspaceId) }),
        queryClient.invalidateQueries({ queryKey: channelKeys.detail(workspaceId, channelId) }),
      ])
    },
  })
}

/**
 * Archive a channel.
 *
 * The detail entry is removed rather than invalidated: refetching it would ask
 * for a channel the server now hides, get a 404, and render the error page over
 * the top of wherever the user has just been sent. Navigating away is the
 * caller's job, and it has to happen — leaving Ada looking at a channel whose
 * next fetch 404s is the whole reason this is not just an invalidate.
 */
export function useArchiveChannel(
  accessToken: string,
  workspaceId: string | null,
  channelId: string,
) {
  const queryClient = useQueryClient()

  return useMutation<Channel, Error, void>({
    mutationFn: () => archiveChannel(accessToken, channelId),
    onSuccess: async () => {
      queryClient.removeQueries({ queryKey: channelKeys.detail(workspaceId, channelId) })
      await queryClient.invalidateQueries({ queryKey: channelKeys.list(workspaceId) })
    },
  })
}
