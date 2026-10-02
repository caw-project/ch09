import type { InfiniteData, QueryClient } from '@tanstack/react-query'
import { act } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ProblemError } from '../../lib/api/client'
import type { Message, MessagePage } from '../../lib/api/messaging'
import { messaging, requests } from '../../test/api'
import { aMessage, aMessagePage } from '../../test/factories'
import { createTestQueryClient, renderHookWithProviders } from '../../test/render'
import { asSocket, FakeSocket } from '../../test/socket'
import {
  applyReaction,
  isPending,
  messageKeys,
  removeMessage,
  replaceMessage,
  upsertMessage,
  useSendMessage,
  useToggleReaction,
  type ReactionEvent,
} from './useMessages'

const WORKSPACE = 'workspace-1'
const CHANNEL = 'channel-1'
const ADA = 'user-ada'
const key = messageKeys.list(WORKSPACE, CHANNEL)

function seeded(...pages: MessagePage[]) {
  const queryClient = createTestQueryClient()
  queryClient.setQueryData<InfiniteData<MessagePage>>(key, {
    pages,
    pageParams: pages.map(() => undefined),
  })
  return queryClient
}

function pagesIn(queryClient: QueryClient) {
  return queryClient.getQueryData<InfiniteData<MessagePage>>(key)?.pages
}

function itemsIn(queryClient: QueryClient): Message[] {
  return (pagesIn(queryClient) ?? []).flatMap((page) => page.items)
}

describe('upsertMessage', () => {
  it('puts a new message at the head of the newest page', () => {
    const older = aMessage({ body: 'older' })
    const queryClient = seeded(aMessagePage([older], 'cursor-2'))
    const arrived = aMessage({ body: 'arrived' })

    upsertMessage(queryClient, key, arrived)

    expect(pagesIn(queryClient)?.[0].items).toEqual([arrived, older])
    // The cursor belongs to the page, and a live message must not reset it.
    expect(pagesIn(queryClient)?.[0].nextCursor).toBe('cursor-2')
  })

  it('replaces a message where it sits, on whichever page holds it', () => {
    const edited = aMessage({ body: 'before' })
    const newest = aMessagePage([aMessage({ body: 'newest' })], 'cursor-2')
    const queryClient = seeded(newest, aMessagePage([edited]))

    upsertMessage(queryClient, key, { ...edited, body: 'after', editedAt: '2026-09-15T10:00:00Z' })

    expect(pagesIn(queryClient)?.[0]).toEqual(newest)
    expect(pagesIn(queryClient)?.[1].items.map((m) => m.body)).toEqual(['after'])
  })

  it('does not render a message twice when its broadcast arrives again', () => {
    const message = aMessage()
    const queryClient = seeded(aMessagePage([]))

    upsertMessage(queryClient, key, message)
    upsertMessage(queryClient, key, message)

    expect(itemsIn(queryClient)).toEqual([message])
  })

  it('invents no history for a channel nothing has loaded', () => {
    const queryClient = createTestQueryClient()

    upsertMessage(queryClient, key, aMessage())

    expect(queryClient.getQueryData(key)).toBeUndefined()
  })

  it('ignores a reply, however it arrives, and still adds a top-level message', () => {
    // Decision 20: a reply written into history by any path is a leak (R3).
    const existing = aMessage({ body: 'existing' })
    const queryClient = seeded(aMessagePage([existing]))
    const reply = aMessage({ body: 'a reply', threadRootId: existing.id })
    const topLevel = aMessage({ body: 'top level' })

    upsertMessage(queryClient, key, reply)
    upsertMessage(queryClient, key, topLevel)

    expect(itemsIn(queryClient)).toEqual([topLevel, existing])
  })
})

