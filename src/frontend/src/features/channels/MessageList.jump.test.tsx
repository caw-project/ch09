/**
 * Jumping to a message in `MessageList`: `/c/:channelId?message=<id>`.
 *
 * The jump looks in the loaded history, pages back for the message up to ten
 * loaded pages, centres and highlights it for two seconds, and removes the
 * param. While it runs nothing is read and a new message does not pull the list
 * to the bottom. It is driven through `MessageList` alone — the hook and the
 * step rule beneath it are the code-writer's to name — so every assertion is on
 * what a user or the network sees: requests, the DOM, `scrollIntoView`, the
 * location, `mark_read`.
 *
 * History is served in pages of two messages, cursors `p2`…`p12`, 24 messages
 * numbered 1…24 oldest to newest: page k holds messages 26−2k and 25−2k, so the
 * newest is on page 1 and message 4 is on page 11. A page can be held back with
 * a gate keyed by its cursor (`null` for the first page), which is how a test
 * looks at the screen between two requests.
 *
 * Two clocks, on purpose. Most tests run in real time and wait on the last
 * effect. The ones that pin the two-second highlight fake only `setTimeout` and
 * `clearTimeout`, from the start, and flush with a bounded loop of
 * `advanceTimersByTimeAsync(0)` — never `vi.waitFor`, which would move the clock
 * on past the instant being pinned.
 */

import { act, fireEvent, screen } from '@testing-library/react'
import type { InfiniteData, QueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { http } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Message, MessagePage } from '../../lib/api/messaging'
import { auth, MESSAGING_URL, messaging, server } from '../../test/api'
import {
  aMessage,
  aMessagePage,
  aWorkspaceMember,
  messageIdAt,
  WORKSPACE_ID,
} from '../../test/factories'
import { giveLayout, layoutEveryElement, stubScrollIntoView } from '../../test/layout'
import { setPageAttention } from '../../test/page'
import { createTestQueryClient, renderWithProviders } from '../../test/render'
import { FakeSocket } from '../../test/socket'
import { useChatStore } from '../../stores/chat'
import { MessageList } from './MessageList'
import { messageKeys, refetchHistory, upsertMessage } from './useMessages'

const CHANNEL = 'channel-general'
const ADA = 'user-ada'
const GRACE = 'user-grace'
const KEY = messageKeys.list(WORKSPACE_ID, CHANNEL)
const GENERAL = `/c/${CHANNEL}`

const m = (n: number, overrides: Partial<Message> = {}) =>
  aMessage({
    id: messageIdAt(n),
    channelId: CHANNEL,
    authorId: GRACE,
    body: `message ${n}`,
    ...overrides,
  })

/** The newest message on page `k` (page 1 is the newest page). */
const newestOn = (k: number) => messageIdAt(26 - 2 * k)

const LAST_PAGE = 12

function pageOf(k: number, newer: Message[], override: Record<string, Partial<Message>>) {
  const hi = 26 - 2 * k
  const items = [m(hi), m(hi - 1)].map((message) => ({ ...message, ...override[message.id] }))
  return aMessagePage(k === 1 ? [...newer, ...items] : items, k < LAST_PAGE ? `p${k + 1}` : null)
}

function deferred() {
  let release!: () => void
  const promise = new Promise<void>((resolve) => {
    release = resolve
  })
  return { promise, release }
}

interface Serving {
  /** Held until released, by the cursor asked for — `'null'` is the first page. */
  hold?: Record<string, Promise<void>>
  /** Newer messages the first page carries, newest first — what a refetch brings. */
  newer?: Message[]
  /** Changes to a served message, by id. */
  override?: Record<string, Partial<Message>>
}

/** Serve the paged history; returns the cursors asked for, in order, live. */
function serveHistory({ hold = {}, newer = [], override = {} }: Serving = {}) {
  const cursors: Array<string | null> = []
  messaging.get('/api/v1/channels/{channel_id}/messages', async ({ request }) => {
    const cursor = new URL(request.url).searchParams.get('cursor')
    cursors.push(cursor)
    await hold[String(cursor)]
    return pageOf(cursor === null ? 1 : Number(cursor.slice(1)), newer, override)
  })
  return cursors
}

function connectedSocket(): FakeSocket {
  const socket = new FakeSocket('token')
  socket.connected = true
  socket.onEmit('mark_read', () => ({ ok: true }))
  return socket
}

function GoTo({ to }: { to: string }) {
  const navigate = useNavigate()
  return <button onClick={() => navigate(to)}>{`go ${to}`}</button>
}

