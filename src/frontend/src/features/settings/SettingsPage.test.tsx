/**
 * The Settings page (issue gh-3, Req 8 and Req 7's save and revert).
 *
 * Auth is stubbed at the network edge and the hooks run for real. Everything is
 * found by role, label or text; the page's `data-testid`s belong to the BDD suite.
 * The Save rule is about the name in the field after `trim().normalize('NFC')`: it
 * is disabled for a name that is unchanged or impossible, and enabled for one that
 * is changed and possible — both halves are here, so neither can pass by Save
 * being always off.
 */

import { fireEvent, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Preferences, Profile, WorkspaceMember } from '../../lib/auth/api'
import * as session from '../../lib/auth/session'
import { useChatStore } from '../../stores/chat'
import { auth, Refusal, requests } from '../../test/api'
import { aWorkspaceMember } from '../../test/factories'
import { createTestQueryClient, renderWithProviders } from '../../test/render'
import { SettingsPage } from './SettingsPage'

const PROFILE: Profile = {
  id: '0199a000-0000-7000-8000-000000000001',
  email: 'ada@collabhub.dev',
  displayName: 'ada',
  avatarAsset: null,
}
const TAKEN = 'That name is already taken.'

const patches = (path: string) =>
  requests().filter((r) => r.method === 'PATCH' && r.url.pathname === path)

function deferred() {
  let release!: () => void
  const promise = new Promise<void>((resolve) => {
    release = resolve
  })
  return { promise, release }
}

/** The page, with the server holding `profile` and `stored` unless a test stubbed more. */
function renderPage(profile: Profile = PROFILE, stored: Preferences = {}) {
  auth.me(profile)
  auth.preferencesBy(() => ({ ...stored }))
  const view = renderWithProviders(<SettingsPage accessToken="token" />, { route: '/settings' })
  return view
}

const nameField = () => screen.findByRole('textbox', { name: 'Display name' })
const save = () => screen.getByRole('button', { name: 'Save' })
const radio = (name: string) => screen.getByRole('radio', { name })

function typeName(field: HTMLElement, value: string) {
  // `fireEvent`, not typing: a 120-unit emoji string and a 101-character one are
  // inputs, not keystrokes.
  fireEvent.change(field, { target: { value } })
}

describe('SettingsPage — what it shows', () => {
  it('shows only what this visit fetched, never a cached copy', async () => {
    const queryClient = createTestQueryClient()
    queryClient.setQueryData(['profile', 'me'], { ...PROFILE, displayName: 'Old' })
    queryClient.setQueryData(['preferences'], { clock: '12h' })
    const held = deferred()
    auth.meBy(async () => {
      await held.promise
      return PROFILE
    })
    auth.preferences({ clock: '24h' })

    renderWithProviders(<SettingsPage accessToken="token" />, { route: '/settings', queryClient })

    await vi.waitFor(() => expect(requests().length).toBeGreaterThanOrEqual(1))
    await new Promise((resolve) => setTimeout(resolve, 25))
    expect(screen.queryByRole('textbox', { name: 'Display name' })).not.toBeInTheDocument()
    expect(screen.queryByDisplayValue('Old')).not.toBeInTheDocument()

    held.release()

    expect(await nameField()).toHaveValue('ada')
    await vi.waitFor(() => expect(radio('24-hour')).toBeChecked())
  })

  it('has a Profile and a Preferences section under a Settings heading', async () => {
    renderPage()
    await nameField()

    expect(screen.getByRole('heading', { name: 'Settings' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Profile' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Preferences' })).toBeInTheDocument()
    expect(screen.getByRole('radiogroup', { name: 'Clock' })).toBeInTheDocument()
  })

  it('checks Automatic when no clock is stored, and the stored one when there is', async () => {
    renderPage(PROFILE, {})
    await nameField()
    await vi.waitFor(() => expect(radio('Automatic')).toBeChecked())
    expect(radio('12-hour')).not.toBeChecked()
    expect(radio('24-hour')).not.toBeChecked()
  })

  it.each([
    ['Back to chat goes to the last channel', 'c1', '/c/c1'],
    ['Back to chat goes home when there is none', null, '/'],
  ])('%s', async (_, lastChannelId, href) => {
    useChatStore.setState({ lastChannelId })
    renderPage()
    await nameField()

    expect(screen.getByRole('link', { name: 'Back to chat' })).toHaveAttribute('href', href)
  })
})

