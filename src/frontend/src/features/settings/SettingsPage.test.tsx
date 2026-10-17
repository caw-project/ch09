/**
 * The Settings page, through the app a user meets (issue gh-3 Req 5, 7 and 8).
 *
 * Every test renders `<App />` at a route, with a fresh module each time as
 * `App.test.tsx` does, so the real router, the sign-in guard and the shell are
 * the parent of the page. Auth and Messaging are stubbed at the network edge.
 *
 * **Holding the directory.** The sidebar mounts the workspace directory on this
 * page too, so call 1 is the shell's first fetch and a successful rename makes
 * the next. Each directory test says what every call answers, and pins the cache
 * write *while the post-save refetch is still held*: a build that only
 * invalidates (so the new name arrives with the next refetch, as it does for
 * everyone else) shows the old name during the hold and fails. Calls released
 * afterwards answer the new name, as the server would after the commit.
 *
 * Cache keys are written as literals, so this file loads before the page does.
 */

import type { QueryClient } from '@tanstack/react-query'
import { act, screen } from '@testing-library/react'
import type { UserEvent } from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Preferences, Profile, TokenPair, Workspace, WorkspaceMember } from '../../lib/auth/api'
import { auth, messaging, requests } from '../../test/api'
import { settleDirectory, scriptDirectory } from '../../test/directory'
import { aChannel, aMessagePage, aWorkspaceMember, WORKSPACE_ID } from '../../test/factories'
import { renderWithProviders } from '../../test/render'

type AppModule = typeof import('../../App')

const AWAY_ID = '0199a000-0000-7000-8000-0000000000f1'
const ADA_ID = 'user-ada'
const GRACE_ID = 'user-grace'
const PROFILE: Profile = {
  id: ADA_ID,
  email: 'ada@collabhub.dev',
  displayName: 'Ada Lovelace',
  avatarAsset: null,
}
const HOME: Workspace = { id: WORKSPACE_ID, name: 'CollabHub', role: 'owner' }
const AWAY: Workspace = { id: AWAY_ID, name: 'Elsewhere', role: 'member' }
const TAKEN = 'That name is already taken.'
const INVISIBLE = 'A display name cannot contain invisible or control characters.'

/** An unsigned token carrying a `wsp` claim — the SPA only ever reads it. */
function tokenFor(workspaceId: string): string {
  const payload = btoa(JSON.stringify({ wsp: workspaceId }))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
  return `header.${payload}.signature`
}
const pair = (workspaceId: string): TokenPair => ({
  accessToken: tokenFor(workspaceId),
  tokenType: 'Bearer',
  expiresIn: 900,
})

let App: AppModule['App']

beforeEach(async () => {
  vi.resetModules()
  const module: AppModule = await import('../../App')
  App = module.App
})

const members = (adaName: string): WorkspaceMember[] => [
  aWorkspaceMember({ id: ADA_ID, displayName: adaName }),
  aWorkspaceMember({ id: GRACE_ID, displayName: 'Grace Hopper' }),
]

interface Arrangement {
  /** What the server says Ada is called, from the second `GET /users/me` on. */
  serverName?: string
  prefs?: Preferences
  workspaces?: Workspace[]
}

/** A returning user: session restored, shell stubs, the directory scripted. */
function arrange({ serverName = 'Ada Lovelace', prefs = {}, workspaces = [HOME] }: Arrangement = {}) {
  auth.refresh(pair(WORKSPACE_ID))
  // Call 1 is the sign-in's; the page's own read is call 2 onwards.
  auth.meBy((call) => (call === 1 ? PROFILE : { ...PROFILE, displayName: serverName }))
  auth.workspaces(workspaces)
  auth.preferences(prefs)
  messaging.get('/api/v1/channels', { items: [], nextCursor: null })
  return scriptDirectory({ [WORKSPACE_ID]: members(serverName) })
}

function deferred() {
  let release!: () => void
  const promise = new Promise<void>((resolve) => {
    release = resolve
  })
  return { promise, release }
}

const nameField = () => screen.findByRole('textbox', { name: 'Display name' })
const save = () => screen.getByRole('button', { name: 'Save' })
const sidebarName = (name: string) => screen.findByRole('link', { name })
const renamePatches = () =>
  requests().filter((r) => r.method === 'PATCH' && r.url.pathname === '/api/v1/users/me')
