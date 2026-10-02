/**
 * The sender: one throttle per socket, the local write and its hold, and what
 * leaving does to a read still waiting in its window.
 *
 * `FakeSocket` plays the server through a `mark_read` responder. The session is
 * mocked at `snapshot` only, so a test can move the live workspace under a hook
 * without a real sign-in (plan decision 30); everything else is real.
 */

import type { QueryClient } from '@tanstack/react-query'
import { act } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Channel, ChannelPage } from '../../lib/api/messaging'
import { snapshot } from '../../lib/auth/session'
import { requests } from '../../test/api'
import { aChannel, aSession, messageIdAt } from '../../test/factories'
import { createTestQueryClient, renderHookWithProviders } from '../../test/render'
import { asSocket, FakeSocket } from '../../test/socket'
import { channelKeys } from './useChannels'
import { useMarkRead } from './useMarkRead'

vi.mock('../../lib/auth/session', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../lib/auth/session')>()),
  snapshot: vi.fn(() => ({ status: 'loading' })),
}))

const WS = 'workspace-1'
const A = 'channel-a'
const B = 'channel-b'
const m = messageIdAt

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  vi.mocked(snapshot).mockReturnValue({ status: 'loading' })
})

afterEach(() => {
  vi.useRealTimers()
})

function connectedSocket(): FakeSocket {
  const socket = new FakeSocket('token')
  socket.connected = true
  socket.onEmit('mark_read', () => ({ ok: true }))
  return socket
}

function seed(queryClient: QueryClient, channelId = A, overrides: Partial<Channel> = {}) {
  const channel = aChannel({ id: channelId, unreadCount: 3, ...overrides })
  queryClient.setQueryData<ChannelPage>(channelKeys.list(WS), { items: [channel], nextCursor: null })
  queryClient.setQueryData(channelKeys.detail(WS, channelId), channel)
}

const inList = (queryClient: QueryClient, id = A) =>
  queryClient.getQueryData<ChannelPage>(channelKeys.list(WS))?.items.find((c) => c.id === id)

const marks = (socket: FakeSocket) =>
  socket.emitted.filter((e) => e.event === 'mark_read').map((e) => e.args[0])

const mark = (channelId: string, messageId: string) => ({ channelId, messageId })

/** Move the fake clock, letting the acks and effects that follow run. */
const advance = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms))

/** A list fetch that lands at once with the old count, as an in-flight poll would. */
function pollLandsWithOldCount(queryClient: QueryClient) {
  return act(async () => {
    await queryClient.fetchQuery({
      queryKey: channelKeys.list(WS),
      queryFn: async (): Promise<ChannelPage> => ({
        items: [aChannel({ id: A, unreadCount: 3 })],
        nextCursor: null,
      }),
      staleTime: 0,
    })
  })
}

function renderMarkRead(socket: FakeSocket | null, queryClient = createTestQueryClient()) {
  let channelId = A
  let current = socket
  const view = renderHookWithProviders(
    () => useMarkRead(current ? asSocket(current) : null, WS, channelId),
    { queryClient },
  )
  return {
    ...view,
    queryClient,
    moveTo(next: string) {
      channelId = next
      view.rerender()
    },
    useSocket(next: FakeSocket) {
      current = next
      view.rerender()
    },
  }
}

