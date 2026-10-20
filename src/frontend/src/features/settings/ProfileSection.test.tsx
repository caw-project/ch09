/**
 * The Profile section of `/settings`: rename yourself (issue gh-3, Req 1, 2, 5, 8).
 *
 * The session is module state, so each test imports a fresh one, signs in through
 * the Auth stubs the way the app does, and imports the component after it — the
 * component and the assertions then share one session. Auth is stubbed at the
 * network edge; the directory is the real hook over `scriptDirectory`, so a stale
 * directory answer is a real in-flight request, not a hand-written cache write.
 *
 * Character rules are the server's and are not repeated here: this file proves
 * what the form does with the server's answers.
 */

import { act, fireEvent, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Profile, TokenPair, Workspace } from '../../lib/auth/api'
import { auth, failWith, requests } from '../../test/api'
import { scriptDirectory, settleDirectory } from '../../test/directory'
import { aWorkspaceMember } from '../../test/factories'
import { createTestQueryClient, renderWithProviders } from '../../test/render'
import { directoryKeys, useWorkspaceMembers } from '../channels/useWorkspaceMembers'
import { profileKeys } from './useProfile'

type SessionModule = typeof import('../../lib/auth/session')

const HOME = 'workspace-home'
const AWAY = 'workspace-away'
const TOKEN = 'header.' + btoa(JSON.stringify({ wsp: HOME })).replace(/=+$/, '') + '.signature'
const PAIR: TokenPair = { accessToken: TOKEN, tokenType: 'Bearer', expiresIn: 900 }
const WORKSPACES: Workspace[] = [
  { id: HOME, name: 'Home', role: 'owner' },
  { id: AWAY, name: 'Away', role: 'member' },
]
const PROFILE: Profile = {
  id: 'user-ada',
  email: 'ada@collabhub.dev',
  displayName: 'Ada Lovelace',
  avatarAsset: null,
}

const TAKEN = 'That name is already taken.'
const LENGTH = 'A display name must be 1 to 100 characters.'

const COMBINING_ACUTE = String.fromCodePoint(0x301)
const E_ACUTE = String.fromCodePoint(0xe9)
const GRIN = String.fromCodePoint(0x1f600)

let session: SessionModule
let ProfileSection: typeof import('./ProfileSection').ProfileSection

beforeEach(async () => {
  vi.resetModules()
  session = await import('../../lib/auth/session')
  ;({ ProfileSection } = await import('./ProfileSection'))
  auth.refresh(PAIR)
  auth.me(PROFILE)
  auth.workspaces(WORKSPACES)
  await session.restore()
})

const nameField = () => screen.findByRole('textbox', { name: 'Display name' })
const saveButton = () => screen.getByRole('button', { name: 'Save' })
const type = (field: HTMLElement, value: string) => fireEvent.change(field, { target: { value } })

const meGets = () =>
  requests().filter((r) => r.method === 'GET' && r.url.pathname === '/api/v1/users/me').length
const patches = () => requests().filter((r) => r.method === 'PATCH')
const signedInName = () => {
  const state = session.snapshot()
  if (state.status !== 'signedIn') throw new Error(`expected signedIn, was ${state.status}`)
  return state.session.profile.displayName
}

function deferred<T = void>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => {
    resolve = r
  })
  return { promise, resolve }
}

