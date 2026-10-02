/**
 * Routing the message events by `threadRootId` (R3, R8, decisions 15 and 28).
 *
 * A reply goes to its thread's cache and never into history; a top-level event
 * goes to history, and also to the thread the root opens. History takes a *new*
 * row only from `message_received` — an edit or delete of a message nobody
 * loaded must not make it the newest one.
 */

import type { InfiniteData, QueryClient } from '@tanstack/react-query'
import { act } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { messageKeys } from '../../features/channels/useMessages'
import { messaging, requests } from '../../test/api'
import { aMessage, aMessagePage, aThreadPage } from '../../test/factories'
import { createTestQueryClient, renderHookWithProviders } from '../../test/render'
import { latestSocket } from '../../test/socket'
import type { Message, MessagePage, ThreadPage } from '../api/messaging'
import { useChannelSocket } from './useChannelSocket'

const WORKSPACE = 'workspace-1'
const CHANNEL = 'channel-1'
const ADA = 'user-ada'
const GRACE = 'user-grace'

const root = aMessage({ channelId: CHANNEL, body: 'who is on call?', replyCount: 1 })
/**
 * `threadKeys.detail` from the plan (decision 15), as a literal: importing it from
 * a module that does not exist yet would fail every test in this file at load,
 * and most of them are about routing, not about that module.
 */
const threadKeyOf = (rootId: string) => ['messages', WORKSPACE, CHANNEL, 'thread', rootId] as const
const threadKey = threadKeyOf(root.id)
const historyKey = messageKeys.list(WORKSPACE, CHANNEL)

function reply(overrides: Partial<Message> = {}): Message {
  return aMessage({ channelId: CHANNEL, threadRootId: root.id, ...overrides })
}

function seedHistory(queryClient: QueryClient, ...items: Message[]) {
  queryClient.setQueryData<InfiniteData<MessagePage>>(historyKey, {
    pages: [aMessagePage(items)],
    pageParams: [undefined],
  })
}

function seedThread(queryClient: QueryClient, ...items: Message[]) {
  queryClient.setQueryData<InfiniteData<ThreadPage>>(threadKey, {
    pages: [aThreadPage(root, items)],
    pageParams: [undefined],
  })
}

const history = (queryClient: QueryClient) =>
  queryClient.getQueryData<InfiniteData<MessagePage>>(historyKey)?.pages[0].items
const thread = (queryClient: QueryClient) =>
  queryClient.getQueryData<InfiniteData<ThreadPage>>(threadKey)?.pages[0]

function connected(queryClient: QueryClient) {
  renderHookWithProviders(() => useChannelSocket('token', WORKSPACE, CHANNEL, ADA), {
    queryClient,
  })
  const socket = latestSocket()
  act(() => socket.serverConnect())
  return socket
}

function reactionOn(message: Message, overrides: Record<string, unknown> = {}) {
  return {
    messageId: message.id,
    channelId: CHANNEL,
    emoji: 'tada',
    count: 1,
    userId: GRACE,
    reacted: true,
    threadRootId: message.threadRootId,
    ...overrides,
  }
}

/** Holds a thread fetch back, as `holdHistoryFetch` does for history. */
function holdThreadFetch(queryClient: QueryClient) {
  let release!: (page: ThreadPage) => void
  const response = new Promise<ThreadPage>((resolve) => {
    release = resolve
  })
  const done = queryClient.fetchInfiniteQuery({
    queryKey: threadKey,
    queryFn: () => response,
    initialPageParam: undefined as string | undefined,
  })
  return {
    async answer(page: ThreadPage) {
      await act(async () => {
        release(page)
        await done
      })
    },
  }
}

