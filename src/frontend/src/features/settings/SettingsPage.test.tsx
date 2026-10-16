/**
 * The Settings page: the Profile form and the clock (issue gh-3, Req 1, 7, 8).
 *
 * Auth is a small stateful stub — the name and the preferences it holds, and the
 * routes that change them — so what the page reads back after a save is what a
 * server would answer. A test holds a response with a deferred promise to look at
 * the screen between request and reply.
 *
 * The markup is queried by role, label and text: a heading `Settings`, a
 * `Profile` region with a `Display name` textbox, `Save` and a `Saved` status; a
 * `Clock` group of `Automatic`, `12-hour` and `24-hour` radios whose error is an
 * alert; and a `Back to chat` link.
 */

import { screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Preferences, Profile } from '../../lib/auth/api'
import { auth, requests } from '../../test/api'
import { createTestQueryClient, renderWithProviders } from '../../test/render'
import { SettingsPage } from './SettingsPage'

const ADA: Profile = {
  id: 'user-ada',
  email: 'ada@collabhub.dev',
  displayName: 'ada',
  avatarAsset: null,
}

/** What Auth holds, and the four routes that read and change it. */
function serverHolds(initial: { name?: string; prefs?: Preferences } = {}) {
  const state = { name: initial.name ?? 'ada', prefs: initial.prefs ?? ({} as Preferences) }
  auth.meBy(() => ({ ...ADA, displayName: state.name }))
  auth.updateMe(({ displayName }) => {
    state.name = displayName
    return { ...ADA, displayName }
  })
  auth.preferences(() => state.prefs)
  auth.updatePreferences((patch) => {
    state.prefs = patch.clock ? { clock: patch.clock } : {}
    return state.prefs
  })
  return state
}

function deferred<T = void>() {
  let release!: (value: T) => void
  const promise = new Promise<T>((resolve) => {
    release = resolve
  })
  return { promise, release }
}

const nameBox = () => screen.findByRole('textbox', { name: 'Display name' })
const saveButton = () => screen.getByRole('button', { name: 'Save' })
const radio = (name: string) => screen.getByRole('radio', { name })
const gets = (path: string) =>
  requests().filter((r) => r.method === 'GET' && r.url.pathname === path)
const patches = (path: string) =>
  requests().filter((r) => r.method === 'PATCH' && r.url.pathname === path)

