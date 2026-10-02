/**
 * The thread's data layer: one infinite query per root, a send that shows at
 * once and settles once, and the panel's edit, delete and reaction writers
 * (R2, R5, R9, decision 28).
 *
 * The thread GET is stubbed at the network edge, so `openapi-fetch` and TanStack
 * Query run for real. The cache is read back through `threadKeys.detail`.
 */

import type { InfiniteData, QueryClient } from '@tanstack/react-query'
import { act } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ProblemError } from '../../lib/api/client'
import type { Message, MessagePage, ThreadPage } from '../../lib/api/messaging'
import { messaging, requests } from '../../test/api'
import { aMessage, aMessagePage, aThreadPage } from '../../test/factories'
import { createTestQueryClient, renderHookWithProviders } from '../../test/render'
import { asSocket, FakeSocket } from '../../test/socket'
import { isPending, messageKeys } from '../channels/useMessages'
import { threadKeys, upsertThreadMessage } from './threadCache'
import { useSendReply, useThread, useThreadActions } from './useThread'

const WORKSPACE = 'workspace-1'
const CHANNEL = 'channel-1'
const ADA = 'user-ada'

const root = aMessage({ channelId: CHANNEL, authorId: ADA, body: 'who is on call?', replyCount: 2 })
const key = threadKeys.detail(WORKSPACE, CHANNEL, root.id)
const historyKey = messageKeys.list(WORKSPACE, CHANNEL)

function reply(overrides: Partial<Message> = {}): Message {
  return aMessage({ channelId: CHANNEL, threadRootId: root.id, ...overrides })
}

function seeded(...items: Message[]): QueryClient {
  const queryClient = createTestQueryClient()
  queryClient.setQueryData<InfiniteData<ThreadPage>>(key, {
    pages: [aThreadPage(root, items)],
    pageParams: [undefined],
  })
  return queryClient
}

const cached = (queryClient: QueryClient, k: readonly unknown[] = key) =>
  queryClient.getQueryData<InfiniteData<ThreadPage>>(k)?.pages
const repliesIn = (queryClient: QueryClient) =>
  (cached(queryClient) ?? []).flatMap((page) => page.items)
const historyItems = (queryClient: QueryClient) =>
  queryClient.getQueryData<InfiniteData<MessagePage>>(historyKey)?.pages.flatMap((p) => p.items)

function renderThread(queryClient: QueryClient, rootId: string = root.id) {
  return renderHookWithProviders(() => useThread('token', WORKSPACE, CHANNEL, rootId), {
    queryClient,
  })
}

