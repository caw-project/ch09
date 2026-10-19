/**
 * The signed-in user's own profile, and renaming it.
 *
 * A name is global — one per user, the same in every workspace (register D46) —
 * so a rename has to reach everywhere the old one is held: the session (the
 * sidebar), every cached workspace directory (message authors, the member panel)
 * and the profile query. `applyRename` does all three.
 */

import { type QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import * as api from '../../lib/auth/api'
import type { Profile, WorkspaceMember } from '../../lib/auth/api'
import * as session from '../../lib/auth/session'

export const profileKeys = {
  me: () => ['profile', 'me'] as const,
}

const DIRECTORIES = ['workspace-members']

export function useProfile(token: string | null, options: { fresh?: boolean } = {}) {
  return useQuery({
    queryKey: profileKeys.me(),
    queryFn: () => api.me(token as string),
    enabled: token !== null,
    staleTime: 5 * 60 * 1000,
    // `fresh`: the Settings page shows what the server holds now, not a cached copy.
    refetchOnMount: options.fresh ? 'always' : true,
  })
}

/**
 * Put a committed rename everywhere, then make the server confirm it.
 *
 * Write first: the new name shows at once, in every workspace the user has
 * cached (their own row only — a rename is theirs alone). Then invalidate:
 * `invalidateQueries` refetches the active queries with `cancelRefetch`, which
 * cancels a fetch already in flight, so a directory answered *before* the commit
 * cannot land the old name back; the refetch it sends is after the commit and
 * carries the new one. A directory nobody is looking at is marked stale and
 * refetches on its next mount.
 */
export function applyRename(queryClient: QueryClient, profile: Profile): void {
  queryClient.setQueriesData<WorkspaceMember[]>({ queryKey: DIRECTORIES }, (members) =>
    members?.map((member) =>
      member.user.id === profile.id
        ? { ...member, user: { ...member.user, displayName: profile.displayName } }
        : member,
    ),
  )
  queryClient.setQueryData(profileKeys.me(), profile)

  void queryClient.invalidateQueries({ queryKey: DIRECTORIES })
  void queryClient.invalidateQueries({ queryKey: profileKeys.me() })
}

/**
 * Rename the signed-in user.
 *
 * The session and cache writes are in the hook's own `onSuccess`, not in a
 * `mutate()` callback: those run only while a component still observes the
 * mutation, and a rename that lands after the user has left the page must still
 * update the sidebar.
 */
export function useUpdateDisplayName(token: string | null) {
  const queryClient = useQueryClient()

  return useMutation<Profile, Error, string>({
    mutationFn: (displayName) => api.updateMe(token as string, { displayName }),
    onSuccess: (profile) => {
      session.updateProfile(profile)
      applyRename(queryClient, profile)
    },
  })
}