describe('SettingsPage — the Save rule', () => {
  it.each([
    ['unchanged', 'ada'],
    ['the same after trimming', ' ada '],
    ['only whitespace', '   '],
    ['empty', ''],
    ['101 characters', 'x'.repeat(101)],
  ])('disables Save for a name that is %s', async (_, typed) => {
    renderPage()
    typeName(await nameField(), typed)

    expect(save()).toBeDisabled()
  })

  it.each([
    ['100 characters', 'x'.repeat(100)],
    ['60 emoji, which are 120 UTF-16 units but 60 characters', '😀'.repeat(60)],
    ['a change of capitals only', 'Ada'],
    ['a longer name', 'Ada Lovelace'],
  ])('enables Save for a name that is %s', async (_, typed) => {
    renderPage()
    typeName(await nameField(), typed)

    expect(save()).toBeEnabled()
  })

  it('treats a typed decomposed form as the stored composed one: unchanged', async () => {
    const jose = 'Jos' + String.fromCharCode(0xe9)
    renderPage({ ...PROFILE, displayName: jose })
    const field = await nameField()
    expect(save()).toBeDisabled()

    typeName(field, 'Jose' + String.fromCharCode(0x301))

    expect(save()).toBeDisabled()
    typeName(field, 'Josep')
    expect(save()).toBeEnabled()
  })
})

describe('SettingsPage — saving the name', () => {
  it('shows a name already taken on the field, and keeps what was typed', async () => {
    auth.problem('patch', '/api/v1/users/me', 409, {
      title: 'Conflict',
      detail: TAKEN,
      errors: { displayName: [TAKEN] },
    })
    const { user } = renderPage()
    const field = await nameField()
    typeName(field, 'GRACE')

    await user.click(save())

    expect(await screen.findByRole('alert')).toHaveTextContent(TAKEN)
    expect(field).toHaveValue('GRACE')
    expect(patches('/api/v1/users/me').map((r) => r.body)).toEqual([{ displayName: 'GRACE' }])
    expect(screen.queryByText('Saved')).not.toBeInTheDocument()
  })

  it('shows a refused name on the field', async () => {
    const reason = 'A display name cannot contain invisible or control characters.'
    auth.problem('patch', '/api/v1/users/me', 400, {
      title: 'Validation error',
      detail: reason,
      errors: { displayName: [reason] },
    })
    const { user } = renderPage()
    typeName(await nameField(), 'Grace' + String.fromCharCode(0x200b))

    await user.click(save())

    expect(await screen.findByRole('alert')).toHaveTextContent(reason)
  })

  it('says Saved after a success, and stops saying it on the next edit', async () => {
    auth.updateMe((body) => ({ ...PROFILE, displayName: body.displayName ?? '' }))
    const { user } = renderPage()
    const field = await nameField()
    expect(screen.queryByText('Saved')).not.toBeInTheDocument()
    typeName(field, 'Ada L')

    await user.click(save())

    expect(await screen.findByText('Saved')).toBeInTheDocument()
    expect(patches('/api/v1/users/me').map((r) => r.body)).toEqual([{ displayName: 'Ada L' }])

    typeName(field, 'Ada Lo')
    expect(screen.queryByText('Saved')).not.toBeInTheDocument()
  })

  it('a saved rename reaches the session and the cached directory, and only the renamer', async () => {
    // Req 5: the page must save through the rename that writes the session profile and
    // the directories. A page with a mutation of its own that writes only the profile
    // query passes every other test here and leaves the sidebar and the renamer's own
    // message authors showing different names.
    const WS = '0199a000-0000-7000-8000-00000000aaa0'
    const token = 'header.' + btoa(JSON.stringify({ wsp: WS })).replace(/=+$/, '') + '.signature'
    auth.me(PROFILE)
    auth.workspaces([{ id: WS, name: 'A', role: 'owner' }])
    auth.refresh({ accessToken: token, tokenType: 'Bearer', expiresIn: 900 })
    await session.restore()
    auth.updateMe((body) => ({ ...PROFILE, displayName: body.displayName ?? '' }))
    const grace = aWorkspaceMember({
      id: '0199a000-0000-7000-8000-000000000002',
      displayName: 'Grace Hopper',
    })
    const queryClient = createTestQueryClient()
    queryClient.setQueryData(
      ['workspace-members', WS],
      [aWorkspaceMember({ id: PROFILE.id, displayName: 'ada' }), grace],
    )
    auth.preferencesBy(() => ({}))
    const { user } = renderWithProviders(<SettingsPage accessToken={token} />, {
      route: '/settings',
      queryClient,
    })
    typeName(await nameField(), 'Ada L')

    await user.click(save())

    expect(await screen.findByText('Saved')).toBeInTheDocument()
    const state = session.snapshot()
    expect(state.status === 'signedIn' ? state.session.profile.displayName : undefined).toBe('Ada L')
    const members = queryClient.getQueryData<WorkspaceMember[]>(['workspace-members', WS]) ?? []
    expect(Object.fromEntries(members.map((m) => [m.user.id, m.user.displayName]))).toEqual({
      [PROFILE.id]: 'Ada L',
      [grace.user.id]: 'Grace Hopper',
    })
  })

  it('shows no error and no Saved before anything is done', async () => {
    renderPage()
    await nameField()

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByText('Saved')).not.toBeInTheDocument()
  })
})

