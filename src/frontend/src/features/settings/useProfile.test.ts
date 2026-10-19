/**
 * Renaming yourself, and everywhere the new name has to appear (issue gh-3, Req 5).
 *
 * The session is the real store, restored through Auth stubs at the network edge,
 * so "the sidebar's name" is what `session.snapshot()` says. The directories are
 * `['workspace-members', <id>]` caches — the same ones `useWorkspaceMembers` reads —
 * and Grace's row in each must never be touched: a rename is Ada's alone.
 *
 * Literal keys (`['profile', 'me']`, `['workspace-members', id]`) rather than the
 * module's exports, so a wrong export name fails a test and does not hide it.
 */

import type { QueryClient } from '@tanstack/react-query'
import { act } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Profile, TokenPair, Workspace, WorkspaceMember } from '../../lib/auth/api'
import * as session from '../../lib/auth/session'
import { auth, requests, resetRequests } from '../../test/api'
import { settleDirectory } from '../../test/directory'
import { aWorkspaceMember } from '../../test/factories'
import { createTestQueryClient, renderHookWithProviders } from '../../test/render'
import { useWorkspaceMembers } from '../channels/useWorkspaceMembers'
import { useProfile, useUpdateDisplayName } from './useProfile'

const WS_A = '0199a000-0000-7000-8000-00000000aaa0'
const WS_B = '0199a000-0000-7000-8000-00000000bbb0'
const TOKEN = 'header.' + btoa(JSON.stringify({ wsp: WS_A })).replace(/=+$/, '') + '.signature'

const ADA_ID = '0199a000-0000-7000-8000-000000000001'
const PROFILE: Profile = {
  id: ADA_ID,
  email: 'ada@collabhub.dev',
  displayName: 'Ada Lovelace',
  avatarAsset: null,
}
const WORKSPACES: Workspace[] = [
  { id: WS_A, name: 'A', role: 'owner' },
  { id: WS_B, name: 'B', role: 'member' },
]
const PAIR: TokenPair = { accessToken: TOKEN, tokenType: 'Bearer', expiresIn: 900 }

const ada = (displayName = 'Ada Lovelace') => aWorkspaceMember({ id: ADA_ID, displayName })
const grace = aWorkspaceMember({ id: '0199a000-0000-7000-8000-000000000002', displayName: 'Grace Hopper' })

const PROFILE_KEY = ['profile', 'me']
const directory = (workspace: string) => ['workspace-members', workspace]

function names(queryClient: QueryClient, workspace: string): Record<string, string> {
  const members = queryClient.getQueryData<WorkspaceMember[]>(directory(workspace)) ?? []
  return Object.fromEntries(members.map((m) => [m.user.id, m.user.displayName]))
}

function sessionName(): string | undefined {
  const state = session.snapshot()
  return state.status === 'signedIn' ? state.session.profile.displayName : undefined
}

function acceptRenames() {
  auth.updateMe((body) => ({ ...PROFILE, displayName: body.displayName ?? '' }))
}

function deferred() {
  let release!: () => void
  const promise = new Promise<void>((resolve) => {
    release = resolve
  })
  return { promise, release }
}

const memberRequests = (workspace: string) =>
  requests().filter((r) => r.url.pathname === `/api/v1/workspaces/${workspace}/members`)

beforeEach(async () => {
  auth.me(PROFILE)
  auth.workspaces(WORKSPACES)
  auth.refresh(PAIR)
  await session.restore()
  // The restore's own requests are set-up, not what a test is asserting about.
  resetRequests()
})