describe('replaceMessage', () => {
  it('replaces a cached row where it sits', () => {
    const edited = aMessage({ body: 'before' })
    const queryClient = seeded(aMessagePage([aMessage({ body: 'newest' })], 'c2'), aMessagePage([edited]))

    replaceMessage(queryClient, key, { ...edited, body: 'after' })

    expect(pagesIn(queryClient)?.[1].items.map((m) => m.body)).toEqual(['after'])
  })

  it('adds nothing for an id that is not cached', () => {
    // Decision 28: an edit of a root nobody loaded must not become the newest message.
    const cached = aMessage({ body: 'cached' })
    const queryClient = seeded(aMessagePage([cached]))

    replaceMessage(queryClient, key, aMessage({ body: 'a stranger' }))
    expect(itemsIn(queryClient)).toEqual([cached])

    // The same call with a cached id replaces it: the silence above was the id check.
    replaceMessage(queryClient, key, { ...cached, body: 'edited' })
    expect(itemsIn(queryClient).map((m) => m.body)).toEqual(['edited'])
  })
})

describe('removeMessage', () => {
  it('drops the message from every page', () => {
    const doomed = aMessage()
    const kept = aMessage()
    const queryClient = seeded(aMessagePage([doomed, kept]))

    removeMessage(queryClient, key, doomed.id)

    expect(itemsIn(queryClient)).toEqual([kept])
  })

  it('leaves an uncached channel uncached', () => {
    const queryClient = createTestQueryClient()

    removeMessage(queryClient, key, 'anything')

    expect(queryClient.getQueryData(key)).toBeUndefined()
  })
})

describe('isPending', () => {
  it('is true only for a browser-made temp id', () => {
    expect(isPending(aMessage({ id: 'temp:1234' }))).toBe(true)
    expect(isPending(aMessage())).toBe(false)
  })
})

describe('useSendMessage', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  function renderSend(queryClient: QueryClient, socket: FakeSocket | null) {
    return renderHookWithProviders(
      () => useSendMessage(socket ? asSocket(socket) : null, WORKSPACE, CHANNEL, ADA),
      { queryClient },
    )
  }

  it('shows the message at once, then swaps in the confirmed one', async () => {
    const queryClient = seeded(aMessagePage([]))
    const socket = new FakeSocket('token')
    const confirmed = aMessage({ channelId: CHANNEL, authorId: ADA, body: 'lunch is at one' })
    let confirm: (ack: unknown) => void = () => undefined
    socket.onEmit('send_message', () => new Promise((resolve) => (confirm = resolve)))
    const { result } = renderSend(queryClient, socket)

    act(() => result.current.mutate('lunch is at one'))

    await vi.waitFor(() => expect(itemsIn(queryClient)).toHaveLength(1))
    const [pending] = itemsIn(queryClient)
    expect(isPending(pending)).toBe(true)
    expect(pending).toMatchObject({ body: 'lunch is at one', authorId: ADA, channelId: CHANNEL })
    expect(socket.emitted).toEqual([
      { event: 'send_message', args: [{ channelId: CHANNEL, body: 'lunch is at one' }] },
    ])

    await act(async () => confirm({ ok: true, data: confirmed }))

    await vi.waitFor(() => expect(itemsIn(queryClient)).toEqual([confirmed]))
  })

  it('shows a message once when its broadcast beats its acknowledgement', async () => {
    const queryClient = seeded(aMessagePage([]))
    const socket = new FakeSocket('token')
    const confirmed = aMessage({ channelId: CHANNEL, authorId: ADA, body: 'race' })
    let confirm: (ack: unknown) => void = () => undefined
    socket.onEmit('send_message', () => new Promise((resolve) => (confirm = resolve)))
    const { result } = renderSend(queryClient, socket)

    act(() => result.current.mutate('race'))
    await vi.waitFor(() => expect(itemsIn(queryClient)).toHaveLength(1))
    // What `useChannelSocket` does with `message_received`.
    upsertMessage(queryClient, key, confirmed)
    await act(async () => confirm({ ok: true, data: confirmed }))

    await vi.waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(itemsIn(queryClient)).toEqual([confirmed])
  })

  it('rolls a refused send back and keeps the server’s reason', async () => {
    const queryClient = seeded(aMessagePage([]))
    const socket = new FakeSocket('token')
    socket.onEmit('send_message', () => ({
      ok: false,
      problem: {
        status: 400,
        title: 'Validation error',
        detail: 'A message must be 8000 characters or fewer.',
        errors: { body: ['A message must be 8000 characters or fewer.'] },
      },
    }))
    const { result } = renderSend(queryClient, socket)

    act(() => result.current.mutate('a'.repeat(8001)))

    await vi.waitFor(() => expect(result.current.isError).toBe(true))
    expect(itemsIn(queryClient)).toEqual([])
    expect(result.current.error).toBeInstanceOf(ProblemError)
    expect((result.current.error as ProblemError).fieldError('body')).toBe(
      'A message must be 8000 characters or fewer.',
    )
  })

  it('rolls back within five seconds when no acknowledgement comes', async () => {
    vi.useFakeTimers()
    const queryClient = seeded(aMessagePage([]))
    const { result } = renderSend(queryClient, new FakeSocket('token'))

    act(() => result.current.mutate('into the void'))
    await act(() => vi.advanceTimersByTimeAsync(4_999))
    expect(itemsIn(queryClient)).toHaveLength(1)

    await act(() => vi.advanceTimersByTimeAsync(1))

    await vi.waitFor(() =>
      expect(result.current.error?.message).toBe(
        'The server did not confirm that message. Nothing was sent.',
      ),
    )
    expect(itemsIn(queryClient)).toEqual([])
  })

  it('refuses to send with no socket', async () => {
    const queryClient = seeded(aMessagePage([]))
    const { result } = renderSend(queryClient, null)

    act(() => result.current.mutate('hello'))

    await vi.waitFor(() =>
      expect(result.current.error?.message).toBe('Not connected. Try again in a moment.'),
    )
    expect(itemsIn(queryClient)).toEqual([])
  })
})

