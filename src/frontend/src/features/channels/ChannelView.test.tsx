/**
 * The switch paths, through the real sidebar and the real channel view.
 *
 * Messaging is a small stateful stub — channels, their histories, and a
 * `mark_read` responder that moves the server's marker — so what the SPA reads
 * back after a switch is what a server would answer. A test can hold the detail
 * or the history response with a gate, to look at the screen between them.
 *
 * Real time throughout: fake timers would stall TanStack's notifications, which
 * are scheduled with `setTimeout`, and `userEvent` waits on timers too — so
 * clicks are `fireEvent.click`.
 */

import { act, fireEvent, screen } from '@testing-library/react'
import { useNavigate } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Channel, Message } from '../../lib/api/messaging'
import { snapshot } from '../../lib/auth/session'
import { auth, messaging, requests } from '../../test/api'
import {
  aChannel,
  aMessage,
  aMessagePage,
  aSession,
  aWorkspaceMember,
  messageIdAt,
  WORKSPACE_ID,
} from '../../test/factories'
import { giveLayout, layoutEveryElement, stubScrollIntoView } from '../../test/layout'
import { setPageAttention } from '../../test/page'
import { renderWithProviders } from '../../test/render'
import { FakeSocket } from '../../test/socket'
import { ChannelList } from './ChannelList'
import { ChannelView } from './ChannelView'
import { channelKeys } from './useChannels'
import { messageKeys, upsertMessage } from './useMessages'

vi.mock('../../lib/auth/session', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../lib/auth/session')>()),
  snapshot: vi.fn(() => ({ status: 'loading' })),
}))

const ADA = 'user-ada'
const GRACE = 'user-grace'
const GENERAL = 'channel-general'
const RANDOM = 'channel-random'

beforeEach(() => {
  vi.mocked(snapshot).mockReturnValue({ status: 'loading' })
})

/** Channel `GENERAL`'s messages are numbered 1…, `RANDOM`'s 11…, so ids never clash. */
const base = (channelId: string) => (channelId === GENERAL ? 0 : 10)
const idIn = (channelId: string, n: number) => messageIdAt(base(channelId) + n)
const bodyIn = (channelId: string, n: number) => `${channelId.replace('channel-', '')} ${n}`

function messageIn(channelId: string, n: number, overrides: Partial<Message> = {}): Message {
  return aMessage({
    id: idIn(channelId, n),
    channelId,
    authorId: GRACE,
    body: bodyIn(channelId, n),
    ...overrides,
  })
}

interface Gate {
  detail: Promise<unknown> | null
  history: Promise<unknown> | null
}

function deferred() {
  let release!: () => void
  const promise = new Promise<void>((resolve) => {
    release = resolve
  })
  return { promise, release }
}

/** What Messaging holds, and the stubs that serve it. */
function startServer(socket: FakeSocket) {
  const channels: Record<string, Channel> = {
    [GENERAL]: aChannel({ id: GENERAL, name: 'general' }),
    [RANDOM]: aChannel({ id: RANDOM, name: 'random' }),
  }
  const history: Record<string, Message[]> = {
    [GENERAL]: [messageIn(GENERAL, 1), messageIn(GENERAL, 2)],
    [RANDOM]: [messageIn(RANDOM, 1), messageIn(RANDOM, 2)],
  }
  const gate: Gate = { detail: null, history: null }
  const state = { applyReads: true }

  messaging.get('/api/v1/channels', () => ({
    items: Object.values(channels).map((c) => ({ ...c })),
    nextCursor: null,
  }))
  messaging.get('/api/v1/channels/{channel_id}', async ({ params }) => {
    await gate.detail
    return { ...channels[params.channel_id] }
  })
  messaging.get('/api/v1/channels/{channel_id}/messages', async ({ params }) => {
    await gate.history
    return aMessagePage([...history[params.channel_id]].reverse())
  })
  messaging.get('/api/v1/channels/{channel_id}/members', { items: [], nextCursor: null })
  auth.members([aWorkspaceMember({ id: ADA }), aWorkspaceMember({ id: GRACE })])

  socket.onEmit('mark_read', (payload: { channelId: string; messageId: string }) => {
    const channel = channels[payload.channelId]
    if (state.applyReads && (channel.lastReadId ?? '') < payload.messageId) {
      channel.lastReadId = payload.messageId
      channel.unreadCount = 0
    }
    return { ok: true }
  })

  return {
    channels,
    gate,
    state,
    /** Grace posts: it is in the channel's history, and unread for Ada. */
    post(channelId: string, n: number) {
      history[channelId].push(messageIn(channelId, n))
      channels[channelId].unreadCount += 1
    },
  }
}

