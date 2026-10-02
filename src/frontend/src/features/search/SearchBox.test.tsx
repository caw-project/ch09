/**
 * The sidebar's search box: what Enter does, what the box shows per route, and
 * that submitting the same query again refetches it.
 *
 * `SearchBox` is rendered on its own, matching every route (`path: '*'`), with
 * `SearchPage` beside it only where a test needs results. It reads the location
 * itself, so a test moves it between routes by navigating.
 */

import { screen, within } from '@testing-library/react'
import { useNavigate } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { auth, messaging, requests } from '../../test/api'
import { aChannel, aMessage, aMessagePage, aWorkspaceMember, WORKSPACE_ID } from '../../test/factories'
import { renderWithProviders } from '../../test/render'
import { SearchBox } from './SearchBox'
import { SearchPage } from './SearchPage'

const box = () => screen.getByRole('searchbox', { name: 'Search messages' })

function GoTo({ to }: { to: string }) {
  const navigate = useNavigate()
  return <button onClick={() => navigate(to)}>{`go ${to}`}</button>
}

const searchRequests = () => requests().filter((r) => r.url.pathname === '/api/v1/search/messages')

describe('SearchBox', () => {
  it.each(['/', '/c/channel-general'])('submits the trimmed text to /search from %s', async (route) => {
    const { user, location } = renderWithProviders(<SearchBox workspaceId={WORKSPACE_ID} />, {
      route,
      path: '*',
    })

    await user.type(box(), '  zeppelin  {Enter}')

    expect(location().pathname).toBe('/search')
    expect(new URLSearchParams(location().search).get('q')).toBe('zeppelin')
  })

  it('submits nothing for a blank box, and does once there is text', async () => {
    const { user, location } = renderWithProviders(<SearchBox workspaceId={WORKSPACE_ID} />, {
      route: '/',
      path: '*',
    })

    await user.type(box(), '   {Enter}')
    expect(location().pathname).toBe('/')
    expect(location().search).toBe('')

    // The same Enter, with text, is what navigates: the silence above was the
    // blank rule, not a box that never submits.
    await user.clear(box())
    await user.type(box(), 'x{Enter}')
    expect(location().pathname).toBe('/search')
    expect(location().search).toBe('?q=x')
  })

  it('takes at most 200 characters', async () => {
    const { user } = renderWithProviders(<SearchBox workspaceId={WORKSPACE_ID} />, {
      route: '/',
      path: '*',
    })

    await user.type(box(), 'a'.repeat(201))

    expect(box()).toHaveValue('a'.repeat(200))
  })

  it('shows the query on /search and nothing elsewhere', async () => {
    const { user } = renderWithProviders(
      <>
        <GoTo to="/c/channel-general?q=zeppelin" />
        <SearchBox workspaceId={WORKSPACE_ID} />
      </>,
      { route: '/search?q=zeppelin', path: '*' },
    )
    expect(box()).toHaveValue('zeppelin')

    // The destination carries the same `q`: only the route decides what the box shows.
    await user.click(screen.getByRole('button', { name: 'go /c/channel-general?q=zeppelin' }))

    expect(box()).toHaveValue('')
  })

  it('refetches when the same query is submitted again', async () => {
    messaging.get('/api/v1/channels', {
      items: [aChannel({ id: 'channel-general', name: 'general' })],
      nextCursor: null,
    })
    auth.members([aWorkspaceMember({ id: 'user-ada' })])
    messaging.get('/api/v1/search/messages', () =>
      aMessagePage([aMessage({ channelId: 'channel-general', authorId: 'user-ada', body: 'a hit' })]),
    )
    const { user, location } = renderWithProviders(
      <>
        <SearchBox workspaceId={WORKSPACE_ID} />
        <SearchPage accessToken="token" workspaceId={WORKSPACE_ID} />
      </>,
      { route: '/search?q=x', path: '/search' },
    )
    await screen.findByText('a hit')
    expect(searchRequests()).toHaveLength(1)

    await user.type(box(), '{Enter}')

    await vi.waitFor(() => expect(searchRequests()).toHaveLength(2))
    // The same URL: no second history entry, and the box still says `x`.
    expect(location().search).toBe('?q=x')
    expect(box()).toHaveValue('x')
  })

  it('sits inside a named search landmark', () => {
    renderWithProviders(<SearchBox workspaceId={WORKSPACE_ID} />, { route: '/', path: '*' })

    const landmark = screen.getByRole('search', { name: 'Search messages' })

    expect(within(landmark).getByRole('searchbox', { name: 'Search messages' })).toBe(box())
  })
})
