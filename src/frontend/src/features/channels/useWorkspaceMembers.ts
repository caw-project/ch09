/**
 * Everyone in the workspace, and a way to put a name to a user id.
 *
 * Messaging returns bare user ids on membership rows, and will return them on
 * message authors too: it owns no user records and must not read Auth's tables
 * (Conventions §2). So the *browser* resolves names, from Auth's own workspace
 * member list, with the token it already holds.
 *
 * One hook, used by every part of the UI that has an id and needs a name — the
 * member panel today, message authors and the typing indicator later. A second
 * fetch with a second key would mean the same directory cached twice under two
 * names, and going stale at two different moments.
 *
 * An id with no matching member renders as a shortened id rather than a blank:
 * someone can be in a channel and no longer in the workspace, and a row with no
 * label in it looks like a bug. It is also the label while the directory is
 * being refetched: a member who joined after it loaded is unknown until it is
 * fetched again.
 *
 * An unknown id refetches the directory once, joining a fetch already in flight
 * (`directoryRefresh.ts`). An id a fetch then lands without is departed, and
 * asks for nothing more until a fetch for another reason (stale mount, focus,
 * reconnect) lands.
 */

import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'

import { workspaceMembers, type WorkspaceMember } from '../../lib/auth/api'
import { directoryTracker } from './directoryRefresh'

export const directoryKeys = {
  /** Every workspace's directory — what a rename must touch, whichever are cached. */
  all: () => ['workspace-members'] as const,
  members: (workspaceId: string | null) => ['workspace-members', workspaceId] as const,
}

export interface Directory {
  /** A display name for a user id, or a shortened id if we have no better. */
  nameFor: (userId: string) => string
  members: WorkspaceMember[]
}

export function shortId(userId: string): string {
  return userId.slice(0, 8)
}

export function useWorkspaceMembers(accessToken: string, workspaceId: string | null): Directory {
  const tracker = directoryTracker(useQueryClient())
  // `fetchStatus` is read for its re-render, not its value: structural sharing
  // hands back the same `data` when a refetch lands without the newcomer, and an
  // observer re-renders only for fields it read. Without it no consumer would
  // render, no effect would run, and an id first seen mid-fetch would never get
  // its follow-up. Do not remove it as unused.
  const { data, fetchStatus } = useQuery({
    queryKey: directoryKeys.members(workspaceId),
    // The workspace comes from the key, never a closure a switch could outlive.
    queryFn: ({ queryKey }) =>
      tracker.load(queryKey[1] as string, () =>
        workspaceMembers(accessToken, queryKey[1] as string),
      ),
    enabled: Boolean(workspaceId),
    // Display names change rarely and this is read on every render of every
    // author line; refetching it on each mount would be a call per navigation.
    staleTime: 5 * 60 * 1000,
  })
  void fetchStatus

  const members = data ?? []
  const byId = new Map(members.map((member) => [member.user.id, member.user.displayName]))

  // Ids this render could not name; handed to the tracker after the commit,
  // never during render.
  const unknown = new Set<string>()

  // No dependency array on purpose: it must run after every commit, because a
  // fetch landing with nothing new changes no dependency but still owes the
  // follow-up for ids first seen while it was in flight.
  useEffect(() => {
    if (workspaceId && unknown.size > 0) tracker.saw(workspaceId, unknown)
  })

  return {
    members,
    nameFor: (userId) => {
      const name = byId.get(userId)
      if (name !== undefined) return name
      unknown.add(userId)
      return shortId(userId)
    },
  }
}