function connectedSocket(): FakeSocket {
  const socket = new FakeSocket('token')
  socket.connected = true
  return socket
}

function Shell({ workspaceId = WORKSPACE_ID }: { workspaceId?: string }) {
  return (
    <>
      <ChannelList accessToken="token" workspaceId={workspaceId} />
      <ChannelView accessToken="token" workspaceId={workspaceId} userId={ADA} />
    </>
  )
}

function renderShell(startAt = GENERAL) {
  const socket = connectedSocket()
  const server = startServer(socket)
  const view = renderWithProviders(<Shell />, {
    route: `/c/${startAt}`,
    path: '/c/:channelId',
    socket,
  })
  return { ...view, socket, server }
}

const sleep = (ms: number) => act(() => new Promise<void>((resolve) => setTimeout(resolve, ms)))

const open = (name: RegExp) => fireEvent.click(screen.getByRole('link', { name }))

const marks = (socket: FakeSocket) =>
  socket.emitted
    .filter((e) => e.event === 'mark_read')
    .map((e) => e.args[0] as { channelId: string; messageId: string })

const markIds = (socket: FakeSocket) => marks(socket).map((mark) => mark.messageId)

const listGets = () =>
  requests().filter((r) => r.method === 'GET' && r.url.pathname === '/api/v1/channels').length
const historyGets = (channelId: string) =>
  requests().filter((r) => r.url.pathname === `/api/v1/channels/${channelId}/messages`).length

const readEverywhere = () => setPageAttention({ visible: true, focused: true })

/** Open `GENERAL`, then `RANDOM`, and come back to a state where both are cached. */
async function visitBoth() {
  await screen.findByText(bodyIn(GENERAL, 2))
  await screen.findByRole('link', { name: /random/ })
  open(/random/)
  await screen.findByText(bodyIn(RANDOM, 2))
  open(/general/)
  await screen.findByText(bodyIn(GENERAL, 2))
}