describe('applyReaction', () => {
  const MESSAGE = 'message-1'

  function event(overrides: Partial<ReactionEvent> = {}): ReactionEvent {
    return {
      messageId: MESSAGE,
      channelId: CHANNEL,
      emoji: 'tada',
      count: 1,
      userId: 'someone-else',
      reacted: true,
      ...overrides,
    }
  }

  it('sets the count on the message the event names', () => {
    const queryClient = seeded(aMessagePage([aMessage({ id: MESSAGE })]))

    applyReaction(queryClient, key, event({ count: 3 }), ADA)

    expect(itemsIn(queryClient)[0].reactions).toEqual([{ emoji: 'tada', count: 3, reacted: false }])
  })

  it('is idempotent, because the count is authoritative and not a delta', () => {
    // The person who clicked applies their own change three times: optimistically,
    // from the REST response, and from their own echo of the broadcast.
    const queryClient = seeded(aMessagePage([aMessage({ id: MESSAGE })]))

    applyReaction(queryClient, key, event({ count: 2 }), ADA)
    applyReaction(queryClient, key, event({ count: 2 }), ADA)
    applyReaction(queryClient, key, event({ count: 2 }), ADA)

    expect(itemsIn(queryClient)[0].reactions).toEqual([{ emoji: 'tada', count: 2, reacted: false }])
  })

  it('lights the chip only for the person who reacted', () => {
    const queryClient = seeded(aMessagePage([aMessage({ id: MESSAGE })]))

    applyReaction(queryClient, key, event({ userId: ADA, reacted: true }), ADA)

    expect(itemsIn(queryClient)[0].reactions[0].reacted).toBe(true)
  })

  it('leaves my own lit state alone when somebody else reacts', () => {
    const message = aMessage({
      id: MESSAGE,
      reactions: [{ emoji: 'tada', count: 1, reacted: true }],
    })
    const queryClient = seeded(aMessagePage([message]))

    applyReaction(queryClient, key, event({ count: 2, userId: 'grace', reacted: true }), ADA)

    expect(itemsIn(queryClient)[0].reactions).toEqual([{ emoji: 'tada', count: 2, reacted: true }])
  })

  it('drops the chip when the last reaction goes', () => {
    const message = aMessage({
      id: MESSAGE,
      reactions: [{ emoji: 'tada', count: 1, reacted: true }],
    })
    const queryClient = seeded(aMessagePage([message]))

    applyReaction(queryClient, key, event({ count: 0, userId: ADA, reacted: false }), ADA)

    expect(itemsIn(queryClient)[0].reactions).toEqual([])
  })

  it('keeps chips in allowlist order however they arrive', () => {
    const message = aMessage({
      id: MESSAGE,
      reactions: [{ emoji: 'heart', count: 1, reacted: false }],
    })
    const queryClient = seeded(aMessagePage([message]))

    applyReaction(queryClient, key, event({ emoji: 'check', count: 1 }), ADA)
    applyReaction(queryClient, key, event({ emoji: 'thumbsup', count: 1 }), ADA)

    expect(itemsIn(queryClient)[0].reactions.map((r) => r.emoji)).toEqual([
      'thumbsup',
      'heart',
      'check',
    ])
  })

  it('touches no other message', () => {
    const other = aMessage()
    const queryClient = seeded(aMessagePage([aMessage({ id: MESSAGE }), other]))

    applyReaction(queryClient, key, event(), ADA)

    expect(itemsIn(queryClient)[1]).toEqual(other)
  })

  it('invents no history for a channel nothing has loaded', () => {
    const queryClient = createTestQueryClient()

    applyReaction(queryClient, key, event(), ADA)

    expect(queryClient.getQueryData(key)).toBeUndefined()
  })
})