describe('ProfileSection — the form', () => {
  it('prefills from the server, not the session’s copy', async () => {
    // The session holds "Ada Lovelace"; the server now says otherwise.
    auth.me({ ...PROFILE, displayName: 'Ada L.' })
    expect(signedInName()).toBe('Ada Lovelace')

    renderWithProviders(<ProfileSection accessToken={TOKEN} />)

    expect(await nameField()).toHaveValue('Ada L.')
  })

  it('on a revisit the field waits for this visit’s fetch', async () => {
    const queryClient = createTestQueryClient()
    queryClient.setQueryData(profileKeys.me, { ...PROFILE, displayName: 'Ada L.' })
    const answer = deferred()
    auth.me(async () => {
      await answer.promise
      return { ...PROFILE, displayName: 'Ada M.' }
    })
    const before = meGets()

    renderWithProviders(<ProfileSection accessToken={TOKEN} />, { queryClient })
    await vi.waitFor(() => expect(meGets()).toBe(before + 1))

    // The cache holds a name, but it is not this visit's: no field to edit yet.
    expect(screen.queryByRole('textbox', { name: 'Display name' })).not.toBeInTheDocument()
    expect(screen.getByText('Loading…')).toBeInTheDocument()

    await act(async () => answer.resolve())
    expect(await nameField()).toHaveValue('Ada M.')
  })

  it('Save is off while unchanged, blank or over 100, and on otherwise', async () => {
    auth.me({ ...PROFILE, displayName: 'Jos' + E_ACUTE })
    renderWithProviders(<ProfileSection accessToken={TOKEN} />)
    const field = await nameField()

    // Unchanged: the same text, padded, and the same name typed in decomposed form.
    expect(saveButton()).toBeDisabled()
    type(field, '  Jos' + E_ACUTE + '  ')
    expect(saveButton()).toBeDisabled()
    type(field, 'Jose' + COMBINING_ACUTE)
    expect(saveButton()).toBeDisabled()

    // Blank.
    type(field, '   ')
    expect(saveButton()).toBeDisabled()
    type(field, '')
    expect(saveButton()).toBeDisabled()

    // The upper bound, in code points: 100 passes and 101 does not, whether each
    // is one UTF-16 unit or two.
    type(field, 'a'.repeat(100))
    expect(saveButton()).toBeEnabled()
    type(field, 'a'.repeat(101))
    expect(saveButton()).toBeDisabled()
    type(field, GRIN.repeat(100))
    expect(saveButton()).toBeEnabled()
    type(field, GRIN.repeat(101))
    expect(saveButton()).toBeDisabled()

    // And an ordinary change is on.
    type(field, 'Josephine')
    expect(saveButton()).toBeEnabled()
  })

  it('shows the 400 and the 409 on the field, and changes nothing', async () => {
    renderWithProviders(<ProfileSection accessToken={TOKEN} />)
    const field = await nameField()
    type(field, 'Ada M.')

    auth.updateMe(() => failWith(400, { title: 'Bad', errors: { displayName: [LENGTH] } }))
    fireEvent.click(saveButton())
    expect(await screen.findByRole('alert')).toHaveTextContent(LENGTH)

    auth.updateMe(() =>
      failWith(409, { title: 'Conflict', detail: TAKEN, errors: { displayName: [TAKEN] } }),
    )
    fireEvent.click(saveButton())
    await vi.waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(TAKEN))
    expect(screen.getByRole('alert')).not.toHaveTextContent(LENGTH)

    // Nothing moved: the text is still the user's, no confirmation, same name everywhere.
    expect(field).toHaveValue('Ada M.')
    expect(screen.queryByText('Saved')).not.toBeInTheDocument()
    expect(signedInName()).toBe('Ada Lovelace')
    expect(patches()).toHaveLength(2)
  })

  it('says Saved after a success, until the next edit', async () => {
    auth.updateMe(({ body }) => ({ ...PROFILE, displayName: (body as { displayName: string }).displayName }))
    renderWithProviders(<ProfileSection accessToken={TOKEN} />)
    const field = await nameField()
    expect(screen.queryByText('Saved')).not.toBeInTheDocument()

    type(field, 'Ada L.')
    fireEvent.click(saveButton())
    expect(await screen.findByText('Saved')).toBeInTheDocument()
    expect(patches().map((p) => p.body)).toEqual([{ displayName: 'Ada L.' }])

    type(field, 'Ada L.x')
    expect(screen.queryByText('Saved')).not.toBeInTheDocument()
  })
})