describe('ChannelView — switching channels', () => {
  it('refetches the channel list on every channel switch', async () => {
    renderShell()
    await screen.findByText(bodyIn(GENERAL, 2))
    await screen.findByRole('link', { name: /random/ })
    await sleep(100)
    const before = listGets()

    open(/random/)
    await screen.findByText(bodyIn(RANDOM, 2))
    await vi.waitFor(() => expect(listGets()).toBe(before + 1))
    await sleep(100)
    expect(listGets()).toBe(before + 1)

    open(/general/)
    await screen.findByText(bodyIn(GENERAL, 2))
    await vi.waitFor(() => expect(listGets()).toBe(before + 2))
  })

  it('reads a cached channel opened from another once its list is measured at the bottom', async () => {
    readEverywhere()
    // A real viewport: a fresh list starts at the top and scrolls itself to its
    // newest message, and it is only that measurement that makes it "at the bottom".
    layoutEveryElement({ clientHeight: 500, scrollHeight: 1200, scrollTop: 0 })
    const { socket, server } = renderShell()
    await screen.findByText(bodyIn(GENERAL, 2))
    await screen.findByRole('link', { name: /random/ })
    await vi.waitFor(() => expect(markIds(socket)).toEqual([idIn(GENERAL, 2)]))
    open(/random/)
    await vi.waitFor(() => expect(markIds(socket)).toEqual([idIn(GENERAL, 2), idIn(RANDOM, 2)]))

    // Something new in #random while Ada is elsewhere, then back to a cached #random.
    server.post(RANDOM, 3)
    open(/general/)
    await screen.findByText(bodyIn(GENERAL, 2))
    open(/random/)
    await screen.findByText(bodyIn(RANDOM, 3))

    await vi.waitFor(() =>
      expect(markIds(socket)).toEqual([idIn(GENERAL, 2), idIn(RANDOM, 2), idIn(RANDOM, 3)]),
    )
  })

  it('does not read a cached channel whose list sits mid-history, and reads it once scrolled down', async () => {
    readEverywhere()
    // Mid-history everywhere, and frozen: the list's own scroll to its newest
    // message cannot move it, so nothing here is at the bottom until a test says.
    layoutEveryElement({ clientHeight: 500, scrollHeight: 1200, scrollTop: 300, frozen: true })
    const { socket, server } = renderShell()
    await visitBoth()
    open(/random/)
    await screen.findByText(bodyIn(RANDOM, 2))
    server.post(RANDOM, 3)
    const before = historyGets(RANDOM)
    open(/general/)
    await screen.findByText(bodyIn(GENERAL, 2))
    open(/random/)
    // Anchor: #random's history refetch has landed and its new message shows.
    await screen.findByText(bodyIn(RANDOM, 3))
    expect(historyGets(RANDOM)).toBeGreaterThan(before)
    await sleep(100)
    expect(marks(socket)).toEqual([])

    const scroller = screen.getAllByRole('article')[0].parentElement as HTMLElement
    giveLayout(scroller, { clientHeight: 500, scrollHeight: 1200, scrollTop: 700, frozen: true })
    fireEvent.scroll(scroller)

    await vi.waitFor(() => expect(marks(socket)).toEqual([{ channelId: RANDOM, messageId: idIn(RANDOM, 3) }]))
  })

  it('sends a read waiting in its window when the user switches channel', async () => {
    readEverywhere()
    const { socket, queryClient } = renderShell()
    await screen.findByText(bodyIn(GENERAL, 2))
    await screen.findByRole('link', { name: /random/ })
    await vi.waitFor(() => expect(markIds(socket)).toEqual([idIn(GENERAL, 2)]))

    // A message arrives inside the window the first read opened: it is held.
    act(() => upsertMessage(queryClient, messageKeys.list(WORKSPACE_ID, GENERAL), messageIn(GENERAL, 3)))
    await screen.findByText(bodyIn(GENERAL, 3))
    expect(markIds(socket)).toEqual([idIn(GENERAL, 2)])

    open(/random/)

    // #general's held read goes out before #random's own.
    await vi.waitFor(() =>
      expect(markIds(socket)).toEqual([idIn(GENERAL, 2), idIn(GENERAL, 3), idIn(RANDOM, 2)]),
    )
  })

  it('sends a read waiting in its window on a channel switch, and drops one on a workspace switch', async () => {
    readEverywhere()
    const { socket, queryClient, server, rerender } = renderShell()
    await screen.findByText(bodyIn(GENERAL, 2))
    await screen.findByRole('link', { name: /random/ })
    await vi.waitFor(() => expect(markIds(socket)).toEqual([idIn(GENERAL, 2)]))
    act(() => upsertMessage(queryClient, messageKeys.list(WORKSPACE_ID, GENERAL), messageIn(GENERAL, 3)))
    await screen.findByText(bodyIn(GENERAL, 3))

    // The channel switch sends what was held — the positive half.
    open(/random/)
    await vi.waitFor(() =>
      expect(markIds(socket)).toEqual([idIn(GENERAL, 2), idIn(GENERAL, 3), idIn(RANDOM, 2)]),
    )

    // #random now holds a read of its own.
    act(() => upsertMessage(queryClient, messageKeys.list(WORKSPACE_ID, RANDOM), messageIn(RANDOM, 3)))
    await screen.findByText(bodyIn(RANDOM, 3))

    // The workspace switch, as `App` does it after `changeWorkspace`: the live
    // session names the new workspace first, then the tree renders with it. The
    // socket stays connected, as the old one is when the child's cleanup runs.
    // The new workspace's channel is held, so the view is left pending and the
    // list unmounts.
    vi.mocked(snapshot).mockReturnValue({
      status: 'signedIn',
      session: aSession({ activeWorkspaceId: 'another-workspace' }),
    })
    const held = deferred()
    server.gate.detail = held.promise
    rerender(<Shell workspaceId="another-workspace" />)
    await screen.findByText('Loading…')
    await sleep(1200)

    expect(markIds(socket)).toEqual([idIn(GENERAL, 2), idIn(GENERAL, 3), idIn(RANDOM, 2)])
    held.release()
  })

  it('does not show the badge of the channel being read, and shows it once the tab is hidden', async () => {
    readEverywhere()
    const { socket, server, queryClient } = renderShell()
    await screen.findByText(bodyIn(GENERAL, 2))
    await vi.waitFor(() => expect(markIds(socket)).toEqual([idIn(GENERAL, 2)]))
    await sleep(50)

    // A refetch lands with a count for the channel being read: Messaging has
    // not (in this stub) taken the read, so it still says 3.
    server.state.applyReads = false
    server.channels[GENERAL].lastReadId = null
    server.channels[GENERAL].unreadCount = 3
    const before = listGets()
    await act(() => queryClient.invalidateQueries({ queryKey: channelKeys.list(WORKSPACE_ID) }))
    await vi.waitFor(() => expect(listGets()).toBe(before + 1))
    await sleep(100)
    expect(screen.queryByLabelText('3 unread messages')).not.toBeInTheDocument()

    // The count was in the cache all along; the badge was held back by R1.
    act(() => setPageAttention({ visible: false, focused: true }))

    expect(await screen.findByLabelText('3 unread messages')).toBeInTheDocument()
  })
})