describe('useUpdateDisplayName', () => {
  it('a rename updates the session and every cached directory', async () => {
    const queryClient = createTestQueryClient()
    queryClient.setQueryData(directory(WS_A), [ada(), grace])
    queryClient.setQueryData(directory(WS_B), [ada()])
    acceptRenames()
    const { result } = renderHookWithProviders(() => useUpdateDisplayName(TOKEN), { queryClient })

    await act(async () => {
      await result.current.mutateAsync('Ada L')
    })

    expect(requests().find((r) => r.method === 'PATCH')?.body).toEqual({ displayName: 'Ada L' })
    expect(sessionName()).toBe('Ada L')
    expect(names(queryClient, WS_A)).toEqual({ [ADA_ID]: 'Ada L', [grace.user.id]: 'Grace Hopper' })
    expect(names(queryClient, WS_B)).toEqual({ [ADA_ID]: 'Ada L' })
    expect(queryClient.getQueryData<Profile>(PROFILE_KEY)?.displayName).toBe('Ada L')
    // A directory nobody is looking at is marked stale, so its next mount refetches it.
    expect(queryClient.getQueryState(directory(WS_B))?.isInvalidated).toBe(true)
  })

  it('the update lands after the page unmounts', async () => {
    const queryClient = createTestQueryClient()
    queryClient.setQueryData(directory(WS_A), [ada(), grace])
    const held = deferred()
    auth.updateMe(async (body) => {
      await held.promise
      return { ...PROFILE, displayName: body.displayName ?? '' }
    })
    const view = renderHookWithProviders(() => useUpdateDisplayName(TOKEN), { queryClient })

    act(() => {
      view.result.current.mutate('Ada L')
    })
    await vi.waitFor(() => expect(requests().some((r) => r.method === 'PATCH')).toBe(true))
    expect(sessionName()).toBe('Ada Lovelace')
    view.unmount()
    held.release()

    await vi.waitFor(() => expect(sessionName()).toBe('Ada L'))
    await vi.waitFor(() => expect(names(queryClient, WS_A)[ADA_ID]).toBe('Ada L'))
    expect(names(queryClient, WS_A)[grace.user.id]).toBe('Grace Hopper')
  })

  it('a failed rename changes neither, and a successful one afterwards does', async () => {
    const queryClient = createTestQueryClient()
    queryClient.setQueryData(directory(WS_A), [ada(), grace])
    auth.problem('patch', '/api/v1/users/me', 409, {
      title: 'Conflict',
      detail: 'That name is already taken.',
      errors: { displayName: ['That name is already taken.'] },
    })
    const { result } = renderHookWithProviders(() => useUpdateDisplayName(TOKEN), { queryClient })

    await act(async () => {
      await expect(result.current.mutateAsync('Grace Hopper')).rejects.toMatchObject({
        errors: { displayName: ['That name is already taken.'] },
      })
    })

    expect(sessionName()).toBe('Ada Lovelace')
    expect(names(queryClient, WS_A)[ADA_ID]).toBe('Ada Lovelace')

    acceptRenames()
    await act(async () => {
      await result.current.mutateAsync('Ada L')
    })

    expect(sessionName()).toBe('Ada L')
    expect(names(queryClient, WS_A)[ADA_ID]).toBe('Ada L')
  })

  it('a directory fetch in flight cannot put the old name back', async () => {
    const queryClient = createTestQueryClient()
    const second = deferred()
    // Call 1 loads the directory; call 2 starts before the rename and is held, then
    // answers with the name as it was; call 3 onwards is after the commit.
    auth.membersBy(async (_workspace, call) => {
      if (call === 1) return [ada('Ada Lovelace'), grace]
      if (call === 2) {
        await second.promise
        return [ada('Ada Lovelace'), grace]
      }
      return [ada('Ada L'), grace]
    })
    acceptRenames()
    const { result } = renderHookWithProviders(
      () => ({
        directory: useWorkspaceMembers(TOKEN, WS_A),
        rename: useUpdateDisplayName(TOKEN),
      }),
      { queryClient },
    )
    await vi.waitFor(() => expect(result.current.directory.members).toHaveLength(2))

    act(() => {
      void queryClient.refetchQueries({ queryKey: directory(WS_A) })
    })
    await vi.waitFor(() => expect(memberRequests(WS_A)).toHaveLength(2))

    await act(async () => {
      await result.current.rename.mutateAsync('Ada L')
    })
    await act(async () => {
      second.release()
    })

    await vi.waitFor(() => expect(memberRequests(WS_A).length).toBeGreaterThanOrEqual(3))
    await settleDirectory(queryClient, WS_A)
    expect(names(queryClient, WS_A)[ADA_ID]).toBe('Ada L')
    expect(queryClient.getQueryData<Profile>(PROFILE_KEY)?.displayName).toBe('Ada L')
  })
})

describe('useProfile', () => {
  it('reads the profile from the server under one key', async () => {
    const queryClient = createTestQueryClient()
    const { result } = renderHookWithProviders(() => useProfile(TOKEN), { queryClient })

    await vi.waitFor(() => expect(result.current.data).toEqual(PROFILE))

    expect(queryClient.getQueryData(PROFILE_KEY)).toEqual(PROFILE)
  })

  it('asks the server again on a visit, whatever is cached and however fresh it looks', async () => {
    const queryClient = createTestQueryClient()
    queryClient.setDefaultOptions({ queries: { retry: false, gcTime: Infinity, staleTime: Infinity } })
    queryClient.setQueryData(PROFILE_KEY, { ...PROFILE, displayName: 'Old' })
    const { result } = renderHookWithProviders(() => useProfile(TOKEN, { fresh: true }), {
      queryClient,
    })

    await vi.waitFor(() => expect(result.current.data?.displayName).toBe('Ada Lovelace'))
    expect(requests().filter((r) => r.url.pathname === '/api/v1/users/me')).toHaveLength(1)
  })

  it('fetches nothing without a token', async () => {
    const { result } = renderHookWithProviders(() => useProfile(null))

    await act(() => new Promise<void>((resolve) => setTimeout(resolve, 25)))

    expect(result.current.data).toBeUndefined()
    expect(requests()).toEqual([])
  })
})
