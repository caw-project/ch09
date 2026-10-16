/**
 * Switching workspace, through the shell the app really mounts (doc 06 §4).
 *
 * A token is scoped to one workspace, so a switch must drop the connection that
 * token opened and must never show the old workspace's cached data. The session
 * is the real store, switched the way the switcher switches it; Auth and
 * Messaging are stubbed at the network edge and the socket is the fake.
 */

import { screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Profile, TokenPair, Workspace } from '../../lib/auth/api'
import * as session from '../../lib/auth/session'
import { useSession } from '../../lib/auth/useSession'
import { auth, messaging } from '../../test/api'
import { settleDirectory } from '../../test/directory'
import { aChannel, aMessage, aMessagePage, aWorkspaceMember } from '../../test/factories'
import { renderWithProviders } from '../../test/render'
import { latestSocket, openedSockets } from '../../test/socket'
import { ChannelView } from './ChannelView'
import { ChatLayout } from './ChatLayout'

const HOME = '0199a000-0000-7000-8000-0000000000a1'
const AWAY = '0199a000-0000-7000-8000-0000000000a2'

const PROFILE: Profile = {
  id: 'user-ada',
  email: 'ada@collabhub.dev',
  displayName: 'Ada Lovelace',
  avatarAsset: null,
}
const WORKSPACES: Workspace[] = [
  { id: HOME, name: 'Home', role: 'owner' },
  { id: AWAY, name: 'Away', role: 'member' },
]

/** An unsigned token carrying a `wsp` claim — the SPA only ever reads it. */
function tokenFor(workspaceId: string): string {
  const payload = btoa(JSON.stringify({ wsp: workspaceId }))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
  return `header.${payload}.signature`
}

function pair(workspaceId: string): TokenPair {
  return { accessToken: tokenFor(workspaceId), tokenType: 'Bearer', expiresIn: 900 }
}

const homeChannel = aChannel({ name: 'general' })
const awayChannel = aChannel({ name: 'design' })

function isAway(request: Request): boolean {
  return request.headers.get('Authorization') === `Bearer ${tokenFor(AWAY)}`
}

/** What `App`'s guard renders for a signed-in user, minus the routing. */
function SignedInShell() {
  const state = useSession()
  if (state.status !== 'signedIn') return null
  return (
    <ChatLayout current={state.session}>
      <p>content</p>
    </ChatLayout>
  )
}

beforeEach(async () => {
  auth.me(PROFILE)
  auth.workspaces(WORKSPACES)
  auth.refresh(pair(HOME))
  await session.restore()
  auth.switchWorkspace(pair(AWAY))
})

describe('ChatLayout — switching workspace', () => {
  it('closes the old socket and connects with the new workspace’s token', async () => {
    messaging.get('/api/v1/channels', ({ request }) => ({
      items: isAway(request) ? [awayChannel] : [homeChannel],
      nextCursor: null,
    }))
    const { user } = renderWithProviders(<SignedInShell />)
    await screen.findByRole('link', { name: 'general' })
    const homeSocket = latestSocket()
    expect(homeSocket.accessToken).toBe(tokenFor(HOME))

    await user.click(screen.getByRole('button', { name: 'Away' }))

    await vi.waitFor(() => expect(latestSocket().accessToken).toBe(tokenFor(AWAY)))
    expect(homeSocket.closed).toBe(true)
    expect(openedSockets().filter((socket) => !socket.closed)).toEqual([latestSocket()])
  })

  it('never shows the old workspace’s channels, even while the new list loads', async () => {
    let release!: () => void
    const awayListHeld = new Promise<void>((resolve) => {
      release = resolve
    })
    messaging.get('/api/v1/channels', async ({ request }) => {
      if (!isAway(request)) return { items: [homeChannel], nextCursor: null }
      await awayListHeld
      return { items: [awayChannel], nextCursor: null }
    })
    const { user } = renderWithProviders(<SignedInShell />)
    await screen.findByRole('link', { name: 'general' })

    await user.click(screen.getByRole('button', { name: 'Away' }))
    await vi.waitFor(() => expect(latestSocket().accessToken).toBe(tokenFor(AWAY)))

    expect(screen.queryByRole('link', { name: 'general' })).not.toBeInTheDocument()

    release()
    expect(await screen.findByRole('link', { name: 'design' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'general' })).not.toBeInTheDocument()
  })
})

const OPEN = '0199a000-0000-7000-8000-0000000000c1'

/** The shell with the real channel view in it, so an author line is the real one. */
function ShellWithChannel() {
  const state = useSession()
  if (state.status !== 'signedIn') return null
  return (
    <ChatLayout current={state.session}>
      <ChannelView
        accessToken={state.session.accessToken}
        workspaceId={state.session.activeWorkspaceId}
        userId={state.session.profile.id}
      />
    </ChatLayout>
  )
}

/** Messaging with one open channel holding one message by the signed-in user. */
function stubOpenChannel() {
  const channel = aChannel({ id: OPEN, name: 'general' })
  messaging.get('/api/v1/channels', { items: [channel], nextCursor: null })
  messaging.get('/api/v1/channels/{channel_id}', channel)
  messaging.get(
    '/api/v1/channels/{channel_id}/messages',
    aMessagePage([aMessage({ channelId: OPEN, authorId: PROFILE.id, body: 'good morning' })]),
  )
  messaging.get('/api/v1/channels/{channel_id}/members', { items: [], nextCursor: null })
}

describe('ChatLayout — the signed-in name', () => {
  it('links to Settings, remembering the page it left', async () => {
    stubOpenChannel()
    auth.members([aWorkspaceMember({ id: PROFILE.id, displayName: 'Ada Lovelace' })])
    const { user, location } = renderWithProviders(<ShellWithChannel />, {
      route: `/c/${OPEN}`,
      path: '/c/:channelId',
    })

    await user.click(await screen.findByRole('link', { name: 'Ada Lovelace' }))

    expect(location().pathname).toBe('/settings')
    expect(location().state).toMatchObject({ from: `/c/${OPEN}` })
  })

  it('names the user as the directory does, so the sidebar and her own messages agree', async () => {
    stubOpenChannel()
    // Another tab renamed her: the directory has the new name, the session the old one.
    auth.members([aWorkspaceMember({ id: PROFILE.id, displayName: 'Ada L' })])

    renderWithProviders(<ShellWithChannel />, { route: `/c/${OPEN}`, path: '/c/:channelId' })

    // The message row is already so today; the sidebar must come to the same name.
    await screen.findByText('good morning')
    await vi.waitFor(() => expect(screen.getAllByText('Ada L')).toHaveLength(2))
    expect(screen.getByRole('link', { name: 'Ada L' })).toBeInTheDocument()
    expect(screen.queryByText('Ada Lovelace')).not.toBeInTheDocument()
  })

  it('falls back to the session’s name while the directory has no entry for her', async () => {
    stubOpenChannel()
    auth.members([aWorkspaceMember({ displayName: 'Grace Hopper' })])

    const { queryClient } = renderWithProviders(<ShellWithChannel />, {
      route: `/c/${OPEN}`,
      path: '/c/:channelId',
    })
    await screen.findByText('good morning')
    await settleDirectory(queryClient, HOME)

    expect(screen.getByRole('link', { name: 'Ada Lovelace' })).toBeInTheDocument()
  })
})