describe('SettingsPage — the Profile', () => {
  it('prefills the name the server has, not the session’s', async () => {
    const reply = deferred<void>()
    const state = serverHolds({ name: 'Ada L' })
    auth.meBy(async () => {
      await reply.promise
      return { ...ADA, displayName: state.name }
    })
    const queryClient = createTestQueryClient()
    queryClient.setQueryData(['profile', 'me'], { ...ADA, displayName: 'Old' })

    renderWithProviders(<SettingsPage accessToken="token" />, { queryClient })

    expect(screen.getByRole('heading', { name: 'Settings' })).toBeInTheDocument()
    // The server has not answered: the cached "Old" must not be offered as the value.
    await new Promise((resolve) => setTimeout(resolve, 30))
    expect(screen.queryByDisplayValue('Old')).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'Display name' })).not.toBeInTheDocument()

    reply.release()
    expect(await nameBox()).toHaveValue('Ada L')
    expect(screen.queryByDisplayValue('Old')).not.toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Profile' })).toBeInTheDocument()
    expect(gets('/api/v1/users/me')).toHaveLength(1)
  })

  it('offers Save only for a changed, valid name', async () => {
    serverHolds({ name: 'Ada L' })
    const { user } = renderWithProviders(<SettingsPage accessToken="token" />)
    const input = await nameBox()
    const type = async (text: string) => {
      await user.clear(input)
      await user.paste(text)
    }

    // The name it has: nothing to save.
    expect(saveButton()).toBeDisabled()
    // The same name with trailing spaces is still the same name.
    await type('Ada L   ')
    expect(saveButton()).toBeDisabled()
    // Capitals alone are a change.
    await type('ADA L')
    expect(saveButton()).toBeEnabled()
    // Nothing but spaces is empty once trimmed.
    await type('   ')
    expect(saveButton()).toBeDisabled()
    // One past the limit, and the limit itself.
    await type('x'.repeat(101))
    expect(saveButton()).toBeDisabled()
    await type('x'.repeat(100))
    expect(saveButton()).toBeEnabled()
  })

  it('shows a taken name on the field and keeps what was typed', async () => {
    serverHolds()
    auth.problem('patch', '/api/v1/users/me', 409, {
      title: 'Conflict',
      detail: 'That name is already taken.',
      errors: { displayName: ['That name is already taken.'] },
    })
    const { user } = renderWithProviders(<SettingsPage accessToken="token" />)
    const input = await nameBox()

    await user.clear(input)
    await user.type(input, 'grace')
    await user.click(saveButton())

    expect(await screen.findByText('That name is already taken.')).toBeInTheDocument()
    expect(input).toHaveValue('grace')
    expect(screen.queryByText('Saved')).not.toBeInTheDocument()
  })

  it('shows a refused name on the field', async () => {
    serverHolds()
    const message = 'A display name cannot contain control or invisible characters.'
    auth.problem('patch', '/api/v1/users/me', 400, {
      title: 'Validation error',
      detail: message,
      errors: { displayName: [message] },
    })
    const { user } = renderWithProviders(<SettingsPage accessToken="token" />)
    const input = await nameBox()

    await user.clear(input)
    await user.type(input, 'Ada L')
    await user.click(saveButton())

    expect(await screen.findByText(message)).toBeInTheDocument()
    expect(input).toHaveValue('Ada L')
    expect(screen.queryByText('Saved')).not.toBeInTheDocument()
  })

  it('says Saved and makes the new name the baseline', async () => {
    serverHolds()
    const { user } = renderWithProviders(<SettingsPage accessToken="token" />)
    const input = await nameBox()

    await user.clear(input)
    await user.type(input, '  Ada L ')
    await user.click(saveButton())

    expect(await screen.findByRole('status')).toHaveTextContent('Saved')
    // The body is the trimmed name, and nothing else.
    expect(patches('/api/v1/users/me').map((r) => r.body)).toEqual([{ displayName: 'Ada L' }])
    // The saved name is now the one to differ from.
    await vi.waitFor(() => expect(saveButton()).toBeDisabled())

    await user.type(input, 'ovelace')
    expect(screen.queryByText('Saved')).not.toBeInTheDocument()
    expect(saveButton()).toBeEnabled()
  })
})

