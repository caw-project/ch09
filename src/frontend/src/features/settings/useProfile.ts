/**
 * The signed-in user's own profile as the server holds it, and the rename
 * (issue gh-3 Req 5 and 8).
 *
 * The page reads the server's copy on every visit rather than the session's or
 * the cache's, so a rename made in another tab shows up here.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { directoryKeys } from '../channels/useWorkspaceMembers'
import { me, updateMe, type WorkspaceMember } from '../../lib/auth/api'
import * as session from '../../lib/auth/session'

export const profileKeys = {
  mine: (userId: string) => ['user-profile', userId] as const,
}

export function useProfile(accessToken: string, userId: string) {
  return useQuery({
    queryKey: profileKeys.mine(userId),
    queryFn: () => me(accessToken),
    // Every visit asks the server, whatever the cache or the session holds.
    refetchOnMount: 'always',
  })
}

/**
 * Rename yourself. A success writes the new name everywhere this tab shows it —
 * the session profile (the sidebar), the profile query and every cached
 * workspace directory (message authors) — at once, rather than waiting for the
 * next directory refetch as everyone else does.
 *
 * **The writes are in the hook's own `onSuccess`, not in a `mutate(…, { onSuccess })`
 * at the call site.** The hook-level callback runs whether or not the page is
 * still mounted; a per-call one runs only while it is subscribed, so a save that
 * lands after the user left would never update the sidebar.
 *
 * Order matters. `cancelQueries` comes first and is awaited: `invalidateQueries`
 * cancels an in-flight fetch only when the query already has data, and with none
 * (a direct load of this page, the sidebar's first directory fetch still out) it
 * joins that fetch, which would then land with the old name. Cancelling covers
 * both cases. The invalidate at the end refetches after the commit; it is not
 * awaited, so "Saved" does not wait for it.
 */
export function useUpdateDisplayName(accessToken: string, userId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (displayName: string) => updateMe(accessToken, { displayName }),
    onSuccess: async (profile) => {
      session.updateProfile(profile)
      queryClient.setQueryData(profileKeys.mine(userId), profile)

      const directories = { queryKey: directoryKeys.all }
      await queryClient.cancelQueries(directories)
      queryClient.setQueriesData<WorkspaceMember[]>(directories, (members) =>
        members?.map((member) =>
          member.user.id === profile.id
            ? { ...member, user: { ...member.user, displayName: profile.displayName } }
            : member,
        ),
      )
      void queryClient.invalidateQueries(directories)
    },
  })
}
