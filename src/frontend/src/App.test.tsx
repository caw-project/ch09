/**
 * The route guards in `App`.
 *
 * The session store is module state and `loading` exists only until the first
 * restore settles, so each test imports a fresh `App` — and with it a fresh
 * session. The session is driven the way the app drives it: `App` calls
 * `restore()` on mount, and the Auth stubs decide what that finds.
 */

import { act, fireEvent, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Profile, TokenPair, Workspace } from './lib/auth/api'
import { auth, AUTH_URL, messaging, requests, server } from './test/api'
import {
  aChannel,
  aMessage,
  aMessagePage,
  aWorkspaceMember,
  WORKSPACE_ID,
} from './test/factories'
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

function aReturningUser(workspaces: Workspace[] = WORKSPACES) {
  auth.refresh(PAIR)
  auth.me(PROFILE)
  auth.workspaces(workspaces)
  messaging.get('/api/v1/channels', { items: [], nextCursor: null })
  // The sidebar's direct messages and every author line read the directory.
  auth.members([aWorkspaceMember({ id: PROFILE.id, displayName: 'Ada Lovelace' })])
}

function aFirstVisit() {
  auth.problem('post', '/api/v1/auth/refresh', 401, { title: 'Unauthorized' })
}

let App: AppModule['App']

