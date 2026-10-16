/**
 * When the workspace directory is asked for an id it doesn't hold, fetch it again —
 * once, joining any fetch already in flight — and stop asking for ids a fetch
 * proved it lacks.
 *
 * One tracker per `QueryClient` (it describes that cache's own fetches), state per
 * workspace. It holds ids and fetch bookkeeping only; names stay in the query
 * cache (D24).
 *
 * - **pending**: ids a render could not name, with a logical timestamp of when
 *   they were first seen.
 * - **departed**: ids a fetch that started *after* they were seen landed without.
 *   They start no further fetch until a fetch for another reason lands.
 *
 * Wall-clock time is not used: a logical clock cannot tie.
 */

import type { QueryClient } from '@tanstack/react-query'

import type { WorkspaceMember } from '../../lib/auth/api'
import { directoryKeys } from './useWorkspaceMembers'

export interface DirectoryTracker {
  /** After a commit: the ids this render could not name. Starts at most one refetch. */
  saw(workspaceId: string, ids: ReadonlySet<string>): void
  /** The directory's queryFn goes through this: it times the fetch and settles its ids. */
  load(workspaceId: string, fetch: () => Promise<WorkspaceMember[]>): Promise<WorkspaceMember[]>
  /**
   * A fetch for another reason is starting or joining one in flight: the next
   * fetch to land for this workspace clears the departed set, whoever started it.
   * The mark outlives a fetch that never lands; the next one to land clears it.
   */
  otherReason(workspaceId: string): void
}

interface WorkspaceState {
  pending: Map<string, number>
  departed: Set<string>
  ownStarting: boolean
  otherMarked: boolean
}

const trackers = new WeakMap<QueryClient, DirectoryTracker>()

export function directoryTracker(queryClient: QueryClient): DirectoryTracker {
  const existing = trackers.get(queryClient)
  if (existing) return existing

  const states = new Map<string, WorkspaceState>()
  let clock = 0

  function stateFor(workspaceId: string): WorkspaceState {
    let state = states.get(workspaceId)
    if (!state) {
      state = { pending: new Map(), departed: new Set(), ownStarting: false, otherMarked: false }
      states.set(workspaceId, state)
    }
    return state
  }

  /** Move every pending id this fetch could have had to `departed`. */
  function departSeenBefore(state: WorkspaceState, startedAt: number, named?: Set<string>) {
    for (const [id, seenAt] of [...state.pending]) {
      if (named?.has(id)) {
        state.pending.delete(id)
      } else if (seenAt < startedAt) {
        state.pending.delete(id)
        state.departed.add(id)
      }
    }
  }

  const tracker: DirectoryTracker = {
    otherReason(workspaceId) {
      stateFor(workspaceId).otherMarked = true
    },

    saw(workspaceId, ids) {
      const state = stateFor(workspaceId)
      for (const id of ids) {
        if (!state.departed.has(id) && !state.pending.has(id)) state.pending.set(id, clock++)
      }
      if (state.pending.size === 0) return

      const key = directoryKeys.members(workspaceId)
      const query = queryClient.getQueryState(key)
      // No data: TanStack's own load and mount refetch are the fetch. In flight: join.
      if (query?.data === undefined || query.fetchStatus !== 'idle') return

      // `queryFn` runs synchronously inside this call, which is how `load` knows
      // the fetch is ours.
      state.ownStarting = true
      void queryClient.refetchQueries({ queryKey: key, exact: true }, { cancelRefetch: false })
      state.ownStarting = false
    },

    async load(workspaceId, fetch) {
      const state = stateFor(workspaceId)
      const own = state.ownStarting
      state.ownStarting = false
      const startedAt = clock++
      const hadData = queryClient.getQueryData(directoryKeys.members(workspaceId)) !== undefined

      let members: WorkspaceMember[]
      try {
        members = await fetch()
      } catch (error) {
        // A failed refetch quiets the ids it was for; retrying on every render
        // would loop on a persistent server error.
        if (hadData) departSeenBefore(state, startedAt)
        throw error
      }

      if (!own || state.otherMarked) {
        state.departed.clear()
        state.otherMarked = false
      }
      const named = new Set(members.map((member) => member.user.id))
      if (hadData) {
        departSeenBefore(state, startedAt, named)
      } else {
        for (const id of [...state.pending.keys()]) if (named.has(id)) state.pending.delete(id)
      }
      return members
    },
  }

  trackers.set(queryClient, tracker)
  return tracker
}