interface RenderOptions {
  /** The message the URL asks for; none means a plain `/c/:channelId`. */
  target?: string
  lastReadId?: string | null
  queryClient?: QueryClient
  /** Destinations a test can navigate to, each as a `go <path>` button. */
  nav?: string[]
}

function renderList({ target, lastReadId = null, queryClient, nav = [] }: RenderOptions = {}) {
  auth.members([aWorkspaceMember({ id: ADA }), aWorkspaceMember({ id: GRACE })])
  const socket = connectedSocket()
  const view = renderWithProviders(
    <>
      {nav.map((to) => (
        <GoTo key={to} to={to} />
      ))}
      <MessageList
        accessToken="token"
        workspaceId={WORKSPACE_ID}
        channelId={CHANNEL}
        userId={ADA}
        myRole={null}
        lastReadId={lastReadId}
        channelFetching={false}
      />
    </>,
    {
      route: target ? `${GENERAL}?message=${target}` : GENERAL,
      path: '/c/:channelId',
      socket,
      queryClient,
    },
  )
  return { ...view, socket }
}

const go = (to: string) => fireEvent.click(screen.getByRole('button', { name: `go ${to}` }))

const marks = (socket: FakeSocket) =>
  socket.emitted
    .filter((e) => e.event === 'mark_read')
    .map((e) => (e.args[0] as { messageId: string }).messageId)

const sleep = (ms: number) => act(() => new Promise<void>((resolve) => setTimeout(resolve, ms)))

const articleOf = (id: string) =>
  document.querySelector<HTMLElement>(`article[data-message-id="${id}"]`)

const highlighted = () =>
  [...document.querySelectorAll('article[data-highlighted="true"]')].map((a) =>
    a.getAttribute('data-message-id'),
  )

const scrollerElement = () => screen.getAllByRole('article')[0].parentElement as HTMLElement

const WAIT = { timeout: 4000 }

/** `scrollIntoView` was called on exactly these articles, in order. */
const scrolledTo = (spy: ReturnType<typeof stubScrollIntoView>) =>
  spy.mock.contexts.map((element) => (element as HTMLElement).getAttribute('data-message-id'))

/** Real browser geometry: a 500px viewport on 1200px of content, free to scroll. */
const VIEWPORT = { clientHeight: 500, scrollHeight: 1200, scrollTop: 0 }

/**
 * Let work run under a faked `setTimeout`: zero-delay timers (TanStack's
 * notifications) and the real network in between. Stops early once `until`
 * holds; bounded either way, and never moves the clock on.
 */
async function flush(until?: () => boolean) {
  for (let i = 0; i < (until ? 150 : 20); i++) {
    await act(() => vi.advanceTimersByTimeAsync(0))
    if (until?.()) return
  }
}

const fakeClock = () => vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })

afterEach(() => {
  vi.useRealTimers()
})

