/**
 * Helpers for tests of the workspace directory's refetch rules.
 *
 * `settleDirectory` waits for a directory to stop fetching *and stay stopped*;
 * `scriptDirectory` answers each `GET …/members` by workspace and call number,
 * and can hold one in flight.
 */

import type { QueryClient } from '@tanstack/react-query'
import { act } from '@testing-library/react'
import { expect, vi } from 'vitest'

import { directoryKeys } from '../features/channels/useWorkspaceMembers'
import type { WorkspaceMember } from '../lib/auth/api'
import { auth, requests } from './api'

/**
 * Resolves once the directory for `workspaceId` is idle and stays idle across a
 * macrotask. TanStack notifies observers on setTimeout(0), and the re-render that
 * follows may start the next fetch from its effect — so one idle reading is not
 * enough: it is taken twice, each after its own macrotask. A build that refetches
 * forever never settles, and the wait times out.
 */
export async function settleDirectory(queryClient: QueryClient, workspaceId: string): Promise<void> {
  await vi.waitFor(async () => {
    for (let i = 0; i < 2; i++) {
      await act(() => new Promise<void>((resolve) => setTimeout(resolve, 0)))
      expect(queryClient.isFetching({ queryKey: directoryKeys.members(workspaceId) })).toBe(0)
    }
  })
}

type Answer = WorkspaceMember[] | Promise<WorkspaceMember[]>

/**
 * Serves the directory. `now` is what every call answers unless a call number was
 * given its own answer; it is mutable, so a test changes who is "in the workspace"
 * by assigning `script.now[ws]`.
 */
export function scriptDirectory(now: Record<string, WorkspaceMember[]>) {
  const at = new Map<string, Answer>()
  const key = (workspaceId: string, call: number) => `${workspaceId}:${call}`

  auth.membersBy((workspaceId, call) => at.get(key(workspaceId, call)) ?? now[workspaceId] ?? [])

  return {
    now,
    /** Call number `call` of `workspaceId` answers `members`, whatever `now` holds. */
    answer(workspaceId: string, call: number, members: WorkspaceMember[]): void {
      at.set(key(workspaceId, call), members)
    },
    /** Holds call number `call` in flight until `release` is called. */
    hold(workspaceId: string, call: number) {
      let resolve!: (members: WorkspaceMember[]) => void
      at.set(
        key(workspaceId, call),
        new Promise<WorkspaceMember[]>((r) => {
          resolve = r
        }),
      )
      return {
        async release(members: WorkspaceMember[]): Promise<void> {
          await act(async () => {
            resolve(members)
          })
        },
      }
    },
    /** The directory requests made for `workspaceId` so far, held ones included. */
    requests(workspaceId: string) {
      return requests().filter(
        (r) => r.url.pathname === `/api/v1/workspaces/${workspaceId}/members`,
      )
    },
  }
}