describe('useThread', () => {
  it('keeps the root apart and shows the replies oldest first', async () => {
    const older = reply({ body: 'older' })
    const newer = reply({ body: 'newer' })
    // The wire is newest first; the DOM reads oldest first.
    messaging.get('/api/v1/messages/{message_id}/thread', aThreadPage(root, [newer, older]))

    const { result } = renderThread(createTestQueryClient())

    await vi.waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.root).toEqual(root)
    expect(result.current.data?.replies.map((m) => m.body)).toEqual(['older', 'newer'])
  })

  it('loads older replies with the cursor', async () => {
    const [newest, middle, oldest] = ['newest', 'middle', 'oldest'].map((body) => reply({ body }))
    messaging.get('/api/v1/messages/{message_id}/thread', ({ request }) =>
      new URL(request.url).searchParams.get('cursor') === 'older'
        ? aThreadPage(root, [oldest])
        : aThreadPage(root, [newest, middle], 'older'),
    )
    const { result } = renderThread(createTestQueryClient())
    await vi.waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.hasNextPage).toBe(true)

    await act(() => result.current.fetchNextPage())

    await vi.waitFor(() =>
      expect(result.current.data?.replies.map((m) => m.body)).toEqual([
        'oldest',
        'middle',
        'newest',
      ]),
    )
    expect(requests().map((r) => r.url.searchParams.get('cursor'))).toEqual([null, 'older'])
    expect(result.current.hasNextPage).toBe(false)
  })

  it('a fetch for thread A that lands after switching to B stays in A', async () => {
    const rootB = aMessage({ channelId: CHANNEL, body: 'a different thread' })
    const answerA = reply({ body: 'for A' })
    const answerB = aMessage({ channelId: CHANNEL, threadRootId: rootB.id, body: 'for B' })
    let releaseA!: () => void
    const heldA = new Promise<void>((resolve) => (releaseA = resolve))
    messaging.get('/api/v1/messages/{message_id}/thread', async ({ params }) => {
      if (params.message_id === root.id) {
        await heldA
        return aThreadPage(root, [answerA])
      }
      return aThreadPage(rootB, [answerB])
    })
    const queryClient = createTestQueryClient()
    let shown = root.id
    const { result, rerender } = renderHookWithProviders(
      () => useThread('token', WORKSPACE, CHANNEL, shown),
      { queryClient },
    )

    shown = rootB.id
    rerender()
    await vi.waitFor(() => expect(result.current.data?.root.id).toBe(rootB.id))
    await act(async () => {
      releaseA()
      await new Promise((resolve) => setTimeout(resolve, 20))
    })

    expect(result.current.data?.replies.map((m) => m.body)).toEqual(['for B'])
    const landedInA = cached(queryClient, key)?.flatMap((page) => page.items)
    expect(landedInA?.map((m) => m.body)).toEqual(['for A'])
    const inB = cached(queryClient, threadKeys.detail(WORKSPACE, CHANNEL, rootB.id))
    expect(inB?.flatMap((page) => page.items).map((m) => m.body)).toEqual(['for B'])
  })

  it('shows a cached thread at once on reopen and refetches it; a reply made meanwhile appears', async () => {
    const first = reply({ body: 'first' })
    const queryClient = seeded(first)
    const madeWhileClosed = reply({ body: 'made while it was closed' })
    messaging.get(
      '/api/v1/messages/{message_id}/thread',
      aThreadPage(root, [madeWhileClosed, first]),
    )

    const { result } = renderThread(queryClient)

    // Before any response: the cache, at once.
    expect(result.current.data?.replies.map((m) => m.body)).toEqual(['first'])
    await vi.waitFor(() =>
      expect(result.current.data?.replies.map((m) => m.body)).toEqual([
        'first',
        'made while it was closed',
      ]),
    )
    expect(requests()).toHaveLength(1)
  })
})

describe('useSendReply', () => {
  const sends = (socket: FakeSocket) => socket.emitted.filter((e) => e.event === 'send_message')

  function renderSend(queryClient: QueryClient, socket: FakeSocket | null) {
    return renderHookWithProviders(
      () => useSendReply(socket ? asSocket(socket) : null, WORKSPACE, CHANNEL, root.id, ADA),
      { queryClient },
    )
  }

  /** A send whose ack the test releases itself. */
  function heldSend() {
    const socket = new FakeSocket('token')
    let confirm: (ack: unknown) => void = () => undefined
    socket.onEmit('send_message', () => new Promise((resolve) => (confirm = resolve)))
    return { socket, confirm: (ack: unknown) => confirm(ack) }
  }

  const confirmed = reply({ authorId: ADA, body: 'I am' })

  it('shows the reply at once as a temp: row, with the root’s count unchanged', async () => {
    const queryClient = seeded()
    const { socket } = heldSend()
    const { result } = renderSend(queryClient, socket)

    act(() => result.current.mutate('I am'))

    await vi.waitFor(() => expect(repliesIn(queryClient)).toHaveLength(1))
    const [pending] = repliesIn(queryClient)
    expect(isPending(pending)).toBe(true)
    expect(pending).toMatchObject({ body: 'I am', authorId: ADA, threadRootId: root.id })
    // No optimistic count bump: the server's summary is the only writer of it.
    expect(cached(queryClient)?.[0].root.replyCount).toBe(2)
  })

  it('send_message carries channelId, body and threadRootId', async () => {
    const { socket } = heldSend()
    const { result } = renderSend(seeded(), socket)

    act(() => result.current.mutate('I am'))

    await vi.waitFor(() => expect(sends(socket)).toHaveLength(1))
    expect(sends(socket)[0].args).toEqual([{ channelId: CHANNEL, body: 'I am', threadRootId: root.id }])
  })

  it('shows once when the ack comes first and the echo second', async () => {
    const queryClient = seeded()
    const { socket, confirm } = heldSend()
    const { result } = renderSend(queryClient, socket)
    act(() => result.current.mutate('I am'))
    await vi.waitFor(() => expect(repliesIn(queryClient)).toHaveLength(1))

    await act(async () => confirm({ ok: true, data: confirmed }))
    await vi.waitFor(() => expect(result.current.isSuccess).toBe(true))
    // What `useChannelSocket` does with `message_received`.
    act(() => upsertThreadMessage(queryClient, key, confirmed))

    expect(repliesIn(queryClient)).toEqual([confirmed])
  })

  it('shows once when the echo comes first and the ack second', async () => {
    const queryClient = seeded()
    const { socket, confirm } = heldSend()
    const { result } = renderSend(queryClient, socket)
    act(() => result.current.mutate('I am'))
    await vi.waitFor(() => expect(repliesIn(queryClient)).toHaveLength(1))

    act(() => upsertThreadMessage(queryClient, key, confirmed))
    await act(async () => confirm({ ok: true, data: confirmed }))

    await vi.waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(repliesIn(queryClient)).toEqual([confirmed])
  })

  it('rolls a refused send back and keeps the server’s reason', async () => {
    const queryClient = seeded()
    const socket = new FakeSocket('token')
    socket.onEmit('send_message', () => ({
      ok: false,
      problem: { status: 404, title: 'Not found', detail: 'No such thread.' },
    }))
    const { result } = renderSend(queryClient, socket)

    act(() => result.current.mutate('I am'))

    await vi.waitFor(() => expect(result.current.isError).toBe(true))
    expect(repliesIn(queryClient)).toEqual([])
    expect(result.current.error).toBeInstanceOf(ProblemError)
    expect(result.current.error?.message).toContain('No such thread.')
  })
})

