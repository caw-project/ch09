/**
 * When the open channel counts as read, and what the list asks for as a result.
 *
 * The rule is three inputs — the page is visible, the window is focused, the
 * list is measured within `STICK_THRESHOLD` of the bottom — and every one gets
 * flipped on its own with the other two true, after a stretch in which nothing
 * was sent. The negative half is anchored on the history having rendered; the
 * positive half is the same test's flip, so "nothing sent" can't pass because
 * nothing could ever be.
 *
 * jsdom has no layout, so every scroll dimension reads 0 and a list looks to be
 * at its bottom. A test that needs it elsewhere stubs geometry **before** the
 * list mounts (`layoutEveryElement`): the first measurement happens at mount.
 */

import { act, fireEvent, screen } from '@testing-library/react'
import type { QueryClient } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'

import type { Message } from '../../lib/api/messaging'
import { auth, messaging } from '../../test/api'
import {
  aMessage,
  aMessagePage,
  aWorkspaceMember,
  messageIdAt,
  WORKSPACE_ID,
} from '../../test/factories'
import { giveLayout, layoutEveryElement } from '../../test/layout'
import { setPageAttention } from '../../test/page'
import { renderWithProviders } from '../../test/render'
import { FakeSocket } from '../../test/socket'
import { useChatStore } from '../../stores/chat'
import { MessageList } from './MessageList'
import { messageKeys, upsertMessage } from './useMessages'

const CHANNEL = 'channel-general'
const ADA = 'user-ada'
const GRACE = 'user-grace'

const m = (n: number, overrides: Partial<Message> = {}) =>
  aMessage({
    id: messageIdAt(n),
    channelId: CHANNEL,
    authorId: GRACE,
    body: `message ${n}`,
    ...overrides,
  })

/** The history the server holds, given oldest-first and served newest-first. */
function stubHistory(...oldestFirst: Message[]) {
  messaging.get('/api/v1/channels/{channel_id}/messages', aMessagePage([...oldestFirst].reverse()))
}

function connectedSocket(): FakeSocket {
  const socket = new FakeSocket('token')
  socket.connected = true
  socket.onEmit('mark_read', () => ({ ok: true }))
  return socket
}

interface ListProps {
  lastReadId?: string | null
  channelFetching?: boolean
}

const list = ({ lastReadId = null, channelFetching = false }: ListProps = {}) => (
  <MessageList
    accessToken="token"
    workspaceId={WORKSPACE_ID}
    channelId={CHANNEL}
    userId={ADA}
    myRole={null}
    lastReadId={lastReadId}
    channelFetching={channelFetching}
  />
)

function renderList(socket: FakeSocket = connectedSocket(), props: ListProps = {}) {
  auth.members([aWorkspaceMember({ id: ADA }), aWorkspaceMember({ id: GRACE })])
  return { ...renderWithProviders(list(props), { socket }), socket }
}

const marks = (socket: FakeSocket) =>
  socket.emitted
    .filter((e) => e.event === 'mark_read')
    .map((e) => (e.args[0] as { messageId: string }).messageId)

const sleep = (ms: number) => act(() => new Promise<void>((resolve) => setTimeout(resolve, ms)))

/** Let effects and zero-delay timers run, so "nothing was sent" is checked late. */
const settle = () => sleep(20)

const scrollerElement = () => screen.getAllByRole('article')[0].parentElement as HTMLElement

const arrives = (queryClient: QueryClient, message: Message) =>
  act(() => upsertMessage(queryClient, messageKeys.list(WORKSPACE_ID, CHANNEL), message))

const BOTTOM = { clientHeight: 500, scrollHeight: 1200, scrollTop: 700, frozen: true }
const SCROLLED_BACK = { clientHeight: 500, scrollHeight: 1200, scrollTop: 300, frozen: true }