describe('useToggleReaction', () => {
  const MESSAGE = '0199a000-0000-7000-8000-00000000000a'

  function renderToggle(queryClient: QueryClient) {
    return renderHookWithProviders(() => useToggleReaction('token', WORKSPACE, CHANNEL, ADA), {
      queryClient,
    })
  }

  it('lights the chip before the server answers', async () => {
    const message = aMessage({ id: MESSAGE, channelId: CHANNEL })
    const queryClient = seeded(aMessagePage([message]))
    messaging.post('/api/v1/messages/{message_id}/reactions', () => ({
      ...message,
      reactions: [{ emoji: 'tada', count: 1, reacted: true }],
    }))
    const { result } = renderToggle(queryClient)

    act(() => result.current.mutate({ message, emoji: 'tada' }))

    // Before any response has come back, the optimistic write is already there.
    expect(itemsIn(queryClient)[0].reactions).toEqual([{ emoji: 'tada', count: 1, reacted: true }])

    await vi.waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(itemsIn(queryClient)[0].reactions).toEqual([{ emoji: 'tada', count: 1, reacted: true }])
  })

  it('removes when the chip is already lit', async () => {
    const message = aMessage({
      id: MESSAGE,
      channelId: CHANNEL,
      reactions: [{ emoji: 'tada', count: 1, reacted: true }],
    })
    const queryClient = seeded(aMessagePage([message]))
    messaging.delete('/api/v1/messages/{message_id}/reactions/{emoji}', () => ({
      ...message,
      reactions: [],
    }))
    const { result } = renderToggle(queryClient)

    act(() => result.current.mutate({ message, emoji: 'tada' }))

    await vi.waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(itemsIn(queryClient)[0].reactions).toEqual([])
    expect(requests().at(-1)?.method).toBe('DELETE')
  })

  it('puts the chip back when the server refuses', async () => {
    const message = aMessage({ id: MESSAGE, channelId: CHANNEL })
    const queryClient = seeded(aMessagePage([message]))
    messaging.problem('post', '/api/v1/messages/{message_id}/reactions', 409, {
      title: 'Conflict',
      detail: 'This message was deleted.',
    })
    const { result } = renderToggle(queryClient)

    act(() => result.current.mutate({ message, emoji: 'tada' }))

    await vi.waitFor(() => expect(result.current.isError).toBe(true))
    expect(itemsIn(queryClient)[0].reactions).toEqual([])
  })
})