describe('useMarkRead', () => {
  it('emits mark_read with the channel and the message', () => {
    const socket = connectedSocket()
    const { result } = renderMarkRead(socket)

    act(() => result.current.request(m(2)))

    expect(marks(socket)).toEqual([mark(A, m(2))])
  })

  it('writes the caches as it emits, with no request', () => {
    const socket = connectedSocket()
    const queryClient = createTestQueryClient()
    seed(queryClient)
    const { result } = renderMarkRead(socket, queryClient)

    act(() => result.current.request(m(2)))

    expect(inList(queryClient)).toMatchObject({ lastReadId: m(2), unreadCount: 0 })
    expect(queryClient.getQueryData<Channel>(channelKeys.detail(WS, A))).toMatchObject({
      lastReadId: m(2),
      unreadCount: 0,
    })
    expect(requests()).toHaveLength(0)
  })

  it('sends nothing when the cached marker is at or past the id, and sends when it is behind', () => {
    const socket = connectedSocket()
    const queryClient = createTestQueryClient()
    seed(queryClient, A, { lastReadId: m(5) })
    const { result } = renderMarkRead(socket, queryClient)

    act(() => result.current.request(m(5)))
    act(() => result.current.request(m(3)))
    expect(marks(socket)).toEqual([])

    act(() => result.current.request(m(6)))
    expect(marks(socket)).toEqual([mark(A, m(6))])
  })

  it('sends nothing while disconnected, and nothing on reconnect by itself', async () => {
    const socket = connectedSocket()
    socket.connected = false
    const { result } = renderMarkRead(socket)
    expect(result.current.connected).toBe(false)

    act(() => result.current.request(m(2)))
    act(() => socket.serverConnect())
    await advance(2000)

    expect(result.current.connected).toBe(true)
    expect(marks(socket)).toEqual([])

    // Connected now, the same hook sends: the silence above was the connection.
    act(() => result.current.request(m(3)))
    expect(marks(socket)).toEqual([mark(A, m(3))])
  })

  it('follows the socket’s disconnect', () => {
    const socket = connectedSocket()
    const { result } = renderMarkRead(socket)
    expect(result.current.connected).toBe(true)

    act(() => socket.serverDisconnect())

    expect(result.current.connected).toBe(false)
  })

  it('does not retry an error ack', async () => {
    const socket = connectedSocket()
    socket.onEmit('mark_read', () => ({ ok: false, problem: { status: 404 } }))
    const { result } = renderMarkRead(socket)

    act(() => result.current.request(m(2)))
    await advance(2000)

    expect(marks(socket)).toEqual([mark(A, m(2))])
  })

  it('releases the hold five seconds after a lost ack', async () => {
    // No responder: FakeSocket never answers, and a `timeout(ms).emit` then
    // fails with a timeout after `ms`, as a real socket does.
    const socket = new FakeSocket('token')
    socket.connected = true
    const queryClient = createTestQueryClient()
    seed(queryClient)
    const { result } = renderMarkRead(socket, queryClient)
    act(() => result.current.request(m(2)))

    await advance(4999)
    await pollLandsWithOldCount(queryClient)
    expect(inList(queryClient)).toMatchObject({ lastReadId: m(2), unreadCount: 0 })

    await advance(2) // 5001 ms: the ack has timed out
    await pollLandsWithOldCount(queryClient)
    expect(inList(queryClient)).toMatchObject({ lastReadId: null, unreadCount: 3 })
  })

  it('holds the write against an old fetch until the ack, and takes fetches as they come after it', async () => {
    const socket = connectedSocket()
    let ack!: (value: unknown) => void
    socket.onEmit('mark_read', () => new Promise((resolve) => (ack = resolve)))
    const queryClient = createTestQueryClient()
    seed(queryClient)
    const { result } = renderMarkRead(socket, queryClient)
    act(() => result.current.request(m(2)))

    await pollLandsWithOldCount(queryClient)
    expect(inList(queryClient)).toMatchObject({ unreadCount: 0 })

    await act(async () => ack({ ok: true }))
    await pollLandsWithOldCount(queryClient)
    expect(inList(queryClient)).toMatchObject({ unreadCount: 3 })
  })

  it('keeps the hold on an un-acked read when the hook unmounts, until the ack', async () => {
    // Leaving a channel unmounts its list; the badge must not come back from a
    // fetch that began before the server committed the marker.
    const socket = connectedSocket()
    let ack!: (value: unknown) => void
    socket.onEmit('mark_read', () => new Promise((resolve) => (ack = resolve)))
    const queryClient = createTestQueryClient()
    seed(queryClient)
    const hook = renderMarkRead(socket, queryClient)
    act(() => hook.result.current.request(m(2)))
    expect(marks(socket)).toEqual([mark(A, m(2))])

    hook.unmount()
    await pollLandsWithOldCount(queryClient)
    expect(inList(queryClient)).toMatchObject({ lastReadId: m(2), unreadCount: 0 })

    // Positive half: the ack still releases it, and fetches are taken after.
    await act(async () => ack({ ok: true }))
    await pollLandsWithOldCount(queryClient)
    expect(inList(queryClient)).toMatchObject({ lastReadId: null, unreadCount: 3 })
  })

  it('keeps the hold on a read flushed by the unmount, until its ack', async () => {
    const socket = connectedSocket()
    const acks: Array<(value: unknown) => void> = []
    socket.onEmit('mark_read', () => new Promise((resolve) => acks.push(resolve)))
    const queryClient = createTestQueryClient()
    seed(queryClient)
    const hook = renderMarkRead(socket, queryClient)
    act(() => hook.result.current.request(m(2)))
    await act(async () => acks[0]({ ok: true }))
    act(() => hook.result.current.request(m(3))) // inside the window: held
    expect(marks(socket)).toEqual([mark(A, m(2))])

    hook.unmount() // flushes m3, un-acked
    expect(marks(socket)).toEqual([mark(A, m(2)), mark(A, m(3))])
    await pollLandsWithOldCount(queryClient)
    expect(inList(queryClient)).toMatchObject({ lastReadId: m(3), unreadCount: 0 })

    await act(async () => acks[1]({ ok: true }))
    await pollLandsWithOldCount(queryClient)
    expect(inList(queryClient)).toMatchObject({ lastReadId: null, unreadCount: 3 })
  })

  it('sends a read held in its window when the channel changes', () => {
    const socket = connectedSocket()
    const hook = renderMarkRead(socket)
    act(() => hook.result.current.request(m(2)))
    act(() => hook.result.current.request(m(3))) // inside the window: held
    expect(marks(socket)).toEqual([mark(A, m(2))])

    act(() => hook.moveTo(B))

    expect(marks(socket)).toEqual([mark(A, m(2)), mark(A, m(3))])
  })

  it('sends a read held in its window when the hook unmounts', () => {
    const socket = connectedSocket()
    const hook = renderMarkRead(socket)
    act(() => hook.result.current.request(m(2)))
    act(() => hook.result.current.request(m(3)))
    expect(marks(socket)).toEqual([mark(A, m(2))])

    hook.unmount()

    expect(marks(socket)).toEqual([mark(A, m(2)), mark(A, m(3))])
  })

  it('drops a read held in its window when the socket changes', async () => {
    const first = connectedSocket()
    const second = connectedSocket()
    const hook = renderMarkRead(first)
    act(() => hook.result.current.request(m(2)))
    act(() => hook.result.current.request(m(3)))

    act(() => hook.useSocket(second))
    await advance(2000)

    expect(marks(first)).toEqual([mark(A, m(2))])
    expect(marks(second)).toEqual([])

    // The new socket is live: only the held read was dropped.
    act(() => hook.result.current.request(m(4)))
    expect(marks(second)).toEqual([mark(A, m(4))])
  })

  it('drops a read held in its window on unmount once the session is in another workspace', async () => {
    // One socket, connected throughout: only the live workspace can stop the emit.
    const socket = connectedSocket()
    const queryClient = createTestQueryClient()

    // Positive: in the same workspace, unmounting sends what was held.
    const first = renderMarkRead(socket, queryClient)
    act(() => first.result.current.request(m(2)))
    act(() => first.result.current.request(m(3)))
    first.unmount()
    expect(marks(socket)).toEqual([mark(A, m(2)), mark(A, m(3))])

    // The workspace switch: the module state names the new workspace before
    // React renders, so the unmount's flush finds the old socket still live.
    const second = renderMarkRead(socket, queryClient)
    act(() => second.result.current.request(m(4)))
    act(() => second.result.current.request(m(5)))
    vi.mocked(snapshot).mockReturnValue({
      status: 'signedIn',
      session: aSession({ activeWorkspaceId: 'another-workspace' }),
    })
    second.unmount()
    await advance(2000)

    expect(marks(socket)).toEqual([mark(A, m(2)), mark(A, m(3)), mark(A, m(4))])
  })
})