describe('MessageList — marking read', () => {
  it('marks read up to the newest message when visible, focused and at the bottom', async () => {
    setPageAttention({ visible: true, focused: true })
    stubHistory(m(1), m(2), m(3))
    const { socket } = renderList()
    await screen.findByText('message 3')

    await vi.waitFor(() => expect(marks(socket)).toEqual([messageIdAt(3)]))
    expect(socket.emitted.find((e) => e.event === 'mark_read')?.args).toEqual([
      { channelId: CHANNEL, messageId: messageIdAt(3) },
    ])
  })

  it('does not mark read while the tab is hidden, and does once it is visible', async () => {
    setPageAttention({ visible: false, focused: true })
    stubHistory(m(1), m(2))
    const { socket } = renderList()
    await screen.findByText('message 2')
    await settle()
    expect(marks(socket)).toEqual([])

    act(() => setPageAttention({ visible: true, focused: true }))

    await vi.waitFor(() => expect(marks(socket)).toEqual([messageIdAt(2)]))
  })

  it('does not mark read while the window is blurred, and does once it is focused', async () => {
    setPageAttention({ visible: true, focused: false })
    stubHistory(m(1), m(2))
    const { socket } = renderList()
    await screen.findByText('message 2')
    await settle()
    expect(marks(socket)).toEqual([])

    act(() => setPageAttention({ visible: true, focused: true }))

    await vi.waitFor(() => expect(marks(socket)).toEqual([messageIdAt(2)]))
  })

  it('does not mark read while scrolled back, and does once scrolled to the bottom', async () => {
    setPageAttention({ visible: true, focused: true })
    layoutEveryElement(SCROLLED_BACK)
    stubHistory(m(1), m(2))
    const { socket } = renderList()
    await screen.findByText('message 2')
    await settle()
    expect(marks(socket)).toEqual([])

    const scroller = scrollerElement()
    giveLayout(scroller, BOTTOM)
    fireEvent.scroll(scroller)

    await vi.waitFor(() => expect(marks(socket)).toEqual([messageIdAt(2)]))
  })

  it('counts 79px from the bottom as the bottom and 80px as not', async () => {
    setPageAttention({ visible: true, focused: true })
    // 1000 − 420 − 500 = 80 from the bottom. Frozen, so the list's own scroll
    // to its newest message can't move it.
    layoutEveryElement({ clientHeight: 500, scrollHeight: 1000, scrollTop: 420, frozen: true })
    stubHistory(m(1), m(2))
    const { socket } = renderList()
    await screen.findByText('message 2')
    const scroller = scrollerElement()

    fireEvent.scroll(scroller)
    await settle()
    expect(marks(socket)).toEqual([])

    giveLayout(scroller, { clientHeight: 500, scrollHeight: 1000, scrollTop: 421, frozen: true })
    fireEvent.scroll(scroller)

    await vi.waitFor(() => expect(marks(socket)).toEqual([messageIdAt(2)]))
  })

  it('marks read again when a message arrives while being read', async () => {
    setPageAttention({ visible: true, focused: true })
    stubHistory(m(1), m(2), m(3))
    const { socket, queryClient } = renderList()
    await screen.findByText('message 3')
    await vi.waitFor(() => expect(marks(socket)).toEqual([messageIdAt(3)]))

    // Real time: fake timers would stall TanStack's own notifications, which
    // are scheduled with `setTimeout`. The first send opened a one-second window,
    // so the second is held through the first part of it and sent at its end.
    arrives(queryClient, m(4))
    await screen.findByText('message 4')
    await sleep(400)
    expect(marks(socket)).toEqual([messageIdAt(3)])

    await vi.waitFor(() => expect(marks(socket)).toEqual([messageIdAt(3), messageIdAt(4)]), {
      timeout: 2000,
    })
  })

  it('targets the newest confirmed message, not a pending send', async () => {
    setPageAttention({ visible: true, focused: true })
    // A `temp:` id sorts after every UUIDv7, so a build that takes the last
    // row marks a message the server has never heard of.
    stubHistory(m(1), m(2), aMessage({ id: 'temp:5d5d', channelId: CHANNEL, authorId: ADA, body: 'sending' }))
    const { socket } = renderList()
    await screen.findByText('sending')

    await vi.waitFor(() => expect(marks(socket)).toEqual([messageIdAt(2)]))
  })

  it('sends nothing until the channel and its history have settled', async () => {
    setPageAttention({ visible: true, focused: true })
    stubHistory(m(1), m(2))
    const { socket, rerender } = renderList(connectedSocket(), { channelFetching: true })
    await screen.findByText('message 2')
    await settle()
    expect(marks(socket)).toEqual([])

    rerender(list({ channelFetching: false }))

    await vi.waitFor(() => expect(marks(socket)).toEqual([messageIdAt(2)]))
  })

  it('evaluates the rule again on reconnect and sends once', async () => {
    setPageAttention({ visible: true, focused: true })
    stubHistory(m(1), m(2), m(3))
    const socket = connectedSocket()
    socket.connected = false
    const { queryClient } = renderList(socket)
    await screen.findByText('message 3')
    arrives(queryClient, m(4))
    await screen.findByText('message 4')
    await settle()
    expect(marks(socket)).toEqual([])

    act(() => socket.serverConnect())

    await vi.waitFor(() => expect(marks(socket)).toEqual([messageIdAt(4)]))
    await settle()
    expect(marks(socket)).toEqual([messageIdAt(4)])
  })

  it('reports the channel as being read only while all three inputs hold', async () => {
    const reading = () => useChatStore.getState().readingChannelId
    setPageAttention({ visible: true, focused: true })
    stubHistory(m(1), m(2))
    const view = renderList()
    await screen.findByText('message 2')
    await vi.waitFor(() => expect(reading()).toBe(CHANNEL))

    act(() => setPageAttention({ visible: false, focused: true }))
    await vi.waitFor(() => expect(reading()).toBeNull())
    act(() => setPageAttention({ visible: true, focused: true }))
    await vi.waitFor(() => expect(reading()).toBe(CHANNEL))

    act(() => setPageAttention({ visible: true, focused: false }))
    await vi.waitFor(() => expect(reading()).toBeNull())
    act(() => setPageAttention({ visible: true, focused: true }))
    await vi.waitFor(() => expect(reading()).toBe(CHANNEL))

    const scroller = scrollerElement()
    giveLayout(scroller, SCROLLED_BACK)
    fireEvent.scroll(scroller)
    await vi.waitFor(() => expect(reading()).toBeNull())
    giveLayout(scroller, BOTTOM)
    fireEvent.scroll(scroller)
    await vi.waitFor(() => expect(reading()).toBe(CHANNEL))

    view.unmount()
    expect(reading()).toBeNull()
  })
})