describe('SettingsPage — the clock', () => {
  it.each([
    ['24-hour', { clock: '24h' }],
    ['12-hour', { clock: '12h' }],
    ['Automatic', {}],
  ] as [string, Preferences][])('shows what the server holds: %s', async (label, prefs) => {
    serverHolds({ prefs })
    renderWithProviders(<SettingsPage accessToken="token" />)

    await vi.waitFor(() => expect(radio(label)).toBeChecked())
    const others = ['Automatic', '12-hour', '24-hour'].filter((name) => name !== label)
    for (const other of others) expect(radio(other)).not.toBeChecked()
    expect(screen.getByRole('group', { name: 'Clock' })).toBeInTheDocument()
  })

  it('saves a choice at once, and Automatic removes it', async () => {
    serverHolds()
    const { user } = renderWithProviders(<SettingsPage accessToken="token" />)
    await vi.waitFor(() => expect(radio('12-hour')).toBeEnabled())

    await user.click(radio('12-hour'))
    await vi.waitFor(() => expect(patches('/api/v1/users/me/preferences')).toHaveLength(1))
    await vi.waitFor(() => expect(radio('12-hour')).toBeChecked())
    await user.click(radio('Automatic'))
    await vi.waitFor(() => expect(patches('/api/v1/users/me/preferences')).toHaveLength(2))

    expect(patches('/api/v1/users/me/preferences').map((r) => r.body)).toEqual([
      { clock: '12h' },
      { clock: null },
    ])
  })

  it('reads the clock from the server on every visit, whatever the cache holds', async () => {
    const reply = deferred<void>()
    serverHolds({ prefs: { clock: '24h' } })
    auth.preferences(async () => {
      await reply.promise
      return { clock: '24h' }
    })
    const queryClient = createTestQueryClient()
    queryClient.setQueryData(['preferences'], { clock: '12h' })

    renderWithProviders(<SettingsPage accessToken="token" />, { queryClient })

    // Until the server has answered the radios are not offered, so a stale
    // "12-hour" can neither be shown as the truth nor be clicked.
    await new Promise((resolve) => setTimeout(resolve, 30))
    for (const name of ['Automatic', '12-hour', '24-hour']) expect(radio(name)).toBeDisabled()

    reply.release()
    await vi.waitFor(() => expect(radio('24-hour')).toBeChecked())
    expect(radio('24-hour')).toBeEnabled()
    expect(radio('12-hour')).not.toBeChecked()
    expect(gets('/api/v1/users/me/preferences')).toHaveLength(1)
  })

  it('puts the choice back and says so when saving fails, then clears the message on success', async () => {
    const state = serverHolds({ prefs: { clock: '12h' } })
    auth.problem('patch', '/api/v1/users/me/preferences', 500, { title: 'Internal error' })
    const { user } = renderWithProviders(<SettingsPage accessToken="token" />)
    await vi.waitFor(() => expect(radio('12-hour')).toBeChecked())
    await vi.waitFor(() => expect(radio('24-hour')).toBeEnabled())

    await user.click(radio('24-hour'))

    const alert = await screen.findByRole('alert')
    expect(alert).not.toBeEmptyDOMElement()
    await vi.waitFor(() => expect(radio('12-hour')).toBeChecked())
    expect(radio('24-hour')).not.toBeChecked()

    // The server works again: the same choice now saves, and the error goes.
    auth.updatePreferences((patch) => {
      state.prefs = patch.clock ? { clock: patch.clock } : {}
      return state.prefs
    })
    await user.click(radio('24-hour'))

    await vi.waitFor(() => expect(radio('24-hour')).toBeChecked())
    await vi.waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
  })
})

describe('SettingsPage — Back to chat', () => {
  it.each([
    ['the channel it came from', { from: '/c/abc' }, '/c/abc'],
    ['the start, when it came from somewhere that is not a channel', { from: '/search' }, '/'],
    ['the start, when it was opened directly', undefined, '/'],
  ])('returns to %s', async (_label, routeState, href) => {
    serverHolds()
    renderWithProviders(<SettingsPage accessToken="token" />, { route: '/settings', routeState })

    expect(await screen.findByRole('link', { name: 'Back to chat' })).toHaveAttribute('href', href)
  })
})

describe('SettingsPage — a workspace switch', () => {
  it('leaves the page as it is: the unsaved edit stays and nothing is fetched again', async () => {
    serverHolds()
    const { user, rerender } = renderWithProviders(<SettingsPage accessToken="token-home" />)
    const input = await nameBox()
    await user.clear(input)
    await user.type(input, 'half a thought')
    await vi.waitFor(() => expect(gets('/api/v1/users/me/preferences')).toHaveLength(1))
    const before = requests().length

    rerender(<SettingsPage accessToken="token-away" />)
    // Let anything the switch would start have started.
    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(screen.getByRole('textbox', { name: 'Display name' })).toHaveValue('half a thought')
    expect(gets('/api/v1/users/me')).toHaveLength(1)
    expect(requests()).toHaveLength(before)
  })
})
