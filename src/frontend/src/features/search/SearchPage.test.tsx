/**
 * The results page at `/search?q=…`, through the boundary a user meets.
 *
 * `searchMessages`, `useSearch`, `useChannelNames` and `SearchResult` are not
 * imported here: each has its behaviour pinned below, by what the page shows and
 * which requests it makes. Real time throughout — fake timers would stall
 * TanStack's notifications, which are scheduled with `setTimeout`.
 *
 * A search request is answered by a stub that records the `Authorization` header
 * it saw and can be held back with a gate, so a test can look at the screen
 * between the request and its answer.
 */

import { onlineManager, type QueryClient } from '@tanstack/react-query'
import { act, screen, within } from '@testing-library/react'
import { http } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Message } from '../../lib/api/messaging'
import { auth, MESSAGING_URL, messaging, requests, server } from '../../test/api'
import {
  aChannel,
  aMessage,
  aMessagePage,
  aWorkspaceMember,
  WORKSPACE_ID,
} from '../../test/factories'
import { setPageAttention } from '../../test/page'
import { createTestQueryClient, renderWithProviders } from '../../test/render'
import { SearchPage } from './SearchPage'

const ADA = 'user-ada'
const GENERAL = aChannel({ id: 'channel-general', name: 'general' })
const SEARCH = '/api/v1/search/messages'

const hit = (body: string, overrides: Partial<Message> = {}) =>
  aMessage({ channelId: GENERAL.id, authorId: ADA, body, ...overrides })

function deferred() {
  let release!: () => void
  const promise = new Promise<void>((resolve) => {
    release = resolve
  })
  return { promise, release }
}

const sleep = (ms: number) => act(() => new Promise<void>((resolve) => setTimeout(resolve, ms)))

const searchRequests = () => requests().filter((r) => r.url.pathname === SEARCH)
const detailRequests = (channelId: string) =>
  requests().filter((r) => r.url.pathname === `/api/v1/channels/${channelId}`)

/** The channel list, and a directory that knows Ada — the page's two side lookups. */
function stubSideLookups(channels = [GENERAL]) {
  messaging.get('/api/v1/channels', { items: channels, nextCursor: null })
  auth.members([aWorkspaceMember({ id: ADA, displayName: 'Ada Lovelace' })])
}

interface RenderOptions {
  route?: string
  queryClient?: QueryClient
}

function renderPage({ route = '/search?q=zeppelin', queryClient }: RenderOptions = {}) {
  return renderWithProviders(<SearchPage accessToken="token" workspaceId={WORKSPACE_ID} />, {
    route,
    path: '/search',
    queryClient,
  })
}

const rows = async () => within(await screen.findByRole('list', { name: 'Search results' })).getAllByRole('listitem')

afterEach(() => {
  onlineManager.setOnline(true)
})