beforeEach(async () => {
  vi.resetModules()
  const module: AppModule = await import('./App')
  App = module.App
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

  it('says so for a route that does not exist', async () => {
    aFirstVisit()

    renderWithProviders(<App />, { route: '/no/such/page' })

    expect(await screen.findByText('No such page.')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// /settings (issue gh-3, Req 5 and 8 — the "Paths each rule holds on" table)
// ---------------------------------------------------------------------------

const AWAY_ID = '0199a000-0000-7000-8000-0000000000f1'
const TWO_WORKSPACES: Workspace[] = [
  { id: WORKSPACE_ID, name: 'CollabHub', role: 'owner' },
  { id: AWAY_ID, name: 'Away', role: 'member' },
]
const AWAY_PAIR: TokenPair = { accessToken: tokenFor(AWAY_ID), tokenType: 'Bearer', expiresIn: 900 }
const RETURN_KEY = 'collabhub.returnTo'
const VERIFIER_KEY = 'collabhub.pkceVerifier'

/** Messaging for one channel the user can open, so the real `ChannelView` renders. */
function aChannelToOpen() {
  const channel = aChannel({ id: CHANNEL_ID, name: 'general' })
  messaging.get('/api/v1/channels', { items: [channel], nextCursor: null })
  messaging.get('/api/v1/channels/{channel_id}', channel)
  messaging.get(
    '/api/v1/channels/{channel_id}/messages',
    aMessagePage([aMessage({ channelId: CHANNEL_ID, body: 'the engine hums' })]),
  )
  messaging.get('/api/v1/channels/{channel_id}/members', { items: [], nextCursor: null })
  auth.members([aWorkspaceMember({ id: PROFILE.id, displayName: 'Ada Lovelace' })])
}

const yourName = (name = 'Ada Lovelace') => screen.findByRole('link', { name })
const nameField = () => screen.findByRole('textbox', { name: 'Display name' })
const type = (field: HTMLElement, value: string) => fireEvent.change(field, { target: { value } })
const patches = () => requests().filter((r) => r.method === 'PATCH')

function deferred() {
  let resolve!: () => void
  const promise = new Promise<void>((r) => {
    resolve = r
  })
  return { promise, resolve }
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  window.sessionStorage.clear()
})

describe('App — /settings', () => {
  it('shows Settings on a direct load, from the server', async () => {
    aReturningUser()
    // The session reads the profile once to sign in; the page must read it again.
    let reads = 0
    auth.me(() => ({ ...PROFILE, displayName: ++reads === 1 ? 'Ada Lovelace' : 'Ada L.' }))
    auth.preferences({ clock: '24h' })

    renderWithProviders(<App />, { route: '/settings' })

    expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Profile' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Preferences' })).toBeInTheDocument()
    expect(await nameField()).toHaveValue('Ada L.')
    await vi.waitFor(() => expect(screen.getByRole('radio', { name: '24-hour' })).toBeChecked())
    // Inside the shell: the sidebar is still there.
    expect(screen.getByRole('link', { name: 'Ada Lovelace' })).toBeInTheDocument()
  })

  it('clicking your name opens Settings', async () => {
    aReturningUser()

    const { user, location } = renderWithProviders(<App />, { route: '/' })
    await user.click(await yourName())

    expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument()
    expect(location().pathname).toBe('/settings')
  })

  it('a signed-out visitor to /settings is asked to sign in, and the path is kept', async () => {
    aFirstVisit()
    const assign = vi.fn()
    vi.stubGlobal('location', { ...window.location, assign })

    const { user, location } = renderWithProviders(<App />, { route: '/settings' })
    await user.click(await screen.findByRole('button', { name: 'Sign in' }))

    expect(location().pathname).toBe('/sign-in')
    await vi.waitFor(() => expect(assign).toHaveBeenCalledOnce())
    expect(window.sessionStorage.getItem(RETURN_KEY)).toBe('/settings')
  })

  it('the callback lands on the kept path', async () => {
    aReturningUser()
    auth.exchange(PAIR)
    window.sessionStorage.setItem(VERIFIER_KEY, 'the-verifier')
    window.sessionStorage.setItem(RETURN_KEY, '/settings')

    const { location } = renderWithProviders(<App />, { route: '/auth/callback?code=abc' })

    await vi.waitFor(() => expect(location().pathname).toBe('/settings'))
    expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument()
    expect(window.sessionStorage.getItem(RETURN_KEY)).toBeNull()
  })

  describe('Back to chat', () => {
    /** Open #general, then your name, so the last channel is known and Settings is showing. */
    async function openChannelThenSettings(workspaces = WORKSPACES) {
      aReturningUser(workspaces)
      aChannelToOpen()
      const view = renderWithProviders(<App />, { route: `/c/${CHANNEL_ID}` })
      await screen.findByText('the engine hums')
      await view.user.click(await yourName())
      await screen.findByRole('heading', { name: 'Settings' })
      return view
    }

    it('returns to the last channel in this workspace', async () => {
      const { user, location } = await openChannelThenSettings()

      await user.click(screen.getByRole('link', { name: 'Back to chat' }))

      expect(location().pathname).toBe(`/c/${CHANNEL_ID}`)
      expect(await screen.findByText('the engine hums')).toBeInTheDocument()
    })

    it('returns to the start after a workspace switch', async () => {
      auth.switchWorkspace(AWAY_PAIR)
      const { user, location } = await openChannelThenSettings(TWO_WORKSPACES)
      await user.click(screen.getByRole('button', { name: 'Away' }))
      // The switch landed: the other workspace is now the one to offer.
      await vi.waitFor(() => expect(screen.getByRole('button', { name: 'CollabHub' })).toBeEnabled())

      await user.click(screen.getByRole('link', { name: 'Back to chat' }))

      expect(location().pathname).toBe('/')
    })

    it('returns to the start when no channel was opened', async () => {
      aReturningUser()
      const { user, location } = renderWithProviders(<App />, { route: '/settings' })

      await user.click(await screen.findByRole('link', { name: 'Back to chat' }))

      expect(location().pathname).toBe('/')
      expect(await screen.findByText('Pick a channel, or create one.')).toBeInTheDocument()
    })
  })

  it('a save still lands after leaving mid-save', async () => {
    aReturningUser()
    const commit = deferred()
    auth.updateMe(async ({ body }) => {
      await commit.promise
      return { ...PROFILE, displayName: (body as { displayName: string }).displayName }
    })
    const { user, location } = renderWithProviders(<App />, { route: '/settings' })
    type(await nameField(), 'Ada L.')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await vi.waitFor(() => expect(patches()).toHaveLength(1))

    await user.click(screen.getByRole('link', { name: 'Back to chat' }))
    expect(location().pathname).toBe('/')
    // Still the old name: the save has not been answered.
    expect(screen.getByRole('link', { name: 'Ada Lovelace' })).toBeInTheDocument()

    await act(async () => commit.resolve())

    expect(await yourName('Ada L.')).toBeInTheDocument()
  })

  it('leaving with an unsaved edit drops it without asking', async () => {
    aReturningUser()
    const confirm = vi.spyOn(window, 'confirm')
    const { user } = renderWithProviders(<App />, { route: '/settings' })
    const field = await nameField()
    type(field, 'Ada Unsaved')
    expect(field).toHaveValue('Ada Unsaved')

    await user.click(screen.getByRole('link', { name: 'Back to chat' }))
    await user.click(await yourName())

    expect(await nameField()).toHaveValue('Ada Lovelace')
    expect(confirm).not.toHaveBeenCalled()
  })

  it('a workspace switch on Settings changes nothing', async () => {
    aReturningUser(TWO_WORKSPACES)
    auth.preferences({ clock: '24h' })
    auth.switchWorkspace(AWAY_PAIR)
    const { user, location } = renderWithProviders(<App />, { route: '/settings' })
    type(await nameField(), 'Ada Unsaved')
    await vi.waitFor(() => expect(screen.getByRole('radio', { name: '24-hour' })).toBeChecked())

    await user.click(screen.getByRole('button', { name: 'Away' }))
    await vi.waitFor(() => expect(screen.getByRole('button', { name: 'CollabHub' })).toBeEnabled())

    expect(requests().some((r) => r.url.pathname.endsWith('/switch-workspace'))).toBe(true)
    expect(location().pathname).toBe('/settings')
    expect(screen.getByRole('textbox', { name: 'Display name' })).toHaveValue('Ada Unsaved')
    expect(screen.getByRole('radio', { name: '24-hour' })).toBeChecked()
    expect(screen.getByRole('link', { name: 'Ada Lovelace' })).toBeInTheDocument()
  })
})