const clockPatches = () =>
  requests().filter((r) => r.method === 'PATCH' && r.url.pathname === '/api/v1/users/me/preferences')
const gets = (path: string) =>
  requests().filter((r) => r.method === 'GET' && r.url.pathname === path)
const adaInDirectory = (queryClient: QueryClient, workspaceId = WORKSPACE_ID) =>
  queryClient
    .getQueryData<WorkspaceMember[]>(['workspace-members', workspaceId])
    ?.find((member) => member.user.id === ADA_ID)?.user.displayName
const graceInDirectory = (queryClient: QueryClient) =>
  queryClient
    .getQueryData<WorkspaceMember[]>(['workspace-members', WORKSPACE_ID])
    ?.find((member) => member.user.id === GRACE_ID)?.user.displayName
const pause = (ms = 50) => act(() => new Promise<void>((resolve) => setTimeout(resolve, ms)))

/** Replace the field's text; `paste` so a 101-letter name is one event, not 101 key presses. */
async function enter(user: UserEvent, input: HTMLElement, value: string) {
  await user.clear(input)
  if (value) {
    await user.click(input)
    await user.paste(value)
  }
}

describe('the page', () => {
  it('shows the server’s name and clock, not the session’s or the cache’s', async () => {
    arrange({ serverName: 'Ada L', prefs: { clock: '24h' } })

    renderWithProviders(<App />, { route: '/settings' })

    // The session was signed in as "Ada Lovelace"; the server now says "Ada L".
    expect(await nameField()).toHaveValue('Ada L')
    expect(await screen.findByRole('heading', { name: 'Profile' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Preferences' })).toBeInTheDocument()
    await vi.waitFor(() => expect(screen.getByRole('radio', { name: '24-hour' })).toBeChecked())
    expect(screen.getByRole('radio', { name: 'Automatic' })).not.toBeChecked()
    expect(screen.getByRole('radio', { name: '12-hour' })).not.toBeChecked()
  })

  it('is reached from the sidebar’s name', async () => {
    arrange()
    const { user, location } = renderWithProviders(<App />, { route: '/' })

    await user.click(await sidebarName('Ada Lovelace'))

    expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument()
    expect(location().pathname).toBe('/settings')
  })

  it('drops an unsaved edit on leaving, without asking', async () => {
    arrange()
    const confirm = vi.spyOn(window, 'confirm')
    const { user, location } = renderWithProviders(<App />, { route: '/settings' })
    await enter(user, await nameField(), 'Ada Draft')
    expect(await nameField()).toHaveValue('Ada Draft')

    await user.click(screen.getByRole('link', { name: 'Back to chat' }))
    await vi.waitFor(() => expect(location().pathname).toBe('/'))
    await user.click(await sidebarName('Ada Lovelace'))

    expect(await nameField()).toHaveValue('Ada Lovelace')
    expect(confirm).not.toHaveBeenCalled()
  })

  it('goes back to the last channel, or home after a direct load', async () => {
    const general = aChannel({ id: 'channel-general', name: 'general' })
    arrange()
    messaging.get('/api/v1/channels', { items: [general], nextCursor: null })
    messaging.get('/api/v1/channels/{channel_id}', general)
    messaging.get('/api/v1/channels/{channel_id}/messages', aMessagePage([]))
    messaging.get('/api/v1/channels/{channel_id}/members', { items: [], nextCursor: null })
    const opened = renderWithProviders(<App />, { route: `/c/${general.id}` })
    await vi.waitFor(() =>
      expect(gets(`/api/v1/channels/${general.id}/messages`).length).toBeGreaterThan(0),
    )

    await opened.user.click(await sidebarName('Ada Lovelace'))
    await opened.user.click(await screen.findByRole('link', { name: 'Back to chat' }))

    await vi.waitFor(() => expect(opened.location().pathname).toBe(`/c/${general.id}`))
    opened.unmount()

    // A direct load has opened no channel, so there is nothing to go back to.
    const direct = renderWithProviders(<App />, { route: '/settings' })
    await direct.user.click(await screen.findByRole('link', { name: 'Back to chat' }))
    await vi.waitFor(() => expect(direct.location().pathname).toBe('/'))
  })
})

describe('Save', () => {
  it('is off while the name is unchanged or invalid, and on for any other', async () => {
    arrange()
    const { user } = renderWithProviders(<App />, { route: '/settings' })
    const input = await nameField()
    expect(save()).toBeDisabled() // unchanged

    await enter(user, input, '   ')
    expect(save()).toBeDisabled()
    await enter(user, input, 'a'.repeat(101))
    expect(save()).toBeDisabled()
    await enter(user, input, '  Ada Lovelace  ')
    expect(save()).toBeDisabled() // the same name once trimmed

    await enter(user, input, 'a'.repeat(100))
    expect(save()).toBeEnabled()
    await enter(user, input, String.fromCodePoint(0x1f600).repeat(100))
    expect(save()).toBeEnabled() // 100 characters, though 200 UTF-16 units
    await enter(user, input, String.fromCodePoint(0x1f600).repeat(101))
    expect(save()).toBeDisabled()
    await enter(user, input, 'Ada L')
    expect(save()).toBeEnabled()
    await enter(user, input, 'ada lovelace')
    expect(save()).toBeEnabled() // changing only the capitals is a change
  })
})

describe('saving the name', () => {
  it('updates the sidebar and the directory at once, and says Saved', async () => {
    const directory = arrange()
    const second = directory.hold(WORKSPACE_ID, 2)
    auth.patchMe((body) => ({ ...PROFILE, displayName: body.displayName }))
    const { user, queryClient } = renderWithProviders(<App />, { route: '/settings' })
    await settleDirectory(queryClient, WORKSPACE_ID)
    expect(directory.requests(WORKSPACE_ID)).toHaveLength(1)
    // From here the server answers with the new name, as it does after the commit.
    directory.now[WORKSPACE_ID] = members('Ada L')

    await enter(user, await nameField(), 'Ada L')
    await user.click(save())

    expect(await screen.findByRole('status')).toHaveTextContent('Saved')
    expect(renamePatches().map((r) => r.body)).toEqual([{ displayName: 'Ada L' }])
    // The refetch after the commit is under way and held: nothing but the
    // mutation's own writes can have put the new name on screen.
    await vi.waitFor(() => expect(directory.requests(WORKSPACE_ID)).toHaveLength(2))
    expect(await sidebarName('Ada L')).toBeInTheDocument()
    expect(adaInDirectory(queryClient)).toBe('Ada L')
    expect(graceInDirectory(queryClient)).toBe('Grace Hopper')

    await second.release(members('Ada L'))
    await settleDirectory(queryClient, WORKSPACE_ID)
    expect(adaInDirectory(queryClient)).toBe('Ada L')
    expect(graceInDirectory(queryClient)).toBe('Grace Hopper')
  })

  it.each([
    [409, TAKEN],
    [400, INVISIBLE],
  ])('shows a %i on the field and changes nothing', async (status, message) => {
    const directory = arrange()
    auth.patchMe(() =>
      auth.refuse(status, { title: 'Refused', detail: message, errors: { displayName: [message] } }),
    )
    const { user, queryClient } = renderWithProviders(<App />, { route: '/settings' })
    await settleDirectory(queryClient, WORKSPACE_ID)

    await enter(user, await nameField(), 'Grace')
    await user.click(save())

    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ada Lovelace' })).toBeInTheDocument()
    expect(adaInDirectory(queryClient)).toBe('Ada Lovelace')
    expect(directory.requests(WORKSPACE_ID)).toHaveLength(1)
  })

  it('still updates the session and the directory when the response lands after leaving', async () => {
    const directory = arrange()
    const second = directory.hold(WORKSPACE_ID, 2)
    const response = deferred()
    auth.patchMe(async (body) => {
      await response.promise
      return { ...PROFILE, displayName: body.displayName }
    })
    const { user, queryClient } = renderWithProviders(<App />, { route: '/settings' })
    await settleDirectory(queryClient, WORKSPACE_ID)
    directory.now[WORKSPACE_ID] = members('Ada L')
    await enter(user, await nameField(), 'Ada L')
    await user.click(save())
    await vi.waitFor(() => expect(renamePatches()).toHaveLength(1))

    await user.click(screen.getByRole('link', { name: 'Back to chat' }))
    await vi.waitFor(() => expect(screen.queryByRole('heading', { name: 'Settings' })).toBeNull())
    response.release()

    expect(await sidebarName('Ada L')).toBeInTheDocument()
    // The refetch after the commit is held, so only the mutation’s own write can satisfy this.
    await vi.waitFor(() => expect(adaInDirectory(queryClient)).toBe('Ada L'))
    await second.release(members('Ada L'))
  })

  it('is not undone by a refetch that was already in flight with the old name', async () => {
    const directory = arrange()
    const inFlight = directory.hold(WORKSPACE_ID, 2)
    const afterSave = directory.hold(WORKSPACE_ID, 3)
    auth.patchMe((body) => ({ ...PROFILE, displayName: body.displayName }))
    const { user, queryClient } = renderWithProviders(<App />, { route: '/settings' })
    await settleDirectory(queryClient, WORKSPACE_ID)
    act(() => {
      void queryClient.refetchQueries({ queryKey: ['workspace-members', WORKSPACE_ID] })
    })
    await vi.waitFor(() => expect(directory.requests(WORKSPACE_ID)).toHaveLength(2))
    directory.now[WORKSPACE_ID] = members('Ada L')

    await enter(user, await nameField(), 'Ada L')
    await user.click(save())

    await vi.waitFor(() => expect(directory.requests(WORKSPACE_ID)).toHaveLength(3))
    expect(adaInDirectory(queryClient)).toBe('Ada L')
    await inFlight.release(members('Ada Lovelace'))
    expect(adaInDirectory(queryClient)).toBe('Ada L')
    await afterSave.release(members('Ada L'))
    await settleDirectory(queryClient, WORKSPACE_ID)
    expect(adaInDirectory(queryClient)).toBe('Ada L')
  })

  it('is not undone by a first directory fetch that is still out with the old name', async () => {
    const directory = arrange()
    const first = directory.hold(WORKSPACE_ID, 1)
    directory.answer(WORKSPACE_ID, 2, members('Ada L'))
    auth.patchMe((body) => ({ ...PROFILE, displayName: body.displayName }))
    const { user, queryClient } = renderWithProviders(<App />, { route: '/settings' })
    await vi.waitFor(() => expect(directory.requests(WORKSPACE_ID)).toHaveLength(1))
    // Nothing is cached yet: an invalidate would join this very fetch.
    expect(queryClient.getQueryData(['workspace-members', WORKSPACE_ID])).toBeUndefined()
    directory.now[WORKSPACE_ID] = members('Ada L')

    await enter(user, await nameField(), 'Ada L')
    await user.click(save())
    expect(await screen.findByRole('status')).toHaveTextContent('Saved')
    await first.release(members('Ada Lovelace'))

    await settleDirectory(queryClient, WORKSPACE_ID)
    expect(adaInDirectory(queryClient)).toBe('Ada L')
  })
})

describe('the workspace switch', () => {
  it('changes nothing on the page: the draft and the clock stay, and nothing is refetched', async () => {
    arrange({ prefs: { clock: '24h' }, workspaces: [HOME, AWAY] })
    auth.switchWorkspace(pair(AWAY_ID))
    const { user } = renderWithProviders(<App />, { route: '/settings' })
    await enter(user, await nameField(), 'Ada Draft')
    await vi.waitFor(() => expect(screen.getByRole('radio', { name: '24-hour' })).toBeChecked())
    await pause()
    const meBefore = gets('/api/v1/users/me').length
    const prefsBefore = gets('/api/v1/users/me/preferences').length

    await user.click(screen.getByRole('button', { name: 'Elsewhere' }))
    await vi.waitFor(() =>
      expect(requests().filter((r) => r.url.pathname === '/api/v1/auth/switch-workspace')).toHaveLength(1),
    )
    // The switch re-reads `me` once, for the session; the page asks for nothing.
    await vi.waitFor(() => expect(gets('/api/v1/users/me')).toHaveLength(meBefore + 1))
    await pause()

    expect(gets('/api/v1/users/me')).toHaveLength(meBefore + 1)
    expect(gets('/api/v1/users/me/preferences')).toHaveLength(prefsBefore)
    expect(await nameField()).toHaveValue('Ada Draft')
    expect(screen.getByRole('radio', { name: '24-hour' })).toBeChecked()
  })
})

describe('the clock', () => {
  it('saves at once when chosen, and back to automatic with null', async () => {
    arrange()
    auth.patchPreferences((body) => (body.clock ? { clock: body.clock } : {}))
    const { user } = renderWithProviders(<App />, { route: '/settings' })

    await user.click(await screen.findByRole('radio', { name: '24-hour' }))
    await vi.waitFor(() => expect(clockPatches()).toHaveLength(1))
    expect(screen.getByRole('radio', { name: '24-hour' })).toBeChecked()

    await user.click(screen.getByRole('radio', { name: 'Automatic' }))
    await vi.waitFor(() => expect(clockPatches()).toHaveLength(2))
    expect(clockPatches().map((r) => r.body)).toEqual([{ clock: '24h' }, { clock: null }])
    expect(screen.getByRole('radio', { name: 'Automatic' })).toBeChecked()
  })

  it('puts the previous clock back when the save fails, and says why', async () => {
    arrange({ prefs: { clock: '12h' } })
    auth.patchPreferences(() =>
      auth.refuse(500, { title: 'Internal error', detail: 'The clock could not be saved.' }),
    )
    const { user } = renderWithProviders(<App />, { route: '/settings' })
    await vi.waitFor(() => expect(screen.getByRole('radio', { name: '12-hour' })).toBeChecked())

    await user.click(screen.getByRole('radio', { name: '24-hour' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('The clock could not be saved.')
    expect(screen.getByRole('radio', { name: '12-hour' })).toBeChecked()
    expect(screen.getByRole('radio', { name: '24-hour' })).not.toBeChecked()
  })

  it('sends a second choice only after the first has reached the server', async () => {
    arrange()
    const first = deferred()
    const second = deferred()
    auth.patchPreferences(async (body) => {
      await (body.clock === '24h' ? first : second).promise
      return { clock: body.clock ?? undefined }
    })
    const { user } = renderWithProviders(<App />, { route: '/settings' })

    await user.click(await screen.findByRole('radio', { name: '24-hour' }))
    await vi.waitFor(() => expect(clockPatches()).toHaveLength(1))
    await user.click(screen.getByRole('radio', { name: '12-hour' }))

    // The tab shows the newest choice at once; the server hears of it later.
    expect(screen.getByRole('radio', { name: '12-hour' })).toBeChecked()
    await pause()
    expect(clockPatches()).toHaveLength(1)

    first.release()
    await vi.waitFor(() => expect(clockPatches()).toHaveLength(2))
    expect(clockPatches().map((r) => r.body)).toEqual([{ clock: '24h' }, { clock: '12h' }])
    // The first answer says 24h, but the choice since is 12h: it must not win.
    expect(screen.getByRole('radio', { name: '12-hour' })).toBeChecked()
    second.release()
    await pause()
    expect(screen.getByRole('radio', { name: '12-hour' })).toBeChecked()
  })

  it('is not undone by a late failure of an older choice', async () => {
    arrange()
    const first = deferred()
    const second = deferred()
    auth.patchPreferences(async (body) => {
      if (body.clock === '24h') {
        await first.promise
        return auth.refuse(500, { title: 'Internal error', detail: 'The clock could not be saved.' })
      }
      await second.promise
      return { clock: body.clock ?? undefined }
    })
    const { user } = renderWithProviders(<App />, { route: '/settings' })

    await user.click(await screen.findByRole('radio', { name: '24-hour' }))
    await vi.waitFor(() => expect(clockPatches()).toHaveLength(1))
    await user.click(screen.getByRole('radio', { name: '12-hour' }))
    first.release()
    await vi.waitFor(() => expect(clockPatches()).toHaveLength(2))

    // The older choice failed; the newer one is still the user’s, and not yet saved.
    expect(screen.getByRole('radio', { name: '12-hour' })).toBeChecked()
    second.release()
    await pause()
    expect(screen.getByRole('radio', { name: '12-hour' })).toBeChecked()
  })
})