describe('MessageList — jumping to a message', () => {
  it('jumps to a message already loaded: centres it, highlights it, removes the param', async () => {
    const spy = stubScrollIntoView()
    serveHistory()
    const target = messageIdAt(23)
    const { location } = renderList({ target })

    await vi.waitFor(() => expect(spy).toHaveBeenCalledTimes(1))
    expect(scrolledTo(spy)).toEqual([target])
    expect(spy).toHaveBeenCalledWith({ block: 'center' })
    expect(articleOf(target)).toHaveAttribute('data-highlighted', 'true')
    expect(highlighted()).toEqual([target])
    // The router commits the navigation a render after the effect that asked for it.
    await vi.waitFor(() => expect(location().search).toBe(''))
  })

  it('pages back until it finds the message', async () => {
    const spy = stubScrollIntoView()
    layoutEveryElement(VIEWPORT)
    const page2 = deferred()
    const cursors = serveHistory({ hold: { p2: page2.promise } })
    const target = newestOn(3)
    renderList({ target })
    await screen.findByText('message 24')

    // The fresh list opened at its newest message and stays there while it seeks:
    // a build that blocks every scroll while jumping would leave 0.
    expect(scrollerElement().scrollTop).toBe(1200)
    await vi.waitFor(() => expect(cursors).toEqual([null, 'p2']))
    expect(spy).not.toHaveBeenCalled()

    page2.release()

    await vi.waitFor(() => expect(spy).toHaveBeenCalledTimes(1))
    expect(cursors).toEqual([null, 'p2', 'p3'])
    expect(scrolledTo(spy)).toEqual([target])
  })

  it('counts pages cached before the jump towards the ten', async () => {
    const spy = stubScrollIntoView()
    const cursors = serveHistory()
    const queryClient = createCache(4)
    renderList({ target: newestOn(11), queryClient })

    // The mount refetch re-fetches the four cached pages from fresh cursors, and
    // the jump takes the next six; a build counting only its own fetches would
    // go on to ask p11 … p14.
    await screen.findByRole('status', {}, WAIT)
    expect(screen.getByRole('status')).toHaveTextContent('That message is too far back to show.')
    expect(cursors).toEqual([null, 'p2', 'p3', 'p4', 'p5', 'p6', 'p7', 'p8', 'p9', 'p10'])
    await sleep(100)
    expect(cursors).not.toContain('p11')
    expect(spy).not.toHaveBeenCalled()
  })

  it('stops at ten loaded pages with the notice', async () => {
    const spy = stubScrollIntoView()
    layoutEveryElement(VIEWPORT)
    const last = deferred()
    const cursors = serveHistory({ hold: { p10: last.promise } })
    const { location } = renderList({ target: newestOn(11) })
    await screen.findByText('message 24')
    await vi.waitFor(() => expect(cursors).toHaveLength(10), WAIT)
    // Away from the bottom, so the give-up's scroll to the newest is its own.
    giveLayout(scrollerElement(), { clientHeight: 500, scrollHeight: 1200, scrollTop: 300 })

    last.release()

    await screen.findByRole('status', {}, WAIT)
    expect(screen.getByRole('status')).toHaveTextContent('That message is too far back to show.')
    expect(cursors).toEqual([null, 'p2', 'p3', 'p4', 'p5', 'p6', 'p7', 'p8', 'p9', 'p10'])
    await sleep(100)
    expect(cursors).not.toContain('p11')
    expect(scrollerElement().scrollTop).toBe(1200)
    expect(location().search).toBe('')
    expect(highlighted()).toEqual([])
    expect(spy).not.toHaveBeenCalled()
  })

  it('ends on a failed fetch with the list’s own error', async () => {
    const spy = stubScrollIntoView()
    serveHistory()
    // Layered over the page stub: only page 2 fails, everything else falls through.
    server.use(
      http.get(`${MESSAGING_URL}/api/v1/channels/:channelId/messages`, ({ request }) =>
        new URL(request.url).searchParams.get('cursor') === 'p2'
          ? Response.json(
              { status: 503, title: 'Unavailable', detail: 'History is unavailable.' },
              { status: 503, headers: { 'Content-Type': 'application/problem+json' } },
            )
          : undefined,
      ),
    )
    const { location } = renderList({ target: newestOn(3) })

    await vi.waitFor(() => expect(location().search).toBe(''))
    expect(await screen.findByRole('alert')).toHaveTextContent('History is unavailable.')
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(spy).not.toHaveBeenCalled()
  })

  it('highlights a tombstone', async () => {
    stubScrollIntoView()
    const target = newestOn(2)
    serveHistory({ override: { [target]: { body: '', deletedAt: '2026-09-15T10:00:00Z' } } })
    renderList({ target })

    await vi.waitFor(() => expect(articleOf(target)).toHaveAttribute('data-highlighted', 'true'))
    expect(screen.getByText('message 24')).toBeInTheDocument()
  })

  it('fades the highlight after two seconds', async () => {
    fakeClock()
    const spy = stubScrollIntoView()
    serveHistory()
    const target = messageIdAt(23)
    renderList({ target })

    await flush(() => spy.mock.calls.length > 0)
    expect(highlighted()).toEqual([target])

    await act(() => vi.advanceTimersByTimeAsync(1999))
    expect(highlighted()).toEqual([target])

    await act(() => vi.advanceTimersByTimeAsync(1))
    expect(highlighted()).toEqual([])
  })

  it('holds reads and the badge off during the jump, then reads once it ends', async () => {
    fakeClock()
    setPageAttention({ visible: true, focused: true })
    layoutEveryElement({ clientHeight: 500, scrollHeight: 1200, scrollTop: 700, frozen: true })
    stubScrollIntoView()
    serveHistory()
    const target = messageIdAt(23)
    const { socket } = renderList({ target })

    await flush(() => articleOf(target) !== null)
    await flush()
    // The negative half comes after the list rendered and the read rule had every
    // chance to fire; the highlight below is what shows the jump was still running.
    expect(marks(socket)).toEqual([])
    expect(useChatStore.getState().readingChannelId).toBeNull()
    expect(highlighted()).toEqual([target])

    await act(() => vi.advanceTimersByTimeAsync(1999))
    expect(marks(socket)).toEqual([])

    await act(() => vi.advanceTimersByTimeAsync(1))
    await flush()
    expect(highlighted()).toEqual([])
    expect(marks(socket)).toEqual([messageIdAt(24)])
    expect(useChatStore.getState().readingChannelId).toBe(CHANNEL)
  })

  it('does not pull to the bottom when a message arrives mid-jump', async () => {
    // Laid out from the start, so loading page 2 does not read a height jump as a prepend.
    layoutEveryElement(VIEWPORT)
    const spy = stubScrollIntoView()
    const page2 = deferred()
    serveHistory({ hold: { p2: page2.promise } })
    const { queryClient } = renderList({ target: newestOn(3) })
    await screen.findByText('message 24')

    // At the bottom of a 1200px list, free to move: a pull would write 1200.
    const scroller = scrollerElement()
    giveLayout(scroller, { clientHeight: 500, scrollHeight: 1200, scrollTop: 700 })
    fireEvent.scroll(scroller)
    act(() => upsertMessage(queryClient, KEY, m(25)))
    await screen.findByText('message 25')

    expect(scroller.scrollTop).toBe(700)

    page2.release()
    await vi.waitFor(() => expect(spy).toHaveBeenCalledTimes(1))
    expect(scrolledTo(spy)).toEqual([newestOn(3)])
    expect(scroller.scrollTop).toBe(700)
  })

  it('waits for a refetch already in flight, then pages back (Timing 1)', async () => {
    const spy = stubScrollIntoView()
    const refetch = deferred()
    const cursors = serveHistory({ hold: { null: refetch.promise }, newer: [m(25)] })
    // Page 1 is cached, so the mount refetch is in flight from the first render
    // and the jump has to wait for it.
    const queryClient = createCache(1)
    renderList({ target: newestOn(3), queryClient })
    await vi.waitFor(() => expect(cursors).toEqual([null]))
    await sleep(50)
    // The half a build that looks while fetching, and pages with the default
    // `cancelRefetch`, fails: it asks for page 2 while the refetch is held.
    expect(cursors).toEqual([null])

    refetch.release()

    await screen.findByText('message 25')
    await vi.waitFor(() => expect(cursors).toEqual([null, 'p2', 'p3']))
    await vi.waitFor(() => expect(spy).toHaveBeenCalledTimes(1))
    expect(scrolledTo(spy)).toEqual([newestOn(3)])
  })

  it('holds reads off when a jump starts on the open channel, after flushing a held read', async () => {
    fakeClock()
    setPageAttention({ visible: true, focused: true })
    layoutEveryElement(VIEWPORT)
    const spy = stubScrollIntoView()
    const page2 = deferred()
    serveHistory({ hold: { p2: page2.promise } })
    const { socket, queryClient } = renderList({ nav: [`${GENERAL}?message=${newestOn(2)}`] })

    await flush(() => marks(socket).length > 0)
    expect(marks(socket)).toEqual([messageIdAt(24)])
    // A newer message inside the read's window: its read is held by the throttle.
    act(() => upsertMessage(queryClient, KEY, m(25)))
    await flush()
    expect(marks(socket)).toEqual([messageIdAt(24)])

    // The jump starts on the mounted list. The held read goes out at once — no
    // time has passed — and nothing is requested after it.
    go(`${GENERAL}?message=${newestOn(2)}`)
    await flush()
    expect(marks(socket)).toEqual([messageIdAt(24), messageIdAt(25)])
    expect(useChatStore.getState().readingChannelId).toBeNull()

    // Geometry reset after the navigation, so a pull writes a different value
    // (1200) from the one the reader is at (700).
    const scroller = scrollerElement()
    giveLayout(scroller, { clientHeight: 500, scrollHeight: 1200, scrollTop: 700 })
    act(() => upsertMessage(queryClient, KEY, m(26)))
    await flush()
    expect(screen.getByText('message 26')).toBeInTheDocument()
    expect(marks(socket)).toEqual([messageIdAt(24), messageIdAt(25)])
    expect(scroller.scrollTop).toBe(700)

    page2.release()
    await flush(() => spy.mock.calls.length > 0)
    expect(scrolledTo(spy)).toEqual([newestOn(2)])
    // A page fetch builds its result from the pages it started with, so the message
    // that arrived while page 2 was held is gone when it lands; the live socket
    // delivers it again (as `reapplyAfterFetch` does), now that the highlight runs.
    act(() => upsertMessage(queryClient, KEY, m(26)))
    await flush()
    expect(screen.getByText('message 26')).toBeInTheDocument()
    await act(() => vi.advanceTimersByTimeAsync(1999))
    expect(marks(socket)).toEqual([messageIdAt(24), messageIdAt(25)])

    await act(() => vi.advanceTimersByTimeAsync(1))
    await flush()
    expect(marks(socket)).toEqual([messageIdAt(24), messageIdAt(25), messageIdAt(26)])
  })

  it('keeps a page fetched across a reconnect, then looks again (Timing 2)', async () => {
    const spy = stubScrollIntoView()
    const page3 = deferred()
    const cursors = serveHistory({ hold: { p3: page3.promise } })
    const { queryClient } = renderList({ target: newestOn(4) })
    await vi.waitFor(() => expect(cursors).toEqual([null, 'p2', 'p3']), WAIT)

    // The join ack of a reconnect, while page 3 is in flight.
    refetchHistory(queryClient, KEY)
    await sleep(50)
    expect(cursors).toEqual([null, 'p2', 'p3'])

    page3.release()

    await vi.waitFor(() => expect(spy).toHaveBeenCalledTimes(1), WAIT)
    // Page 3 kept, then the refetch of what was loaded, then the page it was
    // looking for.
    expect(cursors).toEqual([null, 'p2', 'p3', null, 'p2', 'p3', 'p4'])
    expect(scrolledTo(spy)).toEqual([newestOn(4)])
  })

  it('abandons the jump when the list unmounts', async () => {
    const spy = stubScrollIntoView()
    const page2 = deferred()
    const cursors = serveHistory({ hold: { p2: page2.promise } })
    const { unmount, queryClient } = renderList({ target: newestOn(3) })
    await vi.waitFor(() => expect(cursors).toEqual([null, 'p2']))

    unmount()
    page2.release()

    // The page that was in flight lands in the cache — and nothing looks for more.
    await vi.waitFor(() => expect(cachedPages(queryClient)).toBe(2))
    await sleep(100)
    expect(cursors).toEqual([null, 'p2'])
    expect(spy).not.toHaveBeenCalled()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('abandons the jump when the param is removed by navigation', async () => {
    const spy = stubScrollIntoView()
    const page2 = deferred()
    const cursors = serveHistory({ hold: { p2: page2.promise } })
    const { queryClient } = renderList({ target: newestOn(3), nav: [GENERAL] })
    await vi.waitFor(() => expect(cursors).toEqual([null, 'p2']))

    go(GENERAL)
    page2.release()

    await vi.waitFor(() => expect(cachedPages(queryClient)).toBe(2))
    await screen.findByText('message 22', {}, WAIT)
    await sleep(100)
    expect(cursors).toEqual([null, 'p2'])
    expect(spy).not.toHaveBeenCalled()
    expect(highlighted()).toEqual([])
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('follows only the latest target', async () => {
    const spy = stubScrollIntoView()
    const page2 = deferred()
    const cursors = serveHistory({ hold: { p2: page2.promise } })
    const a = newestOn(3)
    const b = newestOn(2)
    renderList({ target: a, nav: [`${GENERAL}?message=${b}`] })
    await vi.waitFor(() => expect(cursors).toEqual([null, 'p2']))

    go(`${GENERAL}?message=${b}`)
    page2.release()

    await vi.waitFor(() => expect(spy).toHaveBeenCalledTimes(1))
    await sleep(100)
    expect(scrolledTo(spy)).toEqual([b])
    expect(highlighted()).toEqual([b])
    expect(cursors).toEqual([null, 'p2'])
  })

  it('shows the divider and the highlight together', async () => {
    stubScrollIntoView()
    const target = newestOn(3)
    // The marker is on page 2: the divider's boundary loads while the jump pages back.
    serveHistory()
    renderList({ target, lastReadId: messageIdAt(21) })

    await vi.waitFor(() => expect(articleOf(target)).toHaveAttribute('data-highlighted', 'true'))
    expect(screen.getByRole('separator', { name: 'New messages' })).toBeInTheDocument()
  })
})

/** The cache as the list would have it after `pages` loads, for a mount that refetches. */
function createCache(pages: number): QueryClient {
  const queryClient = createTestQueryClient()
  queryClient.setQueryData<InfiniteData<MessagePage>>(KEY, {
    pages: Array.from({ length: pages }, (_, i) => pageOf(i + 1, [], {})),
    pageParams: Array.from({ length: pages }, (_, i) => (i === 0 ? undefined : `p${i + 1}`)),
  })
  return queryClient
}

function cachedPages(queryClient: QueryClient): number {
  return queryClient.getQueryData<InfiniteData<MessagePage>>(KEY)?.pages.length ?? 0
}
