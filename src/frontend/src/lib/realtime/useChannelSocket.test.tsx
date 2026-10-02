import type { InfiniteData } from '@tanstack/react-query'
import { act } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { channelKeys } from '../../features/channels/useChannels'
import { messageKeys, useMessages } from '../../features/channels/useMessages'
import { useChatStore } from '../../stores/chat'
import { messaging, requests } from '../../test/api'
import { aChannel, aMessage, aMessagePage, messageIdAt } from '../../test/factories'
import { createTestQueryClient, renderHookWithProviders } from '../../test/render'
import { latestSocket, type FakeSocket } from '../../test/socket'
import type { Channel, ChannelPage, Message, MessagePage } from '../api/messaging'
import { useChannelSocket } from './useChannelSocket'

const WORKSPACE = 'workspace-1'
const CHANNEL = 'channel-1'
const OTHER = 'channel-2'
/** The signed-in user, so a reaction event knows whose lit state it changes. */
const ADA = 'user-ada'

interface JoinAck {
  ok: boolean
}

/**
 * Plays a server that has received each `join_channel` but not answered yet.
 *
 * The gap between the emit and its acknowledgement is the whole bug: the
 * server enters the room only when it has checked the channel is visible, so
 * anything broadcast before the ack never reaches this connection.
 */
function holdJoins(socket: FakeSocket) {
  const pending: Array<(ack: JoinAck) => void> = []
  socket.onEmit('join_channel', () => new Promise<JoinAck>((resolve) => pending.push(resolve)))

  return {
    async reply(ack: JoinAck) {
      await act(async () => {
        pending.shift()?.(ack)
        await new Promise((resolve) => setTimeout(resolve, 0))
      })
    },
  }
}

function seedHistory(queryClient: ReturnType<typeof createTestQueryClient>, channelId: string) {
  queryClient.setQueryData<InfiniteData<MessagePage>>(messageKeys.list(WORKSPACE, channelId), {
    pages: [aMessagePage([])],
    pageParams: [undefined],
  })
}

function isInvalidated(queryClient: ReturnType<typeof createTestQueryClient>, channelId: string) {
  return queryClient.getQueryState(messageKeys.list(WORKSPACE, channelId))?.isInvalidated
}

const joinedChannel = () => useChatStore.getState().joinedChannelId

/**
 * Starts a history fetch for a channel and holds its response back.
 *
 * The response is the page the server read *before* the message the test is
 * about to broadcast existed — which is exactly what a real fetch answers when
 * the broadcast lands while it is in flight.
 */
function holdHistoryFetch(
  queryClient: ReturnType<typeof createTestQueryClient>,
  channelId: string,
) {
  let release!: (page: MessagePage) => void
  const response = new Promise<MessagePage>((resolve) => {
    release = resolve
  })
  const done = queryClient.fetchInfiniteQuery({
    queryKey: messageKeys.list(WORKSPACE, channelId),
    queryFn: () => response,
    initialPageParam: undefined as string | undefined,
  })

  return {
    async answer(page: MessagePage) {
      await act(async () => {
        release(page)
        await done
      })
    },
  }
}

function historyItems(queryClient: ReturnType<typeof createTestQueryClient>, channelId: string) {
  return queryClient.getQueryData<InfiniteData<MessagePage>>(
    messageKeys.list(WORKSPACE, channelId),
  )?.pages[0].items
}

