/**
 * A rename reaches the renamer's own view (issue gh-3, Req 5).
 *
 * On success the session's profile and every cached workspace directory take the
 * new name at once, so the sidebar and the user's own message authors never
 * disagree. The hook-level callbacks are what make that hold after the component
 * has unmounted; the cancel and the invalidate are what make it hold against a
 * fetch that left with the old name. The session is the real store.
 *
 * Cache keys are written out literally — `['profile','me']` and
 * `['workspace-members', ws]` — so a rename of an exported key shows up here.
 */

import type { QueryClient } from '@tanstack/react-query'
import { act } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Profile, TokenPair, Workspace, WorkspaceMember } from '../../lib/auth/api'
import * as session from '../../lib/auth/session'
import { auth, requests } from '../../test/api'
import { scriptDirectory, settleDirectory } from '../../test/directory'
import { aWorkspaceMember } from '../../test/factories'
import { createTestQueryClient, renderHookWithProviders } from '../../test/render'
import { directoryKeys, useWorkspaceMembers } from '../channels/useWorkspaceMembers'
import { useProfile, useUpdateDisplayName } from './useProfile'

const HOME = 'workspace-home'
const WS_A = '0199a000-0000-7000-8000-00000000aaa0'
const WS_B = '0199a000-0000-7000-8000-00000000bbb0'

const PROFILE: Profile = {
  id: 'user-ada',
  email: 'ada@collabhub.dev',
  displayName: 'Ada Lovelace',
  avatarAsset: null,
}
const WORKSPACES: Workspace[] = [{ id: HOME, name: 'Home', role: 'owner' }]

/** An unsigned token carrying a `wsp` claim — the SPA only ever reads it. */
function pair(workspaceId: string): TokenPair {
  const payload = btoa(JSON.stringify({ wsp: workspaceId }))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
  return { accessToken: `header.${payload}.signature`, tokenType: 'Bearer', expiresIn: 900 }
}

const grace = aWorkspaceMember({ id: 'user-grace', displayName: 'Grace Hopper' })
const adaIn = (name: string): WorkspaceMember =>
  aWorkspaceMember({ id: PROFILE.id, displayName: name })

function namesIn(queryClient: QueryClient, workspace: string): (string | undefined)[] {
  const members = queryClient.getQueryData<WorkspaceMember[]>(['workspace-members', workspace])
  return (members ?? []).map((m) => m.user.displayName)
}

function sessionName(): string | undefined {
  const state = session.snapshot()
  return state.status === 'signedIn' ? state.session.profile.displayName : undefined
}

function deferred<T = void>() {
  let release!: (value: T) => void
  const promise = new Promise<T>((resolve) => {
    release = resolve
  })
  return { promise, release }
}

beforeEach(async () => {
  auth.refresh(pair(HOME))
  auth.me(PROFILE)
  auth.workspaces(WORKSPACES)
  await session.restore()
})