describe('useThreadActions', () => {
  function renderActions(queryClient: QueryClient) {
    return renderHookWithProviders(
      () => useThreadActions('token', WORKSPACE, CHANNEL, root.id, ADA),
      { queryClient },
    )
  }

  it('deleting a reply tombstones it in the thread and leaves history alone', async () => {
    const answer = reply({ authorId: ADA, body: 'oops' })
    const queryClient = seeded(answer)
    const topLevel = aMessage({ channelId: CHANNEL })
    queryClient.setQueryData(historyKey, {
      pages: [aMessagePage([topLevel])],
      pageParams: [undefined],
    })
    messaging.delete('/api/v1/messages/{message_id}', {
      ...answer,
      body: '',
      deletedAt: '2026-09-15T10:00:00Z',
    })
    const { result } = renderActions(queryClient)

    act(() => result.current.remove.mutate(answer.id))

    await vi.waitFor(() => expect(result.current.remove.isSuccess).toBe(true))
    expect(repliesIn(queryClient)[0]).toMatchObject({
      id: answer.id,
      deletedAt: '2026-09-15T10:00:00Z',
    })
    expect(historyItems(queryClient)).toEqual([topLevel])
  })

  it('reacting on the root writes the thread’s root and the history’s', async () => {
    const queryClient = seeded(reply())
    queryClient.setQueryData(historyKey, {
      pages: [aMessagePage([root])],
      pageParams: [undefined],
    })
    const reacted = { ...root, reactions: [{ emoji: 'tada', count: 1, reacted: true }] }
    messaging.post('/api/v1/messages/{message_id}/reactions', reacted)
    const { result } = renderActions(queryClient)

    act(() => result.current.toggleReaction.mutate({ message: root, emoji: 'tada' }))

    await vi.waitFor(() => expect(result.current.toggleReaction.isSuccess).toBe(true))
    expect(cached(queryClient)?.[0].root.reactions).toEqual(reacted.reactions)
    expect(historyItems(queryClient)?.[0].reactions).toEqual(reacted.reactions)
  })

  it('editing a root not in loaded history leaves history unchanged', async () => {
    const other = aMessage({ channelId: CHANNEL, body: 'the only thing loaded' })
    const queryClient = seeded(reply())
    queryClient.setQueryData(historyKey, {
      pages: [aMessagePage([other])],
      pageParams: [undefined],
    })
    messaging.patch('/api/v1/messages/{message_id}', {
      ...root,
      body: 'who is on call this week?',
      version: root.version + 1,
    })
    const { result } = renderActions(queryClient)

    act(() =>
      result.current.edit.mutate({
        messageId: root.id,
        body: 'who is on call this week?',
        version: root.version,
      }),
    )

    await vi.waitFor(() => expect(result.current.edit.isSuccess).toBe(true))
    expect(cached(queryClient)?.[0].root.body).toBe('who is on call this week?')
    expect(historyItems(queryClient)).toEqual([other])
  })
})