describe('useChannelSocket', () => {
  it('writes a received message into that channel’s cached history', () => {
    const queryClient = createTestQueryClient()
    const key = messageKeys.list(WORKSPACE, CHANNEL)
    queryClient.setQueryData<InfiniteData<MessagePage>>(key, {
      pages: [aMessagePage([])],
      pageParams: [undefined],
    })

    renderHookWithProviders(() => useChannelSocket('token', WORKSPACE, CHANNEL, ADA), { queryClient })
    const socket = latestSocket()
    const message = aMessage({ channelId: CHANNEL, body: 'hello from grace' })

    act(() => socket.serverConnect())
    act(() => socket.serverEmit('message_received', message))

    expect(queryClient.getQueryData<InfiniteData<MessagePage>>(key)?.pages[0].items).toEqual([
      message,
    ])
    expect(socket.emitted).toContainEqual({ event: 'join_channel', args: [CHANNEL] })
  })

  describe('joining the open channel', () => {
    it('counts the channel as joined only once the server acknowledges the join', async () => {
      renderHookWithProviders(() => useChannelSocket('token', WORKSPACE, CHANNEL, ADA))
      const socket = latestSocket()
      const joins = holdJoins(socket)

      act(() => socket.serverConnect())

      expect(socket.emitted).toContainEqual({ event: 'join_channel', args: [CHANNEL] })
      expect(joinedChannel()).toBeNull()

      await joins.reply({ ok: true })

      expect(joinedChannel()).toBe(CHANNEL)
    })

    it('refetches the history on connect only after the join is acknowledged', async () => {
      const queryClient = createTestQueryClient()
      seedHistory(queryClient, CHANNEL)
      renderHookWithProviders(() => useChannelSocket('token', WORKSPACE, CHANNEL, ADA), { queryClient })
      const socket = latestSocket()
      const joins = holdJoins(socket)

      act(() => socket.serverConnect())

      // A refetch before the room is entered can miss a message sent in between.
      expect(isInvalidated(queryClient, CHANNEL)).toBe(false)

      await joins.reply({ ok: true })

      expect(isInvalidated(queryClient, CHANNEL)).toBe(true)
    })

    it('counts a channel opened on a live connection as joined once acknowledged', async () => {
      let channel: string | null = null
      const { rerender } = renderHookWithProviders(() =>
        useChannelSocket('token', WORKSPACE, channel, ADA),
      )
      const socket = latestSocket()
      const joins = holdJoins(socket)
      act(() => socket.serverConnect())

      channel = OTHER
      rerender()

      expect(socket.emitted).toContainEqual({ event: 'join_channel', args: [OTHER] })
      expect(joinedChannel()).toBeNull()

      await joins.reply({ ok: true })

      expect(joinedChannel()).toBe(OTHER)
    })

    it('refetches a newly opened channel once its join is acknowledged', async () => {
      const queryClient = createTestQueryClient()
      seedHistory(queryClient, OTHER)
      let channel: string | null = null
      const { rerender } = renderHookWithProviders(
        () => useChannelSocket('token', WORKSPACE, channel, ADA),
        { queryClient },
      )
      const socket = latestSocket()
      const joins = holdJoins(socket)
      act(() => socket.serverConnect())

      channel = OTHER
      rerender()

      // The history loaded as the channel opened, while the join was in flight.
      expect(isInvalidated(queryClient, OTHER)).toBe(false)

      await joins.reply({ ok: true })

      expect(isInvalidated(queryClient, OTHER)).toBe(true)
    })

    /**
     * A page fetch is in flight when the join ack lands. `opened` is how the
     * channel comes to be joined: on connect (the reconnect path) or opened on a
     * connection that is already live (the common one).
     */
    async function keepsPageAcrossAck(opened: 'on connect' | 'on a live socket') {
      let release!: () => void
      const held = new Promise<void>((resolve) => {
        release = resolve
      })
      messaging.get('/api/v1/channels/{channel_id}/messages', async ({ request }) => {
        if (new URL(request.url).searchParams.get('cursor') === 'p2') {
          await held
          return aMessagePage([aMessage({ channelId: CHANNEL, body: 'older' })])
        }
        return aMessagePage([aMessage({ channelId: CHANNEL, body: 'newer' })], 'p2')
      })
      const cursors = () =>
        requests()
          .filter((r) => r.url.pathname.endsWith('/messages'))
          .map((r) => r.url.searchParams.get('cursor'))
      const queryClient = createTestQueryClient()
      let channel: string | null = opened === 'on connect' ? CHANNEL : null
      const { result, rerender } = renderHookWithProviders(
        () => {
          useChannelSocket('token', WORKSPACE, channel, ADA)
          return useMessages('token', WORKSPACE, channel ?? undefined)
        },
        { queryClient },
      )
      const socket = latestSocket()
      const joins = holdJoins(socket)
      act(() => socket.serverConnect())
      if (opened === 'on a live socket') {
        channel = CHANNEL
        rerender()
      }
      // Either way the join has been emitted and is waiting for its ack.
      expect(socket.emitted).toContainEqual({ event: 'join_channel', args: [CHANNEL] })
      await vi.waitFor(() => expect(result.current.isSuccess).toBe(true))
      // A page fetch (a scroll to the top, or a jump) is in flight when the ack lands.
      act(() => void result.current.fetchNextPage({ cancelRefetch: false }))
      await vi.waitFor(() => expect(cursors()).toEqual([null, 'p2']))

      await joins.reply({ ok: true })
      release()

      // The page fetch survives the ack, and the refetch the ack asked for follows it.
      await vi.waitFor(() => expect(cursors()).toEqual([null, 'p2', null, 'p2']))
      await vi.waitFor(() => expect(result.current.isFetching).toBe(false))
      expect(
        queryClient.getQueryData<InfiniteData<MessagePage>>(messageKeys.list(WORKSPACE, CHANNEL))
          ?.pages,
      ).toHaveLength(2)
    }

    it('keeps a page fetched while the join is acknowledged on connect', () =>
      keepsPageAcrossAck('on connect'))

    it('keeps a page fetched while the join of a channel opened on a live socket is acknowledged', () =>
      keepsPageAcrossAck('on a live socket'))

    it('does not count a refused join as joined', async () => {
      renderHookWithProviders(() => useChannelSocket('token', WORKSPACE, CHANNEL, ADA))
      const socket = latestSocket()
      const joins = holdJoins(socket)

      act(() => socket.serverConnect())
      await joins.reply({ ok: false })

      expect(joinedChannel()).toBeNull()
    })

    it('keeps a message that arrives while the channel’s history first loads', async () => {
      const queryClient = createTestQueryClient()
      const history = holdHistoryFetch(queryClient, CHANNEL)
      renderHookWithProviders(() => useChannelSocket('token', WORKSPACE, CHANNEL, ADA), { queryClient })
      const socket = latestSocket()
      act(() => socket.serverConnect())
      const message = aMessage({ channelId: CHANNEL, body: 'the coffee has arrived' })

      act(() => socket.serverEmit('message_received', message))
      await history.answer(aMessagePage([]))

      expect(historyItems(queryClient, CHANNEL)).toEqual([message])
    })

    it('keeps a message that arrives while the channel’s history is being refetched', async () => {
      const queryClient = createTestQueryClient()
      seedHistory(queryClient, CHANNEL)
      const history = holdHistoryFetch(queryClient, CHANNEL)
      renderHookWithProviders(() => useChannelSocket('token', WORKSPACE, CHANNEL, ADA), { queryClient })
      const socket = latestSocket()
      act(() => socket.serverConnect())
      const message = aMessage({ channelId: CHANNEL, body: 'the coffee has arrived' })

      act(() => socket.serverEmit('message_received', message))
      await history.answer(aMessagePage([]))

      expect(historyItems(queryClient, CHANNEL)).toEqual([message])
    })

    it('keeps an edit that arrives during a refetch over the older copy it returns', async () => {
      const queryClient = createTestQueryClient()
      const original = aMessage({ channelId: CHANNEL, body: 'standup at four' })
      queryClient.setQueryData<InfiniteData<MessagePage>>(messageKeys.list(WORKSPACE, CHANNEL), {
        pages: [aMessagePage([original])],
        pageParams: [undefined],
      })
      const history = holdHistoryFetch(queryClient, CHANNEL)
      renderHookWithProviders(() => useChannelSocket('token', WORKSPACE, CHANNEL, ADA), { queryClient })
      const socket = latestSocket()
      act(() => socket.serverConnect())
      const edited = { ...original, body: 'standup at five', version: original.version + 1 }

      act(() => socket.serverEmit('message_edited', edited))
      await history.answer(aMessagePage([original]))

      expect(historyItems(queryClient, CHANNEL)).toEqual([edited])
    })

    it('forgets the joined channel when the connection drops', async () => {
      renderHookWithProviders(() => useChannelSocket('token', WORKSPACE, CHANNEL, ADA))
      const socket = latestSocket()
      const joins = holdJoins(socket)
      act(() => socket.serverConnect())
      await joins.reply({ ok: true })

      act(() => socket.serverDisconnect())

      expect(joinedChannel()).toBeNull()
    })
  })

  describe('read state', () => {
    const newer = messageIdAt(3)
    const older = messageIdAt(2)

    function seedChannel(queryClient: ReturnType<typeof createTestQueryClient>) {
      const channel = aChannel({ id: CHANNEL, unreadCount: 3 })
      queryClient.setQueryData<ChannelPage>(channelKeys.list(WORKSPACE), {
        items: [channel],
        nextCursor: null,
      })
      queryClient.setQueryData(channelKeys.detail(WORKSPACE, CHANNEL), channel)
      queryClient.setQueryData<InfiniteData<MessagePage>>(messageKeys.list(WORKSPACE, CHANNEL), {
        pages: [aMessagePage([aMessage({ id: newer }), aMessage({ id: older })])],
        pageParams: [undefined],
      })
    }

    const listChannel = (queryClient: ReturnType<typeof createTestQueryClient>) =>
      queryClient.getQueryData<ChannelPage>(channelKeys.list(WORKSPACE))?.items[0]
    const detailChannel = (queryClient: ReturnType<typeof createTestQueryClient>) =>
      queryClient.getQueryData<Channel>(channelKeys.detail(WORKSPACE, CHANNEL))
    const listInvalidated = (queryClient: ReturnType<typeof createTestQueryClient>) =>
      queryClient.getQueryState(channelKeys.list(WORKSPACE))?.isInvalidated

    function receipt(messageId: string, userId = ADA) {
      return { channelId: CHANNEL, userId, messageId }
    }

    it('refetches the channel list on every connect', () => {
      const queryClient = createTestQueryClient()
      seedChannel(queryClient)
      renderHookWithProviders(() => useChannelSocket('token', WORKSPACE, CHANNEL, ADA), {
        queryClient,
      })
      const socket = latestSocket()
      expect(listInvalidated(queryClient)).toBe(false)

      act(() => socket.serverConnect())
      expect(listInvalidated(queryClient)).toBe(true)

      // A fresh write clears the flag; a drop and a second connect set it again.
      seedChannel(queryClient)
      expect(listInvalidated(queryClient)).toBe(false)
      act(() => socket.serverDisconnect())
      act(() => socket.serverConnect())
      expect(listInvalidated(queryClient)).toBe(true)
    })

    it('applies the user’s own receipt to the list and the detail', () => {
      const queryClient = createTestQueryClient()
      seedChannel(queryClient)
      renderHookWithProviders(() => useChannelSocket('token', WORKSPACE, CHANNEL, ADA), {
        queryClient,
      })
      const socket = latestSocket()
      act(() => socket.serverConnect())
      seedChannel(queryClient) // clear the connect's invalidation

      act(() => socket.serverEmit('read_receipt_updated', receipt(newer)))

      expect(listChannel(queryClient)).toMatchObject({ lastReadId: newer, unreadCount: 0 })
      expect(detailChannel(queryClient)).toMatchObject({ lastReadId: newer, unreadCount: 0 })
      expect(listInvalidated(queryClient)).toBe(false)
    })

    it('refetches the list for a receipt older than the newest cached message', () => {
      const queryClient = createTestQueryClient()
      seedChannel(queryClient)
      renderHookWithProviders(() => useChannelSocket('token', WORKSPACE, CHANNEL, ADA), {
        queryClient,
      })
      const socket = latestSocket()
      act(() => socket.serverConnect())
      seedChannel(queryClient)

      act(() => socket.serverEmit('read_receipt_updated', receipt(older)))

      expect(listInvalidated(queryClient)).toBe(true)
      expect(listChannel(queryClient)).toMatchObject({ lastReadId: null, unreadCount: 3 })
    })

    it('ignores a receipt for another user', () => {
      const queryClient = createTestQueryClient()
      seedChannel(queryClient)
      renderHookWithProviders(() => useChannelSocket('token', WORKSPACE, CHANNEL, ADA), {
        queryClient,
      })
      const socket = latestSocket()
      act(() => socket.serverConnect())
      seedChannel(queryClient)

      act(() => socket.serverEmit('read_receipt_updated', receipt(newer, 'user-grace')))
      expect(listChannel(queryClient)).toMatchObject({ lastReadId: null, unreadCount: 3 })
      expect(listInvalidated(queryClient)).toBe(false)

      // The same receipt for the signed-in user is applied: the silence above
      // was the user check, not a socket that never delivers the event.
      act(() => socket.serverEmit('read_receipt_updated', receipt(newer)))
      expect(listChannel(queryClient)).toMatchObject({ lastReadId: newer, unreadCount: 0 })
    })
  })

  describe('reactions', () => {
    function seedOne(queryClient: ReturnType<typeof createTestQueryClient>, message: Message) {
      queryClient.setQueryData<InfiniteData<MessagePage>>(messageKeys.list(WORKSPACE, CHANNEL), {
        pages: [aMessagePage([message])],
        pageParams: [undefined],
      })
    }

    it('applies a reaction event to the cached message', () => {
      const queryClient = createTestQueryClient()
      const message = aMessage({ channelId: CHANNEL })
      seedOne(queryClient, message)

      renderHookWithProviders(() => useChannelSocket('token', WORKSPACE, CHANNEL, ADA), {
        queryClient,
      })
      const socket = latestSocket()

      act(() => socket.serverConnect())
      act(() =>
        socket.serverEmit('reaction_changed', {
          messageId: message.id,
          channelId: CHANNEL,
          emoji: 'tada',
          count: 2,
          userId: 'grace',
          reacted: true,
        }),
      )

      // Grace's `reacted`, not mine — the count is everyone's, the lit state is one person's.
      expect(historyItems(queryClient, CHANNEL)?.[0].reactions).toEqual([
        { emoji: 'tada', count: 2, reacted: false },
      ])
    })

    it('keeps a reaction that arrives while the history is being refetched', async () => {
      const queryClient = createTestQueryClient()
      const message = aMessage({ channelId: CHANNEL })
      seedOne(queryClient, message)
      const history = holdHistoryFetch(queryClient, CHANNEL)
      renderHookWithProviders(() => useChannelSocket('token', WORKSPACE, CHANNEL, ADA), {
        queryClient,
      })
      const socket = latestSocket()
      act(() => socket.serverConnect())

      act(() =>
        socket.serverEmit('reaction_changed', {
          messageId: message.id,
          channelId: CHANNEL,
          emoji: 'tada',
          count: 1,
          userId: 'grace',
          reacted: true,
        }),
      )
      // That fetch read the channel before the reaction existed.
      await history.answer(aMessagePage([message]))

      expect(historyItems(queryClient, CHANNEL)?.[0].reactions).toEqual([
        { emoji: 'tada', count: 1, reacted: false },
      ])
    })
  })
})