describe('useUpdateDisplayName', () => {
  it('updates the session and every cached directory, and no one else’s name', async () => {
    auth.updateMe(({ displayName }) => ({ ...PROFILE, displayName }))
    const queryClient = createTestQueryClient()
    queryClient.setQueryData(['workspace-members', WS_A], [adaIn('Ada Lovelace'), grace])
    queryClient.setQueryData(['workspace-members', WS_B], [grace, adaIn('Ada Lovelace')])
    const { result } = renderHookWithProviders(() => useUpdateDisplayName('token'), { queryClient })

    await act(async () => {
      await result.current.mutateAsync('Ada L')
    })

    expect(namesIn(queryClient, WS_A)).toEqual(['Ada L', 'Grace Hopper'])
    expect(namesIn(queryClient, WS_B)).toEqual(['Grace Hopper', 'Ada L'])
    expect(sessionName()).toBe('Ada L')
    expect(queryClient.getQueryData(['profile', 'me'])).toEqual({ ...PROFILE, displayName: 'Ada L' })
    // Marked stale as well, so a fetch that left earlier cannot stay the last word.
    expect(queryClient.getQueryState(['workspace-members', WS_A])?.isInvalidated).toBe(true)
    expect(queryClient.getQueryState(['workspace-members', WS_B])?.isInvalidated).toBe(true)
    expect(queryClient.getQueryState(['profile', 'me'])?.isInvalidated).toBe(true)
  })

  it('leaves everything as it was when the server refuses', async () => {
    auth.problem('patch', '/api/v1/users/me', 409, {
      title: 'Conflict',
      detail: 'That name is already taken.',
      errors: { displayName: ['That name is already taken.'] },
    })
    const queryClient = createTestQueryClient()
    queryClient.setQueryData(['workspace-members', WS_A], [adaIn('Ada Lovelace'), grace])
    const { result } = renderHookWithProviders(() => useUpdateDisplayName('token'), { queryClient })

    await act(async () => {
      await result.current.mutateAsync('grace').catch(() => undefined)
    })

    expect(namesIn(queryClient, WS_A)).toEqual(['Ada Lovelace', 'Grace Hopper'])
    expect(sessionName()).toBe('Ada Lovelace')
  })

  it('lands after the component that asked has unmounted', async () => {
    const reply = deferred()
    auth.updateMe(async ({ displayName }) => {
      await reply.promise
      return { ...PROFILE, displayName }
    })
    const queryClient = createTestQueryClient()
    queryClient.setQueryData(['workspace-members', WS_A], [adaIn('Ada Lovelace'), grace])
    const { result, unmount } = renderHookWithProviders(() => useUpdateDisplayName('token'), {
      queryClient,
    })

    act(() => {
      result.current.mutate('Ada L')
    })
    await vi.waitFor(() => expect(requests().some((r) => r.method === 'PATCH')).toBe(true))
    unmount()
    reply.release()

    await vi.waitFor(() => expect(sessionName()).toBe('Ada L'))
    expect(namesIn(queryClient, WS_A)).toEqual(['Ada L', 'Grace Hopper'])
  })

  it('is not undone by a directory fetch that left with the old name', async () => {
    const script = scriptDirectory({ [WS_A]: [adaIn('Ada Lovelace'), grace] })
    auth.updateMe(({ displayName }) => {
      // From now on the server answers with the new name.
      script.now[WS_A] = [adaIn(displayName), grace]
      return { ...PROFILE, displayName }
    })
    const queryClient = createTestQueryClient()
    const { result } = renderHookWithProviders(
      () => ({
        directory: useWorkspaceMembers('token', WS_A),
        rename: useUpdateDisplayName('token'),
      }),
      { queryClient },
    )
    await vi.waitFor(() => expect(namesIn(queryClient, WS_A)).toContain('Ada Lovelace'))
    await settleDirectory(queryClient, WS_A)
    // A refetch is on its way back with the old name…
    const held = script.hold(WS_A, 2)
    act(() => {
      void queryClient.refetchQueries({ queryKey: directoryKeys.members(WS_A) })
    })
    await vi.waitFor(() => expect(script.requests(WS_A)).toHaveLength(2))

    // …when the rename succeeds, and only then does the old answer arrive.
    await act(async () => {
      await result.current.rename.mutateAsync('Ada L')
    })
    await held.release([adaIn('Ada Lovelace'), grace])

    await vi.waitFor(() => expect(namesIn(queryClient, WS_A)).toContain('Ada L'))
    await settleDirectory(queryClient, WS_A)
    expect(namesIn(queryClient, WS_A)).toEqual(['Ada L', 'Grace Hopper'])
  })

  it('is not undone by a profile fetch that left with the old name', async () => {
    let name = 'Ada Lovelace'
    let calls = 0
    const held = deferred()
    auth.meBy(async () => {
      calls += 1
      const answering = name // what the server holds the moment the request arrives
      if (calls === 2) await held.promise
      return { ...PROFILE, displayName: answering }
    })
    auth.updateMe(({ displayName }) => {
      name = displayName
      return { ...PROFILE, displayName }
    })
    const queryClient = createTestQueryClient()
    const { result } = renderHookWithProviders(
      () => ({ profile: useProfile('token'), rename: useUpdateDisplayName('token') }),
      { queryClient },
    )
    await vi.waitFor(() =>
      expect(queryClient.getQueryData<Profile>(['profile', 'me'])?.displayName).toBe('Ada Lovelace'),
    )
    act(() => {
      void queryClient.refetchQueries({ queryKey: ['profile', 'me'] })
    })
    await vi.waitFor(() => expect(calls).toBe(2))

    await act(async () => {
      await result.current.rename.mutateAsync('Ada L')
    })
    held.release()

    await vi.waitFor(() =>
      expect(queryClient.getQueryData<Profile>(['profile', 'me'])?.displayName).toBe('Ada L'),
    )
    // Let the held answer land and the invalidate’s own fetch finish: the last word is the new name.
    await act(() => new Promise<void>((resolve) => setTimeout(resolve, 50)))
    expect(queryClient.getQueryData<Profile>(['profile', 'me'])?.displayName).toBe('Ada L')
    expect(calls).toBeGreaterThanOrEqual(3)
  })
})