describe('useChannelSocket — threads', () => {
  it('a reply event goes to its thread and never into history', () => {
    const queryClient = createTestQueryClient()
    const topLevel = aMessage({ channelId: CHANNEL, body: 'a top-level message' })
    seedHistory(queryClient, topLevel)
    seedThread(queryClient)
    const socket = connected(queryClient)
    const answer = reply({ body: 'I am' })

    act(() => socket.serverEmit('message_received', answer))

    expect(thread(queryClient)?.items).toEqual([answer])
    expect(history(queryClient)).toEqual([topLevel])
  })

  it('a top-level event still goes to history — the routing is by threadRootId, not a blanket drop', () => {
    const queryClient = createTestQueryClient()
    seedHistory(queryClient)
    const socket = connected(queryClient)
    const arrived = aMessage({ channelId: CHANNEL, body: 'hello' })

    act(() => socket.serverEmit('message_received', arrived))

    expect(history(queryClient)).toEqual([arrived])
  })

  it('a reply for an uncached thread creates no entry and leaves history alone', () => {
    const queryClient = createTestQueryClient()
    const topLevel = aMessage({ channelId: CHANNEL })
    seedHistory(queryClient, topLevel)
    const openRoot = aMessage({ channelId: CHANNEL })
    const openKey = threadKeyOf(openRoot.id)
    queryClient.setQueryData<InfiniteData<ThreadPage>>(openKey, {
      pages: [aThreadPage(openRoot, [])],
      pageParams: [undefined],
    })
    const socket = connected(queryClient)

    // Positive half: a reply to the cached thread lands there.
    const landed = aMessage({ channelId: CHANNEL, threadRootId: openRoot.id })
    act(() => socket.serverEmit('message_received', landed))
    expect(queryClient.getQueryData<InfiniteData<ThreadPage>>(openKey)?.pages[0].items).toEqual([
      landed,
    ])

    act(() => socket.serverEmit('message_received', reply({ body: 'to nobody' })))

    expect(queryClient.getQueryData(threadKey)).toBeUndefined()
    expect(history(queryClient)).toEqual([topLevel])
  })

  it('edits and deletes of a reply reach the open thread', () => {
    const queryClient = createTestQueryClient()
    const topLevel = aMessage({ channelId: CHANNEL })
    const answer = reply({ body: 'I am' })
    seedHistory(queryClient, topLevel)
    seedThread(queryClient, answer)
    const socket = connected(queryClient)

    act(() => socket.serverEmit('message_edited', { ...answer, body: 'I am, until nine' }))
    expect(thread(queryClient)?.items[0].body).toBe('I am, until nine')

    act(() =>
      socket.serverEmit('message_deleted', {
        ...answer,
        body: '',
        deletedAt: '2026-09-15T10:00:00Z',
      }),
    )
    expect(thread(queryClient)?.items[0]).toMatchObject({
      id: answer.id,
      deletedAt: '2026-09-15T10:00:00Z',
    })
    expect(history(queryClient)).toEqual([topLevel])
  })

  it('an edit of a root reaches history and the panel’s root', () => {
    const queryClient = createTestQueryClient()
    seedHistory(queryClient, root)
    seedThread(queryClient)
    const socket = connected(queryClient)

    act(() => socket.serverEmit('message_edited', { ...root, body: 'who is on call this week?' }))

    expect(history(queryClient)?.[0].body).toBe('who is on call this week?')
    expect(thread(queryClient)?.root.body).toBe('who is on call this week?')
  })

  it('an edit of a root not in loaded history reaches the panel and leaves history unchanged', () => {
    const queryClient = createTestQueryClient()
    const other = aMessage({ channelId: CHANNEL, body: 'the only thing loaded' })
    seedHistory(queryClient, other)
    seedThread(queryClient)
    const socket = connected(queryClient)

    act(() => socket.serverEmit('message_edited', { ...root, body: 'who is on call this week?' }))

    expect(history(queryClient)).toEqual([other])
    expect(thread(queryClient)?.root.body).toBe('who is on call this week?')
  })

  it('a reaction on a reply reaches the open thread', () => {
    const queryClient = createTestQueryClient()
    const answer = reply({ body: 'I am' })
    const topLevel = aMessage({ channelId: CHANNEL })
    seedHistory(queryClient, topLevel)
    seedThread(queryClient, answer)
    const socket = connected(queryClient)

    act(() => socket.serverEmit('reaction_changed', reactionOn(answer, { count: 2 })))

    expect(thread(queryClient)?.items[0].reactions).toEqual([
      { emoji: 'tada', count: 2, reacted: false },
    ])
    expect(history(queryClient)).toEqual([topLevel])
  })

  it('another user’s reaction on the root reaches history and the panel’s root', () => {
    const queryClient = createTestQueryClient()
    seedHistory(queryClient, root)
    seedThread(queryClient)
    const socket = connected(queryClient)

    act(() => socket.serverEmit('reaction_changed', reactionOn(root, { threadRootId: null })))

    const shown = [{ emoji: 'tada', count: 1, reacted: false }]
    expect(history(queryClient)?.[0].reactions).toEqual(shown)
    expect(thread(queryClient)?.root.reactions).toEqual(shown)
  })

  it('thread_summary_changed sets, never adds', () => {
    const queryClient = createTestQueryClient()
    seedHistory(queryClient, { ...root, replyCount: 0 })
    seedThread(queryClient)
    const socket = connected(queryClient)
    const summary = (replyCount: number, lastReplyAt: string | null) => ({
      channelId: CHANNEL,
      rootId: root.id,
      replyCount,
      lastReplyAt,
    })

    act(() => socket.serverEmit('thread_summary_changed', summary(2, '2026-09-15T10:00:00Z')))
    act(() => socket.serverEmit('thread_summary_changed', summary(2, '2026-09-15T10:00:00Z')))
    expect(history(queryClient)?.[0].replyCount).toBe(2)
    expect(thread(queryClient)?.root.replyCount).toBe(2)

    act(() => socket.serverEmit('thread_summary_changed', summary(1, '2026-09-15T09:30:00Z')))
    expect(history(queryClient)?.[0]).toMatchObject({
      replyCount: 1,
      lastReplyAt: '2026-09-15T09:30:00Z',
    })
  })

  it('a reply arriving during a thread refetch survives it', async () => {
    const queryClient = createTestQueryClient()
    seedThread(queryClient)
    const fetching = holdThreadFetch(queryClient)
    const socket = connected(queryClient)
    const answer = reply({ body: 'I am' })

    act(() => socket.serverEmit('message_received', answer))
    // That fetch read the thread before the reply existed.
    await fetching.answer(aThreadPage(root, []))

    expect(thread(queryClient)?.items).toEqual([answer])
  })

  it('a summary arriving during a history refetch survives it', async () => {
    const queryClient = createTestQueryClient()
    const unread = { ...root, replyCount: 0, lastReplyAt: null }
    seedHistory(queryClient, unread)
    let release!: (page: MessagePage) => void
    const response = new Promise<MessagePage>((resolve) => {
      release = resolve
    })
    const done = queryClient.fetchInfiniteQuery({
      queryKey: historyKey,
      queryFn: () => response,
      initialPageParam: undefined as string | undefined,
    })
    const socket = connected(queryClient)

    act(() =>
      socket.serverEmit('thread_summary_changed', {
        channelId: CHANNEL,
        rootId: root.id,
        replyCount: 1,
        lastReplyAt: '2026-09-15T10:00:00Z',
      }),
    )
    // Precondition: the event is applied at once, so the stale response below is
    // what would undo it.
    expect(history(queryClient)?.[0].replyCount).toBe(1)

    // That fetch read the root before the reply committed.
    await act(async () => {
      release(aMessagePage([unread]))
      await done
    })

    expect(history(queryClient)?.[0]).toMatchObject({
      replyCount: 1,
      lastReplyAt: '2026-09-15T10:00:00Z',
    })
  })

  it('a summary arriving during a thread refetch survives it on the panel’s root', async () => {
    const queryClient = createTestQueryClient()
    seedThread(queryClient)
    const fetching = holdThreadFetch(queryClient)
    const socket = connected(queryClient)

    act(() =>
      socket.serverEmit('thread_summary_changed', {
        channelId: CHANNEL,
        rootId: root.id,
        replyCount: 3,
        lastReplyAt: '2026-09-15T10:00:00Z',
      }),
    )
    expect(thread(queryClient)?.root.replyCount).toBe(3)

    await fetching.answer(aThreadPage({ ...root, replyCount: 0, lastReplyAt: null }, []))

    expect(thread(queryClient)?.root).toMatchObject({
      replyCount: 3,
      lastReplyAt: '2026-09-15T10:00:00Z',
    })
  })

  it('the join ack refetches the open thread', async () => {
    // Imported here, not at the top, so the file's other tests load without it
    // before the module exists; a variable path keeps Vite from resolving it at
    // transform time.
    const modulePath = '../../features/threads/useThread'
    const { useThread } = (await import(/* @vite-ignore */ modulePath)) as {
      useThread: typeof import('../../features/threads/useThread').useThread
    }
    messaging.get('/api/v1/messages/{message_id}/thread', aThreadPage(root, []))
    const queryClient = createTestQueryClient()
    const { result } = renderHookWithProviders(
      () => {
        useChannelSocket('token', WORKSPACE, CHANNEL, ADA)
        return useThread('token', WORKSPACE, CHANNEL, root.id)
      },
      { queryClient },
    )
    const socket = latestSocket()
    socket.onEmit('join_channel', () => ({ ok: true }))
    const gets = () => requests().filter((r) => r.url.pathname.endsWith('/thread')).length
    await vi.waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(gets()).toBe(1)

    act(() => socket.serverConnect())

    // The prefix invalidation reaches the nested thread key (decision 15).
    await vi.waitFor(() => expect(gets()).toBe(2))
  })
})
