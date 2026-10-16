/**
 * The route guards in `App`.
 *
 * The session store is module state and `loading` exists only until the first
 * restore settles, so each test imports a fresh `App` — and with it a fresh
 * session. The session is driven the way the app drives it: `App` calls
 * `restore()` on mount, and the Auth stubs decide what that finds.
 */

import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Profile, TokenPair, Workspace } from './lib/auth/api'
import { auth, AUTH_URL, messaging, server } from './test/api'
import { aChannel, aMessage, aWorkspaceMember, WORKSPACE_ID } from './test/factories'
import { renderWithProviders } from './test/render'

type AppModule = typeof import('./App')

const CHANNEL_ID = '0199a000-0000-7000-8000-00000000c001'

const PROFILE: Profile = {
  id: 'user-ada',
  email: 'ada@collabhub.dev',
  displayName: 'Ada Lovelace',
  avatarAsset: null,
}
const WORKSPACES: Workspace[] = [{ id: WORKSPACE_ID, name: 'CollabHub', role: 'owner' }]

/** An unsigned token carrying a `wsp` claim — the SPA only ever reads it. */
function tokenFor(workspaceId: string): string {
  const payload = btoa(JSON.stringify({ wsp: workspaceId }))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
  return `header.${payload}.signature`
}

const PAIR: TokenPair = { accessToken: tokenFor(WORKSPACE_ID), tokenType: 'Bearer', expiresIn: 900 }

function aReturningUser() {
  auth.refresh(PAIR)
  auth.me(PROFILE)
  auth.workspaces(WORKSPACES)
  messaging.get('/api/v1/channels', { items: [], nextCursor: null })
}

function aFirstVisit() {
  auth.problem('post', '/api/v1/auth/refresh', 401, { title: 'Unauthorized' })
}

let App: AppModule['App']

async function freshApp(): Promise<AppModule['App']> {
  vi.resetModules()
  const module: AppModule = await import('./App')
  return module.App
}

beforeEach(async () => {
  App = await freshApp()
})

afterEach(() => {
  window.sessionStorage.clear()
  vi.unstubAllGlobals()
})

describe('App routes', () => {
  it('sends a signed-out visitor who opens a channel link to sign in', async () => {
    aFirstVisit()

    const { location } = renderWithProviders(<App />, { route: `/c/${CHANNEL_ID}` })

    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument()
    expect(location().pathname).toBe('/sign-in')
  })

  it('shows loading, not sign-in, while the session is restoring', async () => {
    let release!: () => void
    const held = new Promise<void>((resolve) => {
      release = resolve
    })
    server.use(
      http.post(`${AUTH_URL}/api/v1/auth/refresh`, async () => {
        await held
        return HttpResponse.json({ status: 401, title: 'Unauthorized' }, { status: 401 })
      }),
    )

    const { location } = renderWithProviders(<App />, { route: `/c/${CHANNEL_ID}` })

    expect(await screen.findByText('Loading…')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Sign in' })).not.toBeInTheDocument()
    expect(location().pathname).toBe(`/c/${CHANNEL_ID}`)

    release()
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('sends a signed-in visitor on the sign-in page into the app', async () => {
    aReturningUser()

    const { location } = renderWithProviders(<App />, { route: '/sign-in' })

    expect(await screen.findByText('Pick a channel, or create one.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Sign in' })).not.toBeInTheDocument()
    expect(location().pathname).toBe('/')
  })

  it('shows search results on /search for a signed-in user', async () => {
    aReturningUser()
    messaging.get('/api/v1/search/messages', {
      items: [aMessage({ channelId: CHANNEL_ID, authorId: PROFILE.id, body: 'the zeppelin lands' })],
      nextCursor: null,
    })
    messaging.get('/api/v1/channels/{channel_id}', aChannel({ id: CHANNEL_ID, name: 'general' }))
    auth.members([aWorkspaceMember({ id: PROFILE.id, displayName: 'Ada Lovelace' })])

    renderWithProviders(<App />, { route: '/search?q=zeppelin' })

    expect(await screen.findByText('the zeppelin lands')).toBeInTheDocument()
    // Inside the shell: the sidebar's search box is on the page beside the results.
    expect(screen.getByRole('search', { name: 'Search messages' })).toBeInTheDocument()
  })

  it('shows no email address and no password on the sign-in page', async () => {
    aFirstVisit()

    const { container } = renderWithProviders(<App />, { route: '/sign-in' })

    // The page has rendered, so the absence below is not an empty screen.
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument()
    expect(screen.getByText('Sign in with your CollabHub account.')).toBeInTheDocument()

    const text = container.textContent ?? ''
    expect(text).not.toMatch(/\S+@\S+\.\S+/)
    expect(text).not.toMatch(/password/i)
    // The demo password; the heading's "CollabHub" is capitalised and doesn't match.
    expect(text).not.toMatch(/\bcollabhub\b/)
  })

  it('renders /settings on a direct load', async () => {
    aReturningUser()
    auth.members([aWorkspaceMember({ id: PROFILE.id, displayName: 'Ada Lovelace' })])

    renderWithProviders(<App />, { route: '/settings' })

    expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument()
    // Inside the shell, reached from the sidebar’s name.
    expect(screen.getByRole('search', { name: 'Search messages' })).toBeInTheDocument()
  })

  it('says so for a route that does not exist', async () => {
    aFirstVisit()

    renderWithProviders(<App />, { route: '/no/such/page' })

    expect(await screen.findByText('No such page.')).toBeInTheDocument()
  })
})

describe('App — coming back after sign-in', () => {
  const RETURN_KEY = 'collabhub.returnTo'
  const VERIFIER_KEY = 'collabhub.pkceVerifier'

  it('takes a signed-out visitor on /settings through sign-in and back to /settings', async () => {
    aFirstVisit()
    const assign = vi.fn()
    vi.stubGlobal('location', { ...window.location, assign })
    const first = renderWithProviders(<App />, { route: '/settings' })

    // Sent to sign in, remembering where from.
    await first.user.click(await screen.findByRole('button', { name: 'Sign in' }))
    await vi.waitFor(() => expect(assign).toHaveBeenCalled())
    expect(first.location().pathname).toBe('/sign-in')
    expect(window.sessionStorage.getItem(RETURN_KEY)).toBe('/settings')
    first.unmount()

    // The identity provider sends the browser back, to a page load of its own.
    const Callback = await freshApp()
    aReturningUser()
    auth.exchange(PAIR)
    auth.members([aWorkspaceMember({ id: PROFILE.id, displayName: 'Ada Lovelace' })])
    expect(window.sessionStorage.getItem(VERIFIER_KEY)).not.toBeNull()
    const second = renderWithProviders(<Callback />, { route: '/auth/callback?code=c' })

    expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument()
    expect(second.location().pathname).toBe('/settings')
    expect(window.sessionStorage.getItem(RETURN_KEY)).toBeNull()
  })

  it('lands on / when no path was remembered', async () => {
    aReturningUser()
    auth.exchange(PAIR)
    window.sessionStorage.setItem(VERIFIER_KEY, 'verifier')

    const { location } = renderWithProviders(<App />, { route: '/auth/callback?code=c' })

    expect(await screen.findByText('Pick a channel, or create one.')).toBeInTheDocument()
    expect(location().pathname).toBe('/')
  })
})