describe('ChannelView — jumping to a message', () => {
  function JumpShell({ to }: { to: string }) {
    const navigate = useNavigate()
    return (
      <>
        <button onClick={() => navigate(to)}>jump</button>
        <Shell />
      </>
    )
  }

  it('starts a jump into another channel once its history arrives', async () => {
    const spy = stubScrollIntoView()
    const socket = connectedSocket()
    const server = startServer(socket)
    const target = idIn(RANDOM, 2)
    renderWithProviders(<JumpShell to={`/c/${RANDOM}?message=${target}`} />, {
      route: `/c/${GENERAL}`,
      path: '/c/:channelId',
      socket,
    })
    await screen.findByText(bodyIn(GENERAL, 2))
    const held = deferred()
    server.gate.detail = held.promise

    fireEvent.click(screen.getByRole('button', { name: 'jump' }))

    // #random's detail is uncached, so the view waits behind "Loading…" and the
    // list — and the jump with it — does not exist yet.
    await screen.findByText('Loading…')
    await sleep(50)
    expect(spy).not.toHaveBeenCalled()

    held.release()

    await screen.findByText(bodyIn(RANDOM, 2))
    await vi.waitFor(() => expect(spy).toHaveBeenCalledTimes(1))
    expect(spy.mock.contexts[0]).toBe(
      document.querySelector(`article[data-message-id="${target}"]`),
    )
    expect(document.querySelector(`article[data-message-id="${target}"]`)).toHaveAttribute(
      'data-highlighted',
      'true',
    )
  })
})

describe('ChannelView — returning to a cached channel', () => {
  it.each(['detail', 'history'] as const)(
    'captures today’s marker only after both refetches (%s lands first)',
    async (first) => {
      // Nothing is read in this test until Ada is looking, so the marker the
      // server holds is the only one in play.
      setPageAttention({ visible: false, focused: false })
      const { socket, server } = renderShell()
      server.channels[GENERAL].lastReadId = idIn(GENERAL, 1)
      await visitBoth()
      open(/random/)
      await screen.findByText(bodyIn(RANDOM, 2))

      // While Ada was away she read #general to its end somewhere else, and
      // Grace posted again.
      server.channels[GENERAL].lastReadId = idIn(GENERAL, 2)
      server.post(GENERAL, 3)
      const detail = deferred()
      const history = deferred()
      server.gate.detail = detail.promise
      server.gate.history = history.promise

      open(/general/)
      // Only now is Ada looking, with #random gone, so the one read that can
      // follow is for #general, and only after its capture.
      act(() => setPageAttention({ visible: true, focused: true }))
      // The cached list is on screen at once; its detail and history are still held.
      await screen.findByText(bodyIn(GENERAL, 2))
      await sleep(50)
      expect(screen.queryByRole('separator', { name: 'New messages' })).not.toBeInTheDocument()

      const gates = { detail, history }
      gates[first].release()
      await sleep(150)
      // One of the two has landed; the capture still waits for the other.
      expect(screen.queryByRole('separator', { name: 'New messages' })).not.toBeInTheDocument()
      expect(marks(socket)).toEqual([])

      gates[first === 'detail' ? 'history' : 'detail'].release()

      const divider = await screen.findByRole('separator', { name: 'New messages' })
      // Above the message that arrived while away — two messages sit above it.
      const above = [...document.querySelectorAll('article')].filter(
        (row) => row.compareDocumentPosition(divider) & Node.DOCUMENT_POSITION_FOLLOWING,
      )
      expect(above).toHaveLength(2)
      await vi.waitFor(() => expect(markIds(socket)).toEqual([idIn(GENERAL, 3)]))
    },
  )
})
