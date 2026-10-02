/**
 * The open channel: its header, its history, its composer and its members.
 *
 * The composition is the point of this file; everything it renders belongs to a
 * component of its own. What it owns is the one query the others hang off —
 * the channel itself — and the three states that query can be in, including the
 * clean "not found" that a channel id nobody may see has to produce.
 */

import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { useEffect } from 'react'

import { getChannel } from '../../lib/api/messaging'
import { ThreadPanel } from '../threads/ThreadPanel'
import { useThreadParam } from '../threads/useThreadParam'
import { ChannelHeader } from './ChannelHeader'
import { MemberPanel } from './MemberPanel'
import { MessageComposer } from './MessageComposer'
import { MessageList } from './MessageList'
import { channelKeys } from './useChannels'
import { useChatStore } from '../../stores/chat'

interface Props {
  accessToken: string
  workspaceId: string | null
  userId: string
}

export function ChannelView({ accessToken, workspaceId, userId }: Props) {
  const { channelId } = useParams<{ channelId: string }>()
  const setActiveChannel = useChatStore((state) => state.setActiveChannel)

  useEffect(() => {
    setActiveChannel(channelId ?? null)
    return () => setActiveChannel(null)
  }, [channelId, setActiveChannel])

  const queryClient = useQueryClient()
  // Which thread is open lives in the URL. Switching channel drops it, since
  // the new channel's address carries no `?thread=`.
  const { threadId, openThread, closeThread } = useThreadParam()

  // Opening a channel refetches the list: the sidebar's counts are the
  // server's, and the user has just changed what they are looking at.
  useEffect(() => {
    void queryClient.invalidateQueries({ queryKey: channelKeys.list(workspaceId) })
  }, [queryClient, workspaceId, channelId])

  const {
    data: channel,
    isPending,
    isFetching,
    error,
  } = useQuery({
    queryKey: channelKeys.detail(workspaceId, channelId),
    queryFn: () => getChannel(accessToken, channelId as string),
    enabled: Boolean(channelId),
  })

  if (isPending) {
    return (
      <p data-testid="channel-loading" className="p-6 text-sm text-ink-muted">
        Loading…
      </p>
    )
  }

  if (error) {
    return (
      <p data-testid="channel-error" role="alert" className="p-6 text-sm text-danger">
        {error.message}
      </p>
    )
  }

  return (
    <section
      data-testid="channel-view"
      data-channel-name={channel.name}
      className="flex h-full flex-col"
    >
      <ChannelHeader accessToken={accessToken} workspaceId={workspaceId} channel={channel} />

      <div className="flex min-h-0 flex-1">
        <div className="flex min-w-0 flex-1 flex-col">
          {/* Keyed by channel: every channel is a fresh mount, which starts at
              its newest message, measures the bottom, takes its divider once
              and flushes its pending read as it unmounts. */}
          <MessageList
            key={channel.id}
            accessToken={accessToken}
            workspaceId={workspaceId}
            channelId={channel.id}
            userId={userId}
            myRole={channel.myRole ?? null}
            lastReadId={channel.lastReadId ?? null}
            channelFetching={isFetching}
            onOpenThread={openThread}
          />
          {/* Enabled for any channel this view can render: visibility is the
              write test as well as the read one, so someone who can see a
              public channel can talk in it without joining. */}
          {/* Keyed by channel, so a half-finished batch error from one channel
              is not carried into the next. Text, chips and send errors are per
              channel in their stores. A key of its own: the list above is
              keyed by the same id, and siblings must not share one. */}
          <MessageComposer
            key={`composer-${channel.id}`}
            accessToken={accessToken}
            workspaceId={workspaceId}
            channelId={channel.id}
            channelName={channel.name}
            userId={userId}
          />
        </div>

        {/* A thread takes the members' place: one right-hand column, so the
            channel list never loses width to a third pane. Keyed by the root so
            each thread is a fresh mount with its own scroll position. */}
        {threadId ? (
          <ThreadPanel
            key={threadId}
            accessToken={accessToken}
            workspaceId={workspaceId}
            channelId={channel.id}
            rootId={threadId}
            userId={userId}
            myRole={channel.myRole ?? null}
            onClose={closeThread}
          />
        ) : (
          <MemberPanel accessToken={accessToken} workspaceId={workspaceId} channel={channel} />
        )}
      </div>
    </section>
  )
}