describe('SettingsPage — the clock', () => {
  const PATH = '/api/v1/users/me/preferences'

  function renderWithClock(initial: Preferences) {
    let stored: Preferences = { ...initial }
    auth.me(PROFILE)
    auth.preferencesBy(() => ({ ...stored }))
    auth.updatePreferencesBy(async (_call, body) => {
      stored = body.clock === null ? {} : { ...stored, ...body }
      return { ...stored }
    })
    return renderWithProviders(<SettingsPage accessToken="token" />, { route: '/settings' })
  }

  it('saves a chosen clock at once', async () => {
    const { user } = renderWithClock({})
    await nameField()
    await vi.waitFor(() => expect(radio('Automatic')).toBeChecked())

    await user.click(radio('24-hour'))

    await vi.waitFor(() => expect(patches(PATH)).toHaveLength(1))
    expect(patches(PATH)[0].body).toEqual({ clock: '24h' })
    expect(radio('24-hour')).toBeChecked()
  })

  it('saves Automatic as null', async () => {
    const { user } = renderWithClock({ clock: '24h' })
    await nameField()
    await vi.waitFor(() => expect(radio('24-hour')).toBeChecked())

    await user.click(radio('Automatic'))

    await vi.waitFor(() => expect(patches(PATH)).toHaveLength(1))
    expect(patches(PATH)[0].body).toEqual({ clock: null })
    expect(radio('Automatic')).toBeChecked()
  })

  it('puts the previous choice back when a save fails, and shows the error', async () => {
    auth.me(PROFILE)
    auth.preferencesBy(() => ({ clock: '12h' }))
    auth.updatePreferencesBy(
      () => new Refusal(500, { title: 'Internal error', detail: 'Could not save that.' }),
    )
    const { user } = renderWithProviders(<SettingsPage accessToken="token" />, {
      route: '/settings',
    })
    await nameField()
    await vi.waitFor(() => expect(radio('12-hour')).toBeChecked())

    await user.click(radio('24-hour'))

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not save that.')
    await vi.waitFor(() => expect(radio('12-hour')).toBeChecked())
    expect(radio('24-hour')).not.toBeChecked()
  })
})

describe('SettingsPage — a new token', () => {
  it('leaves an unsaved edit alone and fetches nothing', async () => {
    const { rerender } = renderPage()
    const field = await nameField()
    await vi.waitFor(() => expect(radio('Automatic')).toBeChecked())
    typeName(field, 'Unsaved edit')
    const before = requests().length

    // A workspace switch hands the page another token; the name and the clock are per user.
    rerender(<SettingsPage accessToken="another-token" />)
    await new Promise((resolve) => setTimeout(resolve, 25))

    expect(screen.getByRole('textbox', { name: 'Display name' })).toHaveValue('Unsaved edit')
    expect(requests()).toHaveLength(before)
  })
})