describe('SearchPage', () => {
  it('lists results in the order served, newest first', async () => {
    stubSideLookups()
    const newer = hit('the newer hit', { createdAt: '2026-09-16T09:00:00Z' })
    const older = hit('the older hit', { createdAt: '2026-09-15T09:00:00Z' })
    messaging.get(SEARCH, aMessagePage([newer, older]))
    renderPage()

    const items = await rows()

    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent('the newer hit')
    expect(items[1]).toHaveTextContent('the older hit')
  })

  it('shows channel, author, date and time, and the body as plain text', async () => {
    stubSideLookups()
    const message = hit('<b>bold</b> words', { createdAt: '2026-09-15T09:30:00Z' })
    messaging.get(SEARCH, aMessagePage([message]))
    renderPage()

    const [row] = await rows()

    expect(within(row).getByText('#general')).toBeInTheDocument()
    expect(await within(row).findByText('Ada Lovelace')).toBeInTheDocument()
    const time = row.querySelector('time')
    expect(time).toHaveAttribute('datetime', '2026-09-15T09:30:00Z')
    expect(time).toHaveTextContent(/2026/)
    // Markup in a body is text: shown literally, with no element made from it.
    expect(within(row).getByText('<b>bold</b> words')).toBeInTheDocument()
    expect(row.querySelector('b')).toBeNull()
    expect(row.querySelector('mark')).toBeNull()
  })

  it('marks an edited result, and only that one', async () => {
    stubSideLookups()
    messaging.get(
      SEARCH,
      aMessagePage([hit('untouched'), hit('reworded', { editedAt: '2026-09-15T10:00:00Z' })]),
    )
    renderPage()

    const [first, second] = await rows()

    expect(within(second).getByText('(edited)')).toBeInTheDocument()
    expect(within(first).queryByText('(edited)')).not.toBeInTheDocument()
    expect(screen.getAllByText('(edited)')).toHaveLength(1)
  })

  it('names a channel outside the list from its detail, fetched once', async () => {
    stubSideLookups()
    const design = aChannel({ id: 'channel-design', name: 'design' })
    const gate = deferred()
    messaging.get('/api/v1/channels/{channel_id}', async () => {
      await gate.promise
      return design
    })
    messaging.get(
      SEARCH,
      aMessagePage([hit('one', { channelId: design.id }), hit('two', { channelId: design.id })]),
    )
    renderPage()

    await rows()
    await vi.waitFor(() => expect(detailRequests(design.id)).toHaveLength(1))
    // Held: both rows wait on the one fetch behind a placeholder.
    expect(screen.getAllByText('#…')).toHaveLength(2)

    gate.release()

    await vi.waitFor(() => expect(screen.getAllByText('#design')).toHaveLength(2))
    expect(detailRequests(design.id)).toHaveLength(1)
  })

  it('leaves the row as it is when the channel’s detail is a 404', async () => {
    stubSideLookups()
    messaging.problem('get', '/api/v1/channels/{channel_id}', 404, {
      title: 'Not Found',
      detail: 'Channel not found.',
    })
    messaging.get(
      SEARCH,
      aMessagePage([hit('in the list'), hit('out of reach', { channelId: 'channel-gone' })]),
    )
    renderPage()

    const [inList, outside] = await rows()
    await vi.waitFor(() => expect(detailRequests('channel-gone')).toHaveLength(1))
    await sleep(50)

    expect(within(outside).getByText('#…')).toBeInTheDocument()
    expect(within(inList).getByText('#general')).toBeInTheDocument()
  })

  it('does not fetch a detail for a channel in the list', async () => {
    stubSideLookups()
    // Stubbed, so a build that asks anyway is recorded rather than refused.
    messaging.get('/api/v1/channels/{channel_id}', GENERAL)
    messaging.get(SEARCH, aMessagePage([hit('in the list')]))
    renderPage()

    const [row] = await rows()
    await vi.waitFor(() => expect(within(row).getByText('#general')).toBeInTheDocument())
    await sleep(50)

    expect(detailRequests(GENERAL.id)).toHaveLength(0)
  })

  it('loads more after a short page until nextCursor is null', async () => {
    stubSideLookups()
    messaging.get(SEARCH, ({ request }) =>
      new URL(request.url).searchParams.get('cursor') === 'c2'
        ? aMessagePage([hit('page two')])
        : aMessagePage([hit('page one')], 'c2'),
    )
    const { user } = renderPage()
    await screen.findByText('page one')

    // One item on a page, and a cursor: the list is not at its end.
    await user.click(screen.getByRole('button', { name: 'Load more' }))

    await screen.findByText('page two')
    expect(searchRequests().map((r) => r.url.searchParams.get('cursor'))).toEqual([null, 'c2'])
    const items = await rows()
    expect(items[0]).toHaveTextContent('page one')
    expect(items[1]).toHaveTextContent('page two')
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument()
  })

  it('says nothing matches, with no caveat', async () => {
    stubSideLookups()
    messaging.get(SEARCH, aMessagePage([]))
    renderPage()

    const status = await screen.findByRole('status')

    expect(status.textContent).toBe('No messages match "zeppelin".')
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument()
  })

  it('says search is unavailable on a 503, and Retry fetches again', async () => {
    stubSideLookups()
    messaging.problem('get', SEARCH, 503, { title: 'Service Unavailable', detail: 'Search is unavailable.' })
    const { user } = renderPage()

    expect(await screen.findByRole('alert')).toHaveTextContent('Search is unavailable.')
    const retry = screen.getByRole('button', { name: 'Retry' })
    messaging.get(SEARCH, aMessagePage([hit('back again')]))

    await user.click(retry)

    await screen.findByText('back again')
    expect(searchRequests()).toHaveLength(2)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('keeps the list and offers Load more again when a later page fails', async () => {
    stubSideLookups()
    messaging.get(SEARCH, aMessagePage([hit('page one')], 'c2'))
    // Layered over the stub: only the second page fails, the rest falls through.
    server.use(
      http.get(`${MESSAGING_URL}${SEARCH}`, ({ request }) =>
        new URL(request.url).searchParams.get('cursor') === 'c2'
          ? Response.json(
              { status: 503, title: 'Service Unavailable', detail: 'Search is unavailable.' },
              { status: 503, headers: { 'Content-Type': 'application/problem+json' } },
            )
          : undefined,
      ),
    )
    const { user } = renderPage()
    await screen.findByText('page one')

    await user.click(screen.getByRole('button', { name: 'Load more' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Search is unavailable.')
    expect(screen.getByText('page one')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Load more' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument()
  })

  it('shows the cached list at once on return, then refetches', async () => {
    stubSideLookups()
    const gate = deferred()
    let calls = 0
    messaging.get(SEARCH, async () => {
      calls += 1
      if (calls === 1) return aMessagePage([hit('the old list')])
      await gate.promise
      return aMessagePage([hit('the new list')])
    })
    const queryClient = createTestQueryClient()
    const first = renderPage({ queryClient })
    await screen.findByText('the old list')
    first.unmount()

    renderPage({ queryClient })

    // Synchronously: the cached rows are on screen before the refetch answers.
    expect(screen.getByText('the old list')).toBeInTheDocument()
    await vi.waitFor(() => expect(searchRequests()).toHaveLength(2))
    expect(screen.getByText('the old list')).toBeInTheDocument()

    gate.release()

    await screen.findByText('the new list')
    expect(screen.queryByText('the old list')).not.toBeInTheDocument()
  })

  it('does not update a list on screen on focus or reconnect', async () => {
    stubSideLookups()
    messaging.get(SEARCH, aMessagePage([hit('a result')]))
    const queryClient = createTestQueryClient()
    const first = renderPage({ queryClient })
    await screen.findByText('a result')
    expect(searchRequests()).toHaveLength(1)

    // The tab is hidden and comes back, and the window is refocused…
    act(() => setPageAttention({ visible: false, focused: false }))
    act(() => setPageAttention({ visible: true, focused: true }))
    // … and the network drops and returns.
    act(() => onlineManager.setOnline(false))
    act(() => onlineManager.setOnline(true))
    await sleep(100)

    expect(searchRequests()).toHaveLength(1)

    // The positive half: a return to the page *does* refetch, so the count above
    // would have moved had focus or reconnect been refetching.
    first.unmount()
    renderPage({ queryClient })
    await vi.waitFor(() => expect(searchRequests()).toHaveLength(2))
  })

  it('searches the new workspace on a switch and shows nothing from the old one', async () => {
    stubSideLookups()
    const gate = deferred()
    const seen: Array<string | null> = []
    messaging.get(SEARCH, async ({ request }) => {
      const authorization = request.headers.get('authorization')
      seen.push(authorization)
      if (authorization === 'Bearer token-b') {
        await gate.promise
        return aMessagePage([hit('workspace B result')])
      }
      return aMessagePage([hit('workspace A result')])
    })
    const view = renderWithProviders(
      <SearchPage accessToken="token-a" workspaceId="workspace-a" />,
      { route: '/search?q=zeppelin', path: '/search' },
    )
    await screen.findByText('workspace A result')

    view.rerender(<SearchPage accessToken="token-b" workspaceId="workspace-b" />)

    expect(screen.queryByText('workspace A result')).not.toBeInTheDocument()
    await vi.waitFor(() => expect(seen).toEqual(['Bearer token-a', 'Bearer token-b']))

    gate.release()

    expect(await screen.findByText('workspace B result')).toBeInTheDocument()
    expect(screen.queryByText('workspace A result')).not.toBeInTheDocument()
  })

  it('fetches nothing for a blank query', async () => {
    stubSideLookups()
    renderPage({ route: '/search?q=%20%20' })

    expect(await screen.findByText('Type in the search box to find messages.')).toBeInTheDocument()
    await sleep(50)

    expect(searchRequests()).toHaveLength(0)
  })

  it('links each result to its message in its channel', async () => {
    stubSideLookups()
    const message = hit('find me')
    messaging.get(SEARCH, aMessagePage([message]))
    const { user, location } = renderPage()
    await screen.findByText('find me')

    const link = within((await rows())[0]).getByRole('link')

    expect(link).toHaveAttribute('href', `/c/${GENERAL.id}?message=${message.id}`)

    await user.click(link)

    expect(location().pathname).toBe(`/c/${GENERAL.id}`)
    expect(location().search).toBe(`?message=${message.id}`)
  })
})