describe('ProfileSection — what a success updates', () => {
  const ada = (displayName: string) => aWorkspaceMember({ id: PROFILE.id, displayName })
  const grace = aWorkspaceMember({ id: 'user-grace', displayName: 'Grace Hopper' })
  const renamed = (body: unknown) => ({ ...PROFILE, displayName: (body as { displayName: string }).displayName })

  it('a success updates the session and every cached directory', async () => {
    const queryClient = createTestQueryClient()
    queryClient.setQueryData(directoryKeys.members(HOME), [ada('Ada Lovelace'), grace])
    queryClient.setQueryData(directoryKeys.members(AWAY), [grace, ada('Ada Lovelace')])
    auth.updateMe(({ body }) => renamed(body))
    renderWithProviders(<ProfileSection accessToken={TOKEN} />, { queryClient })

    type(await nameField(), 'Ada L.')
    fireEvent.click(saveButton())

    await vi.waitFor(() => expect(signedInName()).toBe('Ada L.'))
    for (const workspaceId of [HOME, AWAY]) {
      const members = queryClient.getQueryData<ReturnType<typeof ada>[]>(
        directoryKeys.members(workspaceId),
      )
      expect(members?.map((m) => m.user.displayName).sort()).toEqual(['Ada L.', 'Grace Hopper'])
    }
    expect(queryClient.getQueryData<Profile>(profileKeys.me)?.displayName).toBe('Ada L.')
  })

  /** The real directory hook, drawn as a list, beside the form. */
  function Names() {
    const { members } = useWorkspaceMembers(TOKEN, HOME)
    return (
      <ul aria-label="names">
        {members.map((m) => (
          <li key={m.user.id}>{m.user.displayName}</li>
        ))}
      </ul>
    )
  }

  const listed = () => screen.getAllByRole('listitem').map((li) => li.textContent)

  async function renderBeside() {
    const script = scriptDirectory({ [HOME]: [ada('Ada Lovelace')] })
    const view = renderWithProviders(
      <>
        <Names />
        <ProfileSection accessToken={TOKEN} />
      </>,
    )
    await screen.findByText('Ada Lovelace', { selector: 'li' })
    await settleDirectory(view.queryClient, HOME)
    return { script, ...view }
  }

  const refetchDirectory = (queryClient: ReturnType<typeof createTestQueryClient>) => {
    void queryClient.invalidateQueries({ queryKey: directoryKeys.members(HOME) })
  }

  it('a directory fetch answered before the rename cannot bring the old name back', async () => {
    const { script, queryClient } = await renderBeside()
    // A refetch is in flight when the rename lands, and will answer with the old name.
    const held = script.hold(HOME, 2)
    refetchDirectory(queryClient)
    await vi.waitFor(() => expect(script.requests(HOME)).toHaveLength(2))
    auth.updateMe(({ body }) => renamed(body))
    script.now[HOME] = [ada('Ada L.')]

    type(await nameField(), 'Ada L.')
    fireEvent.click(saveButton())
    await vi.waitFor(() => expect(listed()).toEqual(['Ada L.']))

    await held.release([ada('Ada Lovelace')])
    await settleDirectory(queryClient, HOME)

    expect(listed()).toEqual(['Ada L.'])
    expect(signedInName()).toBe('Ada L.')
  })

  it('a directory fetch answered while the rename is in flight still ends on the new name', async () => {
    const { script, queryClient } = await renderBeside()
    const commit = deferred()
    auth.updateMe(async ({ body }) => {
      await commit.promise
      return renamed(body)
    })

    type(await nameField(), 'Ada L.')
    fireEvent.click(saveButton())
    await vi.waitFor(() => expect(patches()).toHaveLength(1))
    // The old name comes back from the server, as it should before the commit.
    refetchDirectory(queryClient)
    await vi.waitFor(() => expect(script.requests(HOME)).toHaveLength(2))
    await settleDirectory(queryClient, HOME)
    expect(listed()).toEqual(['Ada Lovelace'])

    script.now[HOME] = [ada('Ada L.')]
    await act(async () => commit.resolve())
    await vi.waitFor(() => expect(listed()).toEqual(['Ada L.']))
    await settleDirectory(queryClient, HOME)

    expect(listed()).toEqual(['Ada L.'])
  })
})
