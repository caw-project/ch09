/**
 * The signed-in user's own profile, read from the server, and renaming it.
 *
 * `useProfile` refetches on every mount: the Profile form must show what the
 * server holds *now*, not the session's copy from sign-in or a name cached on an
 * earlier visit (issue gh-3, Req 8).
 *
 * ## What a rename updates, and why it is the mutation's own `onSuccess`
 *
 * The callbacks live in `useMutation`, not in `mutate(…, { onSuccess })`: the
 * latter run only while the component that called `mutate` is still mounted, and a
 * user who clicks Save and then leaves the page must still see the new name in the
 * sidebar and on their own messages when the save lands.
 *
 * On success, in this order:
 *
 * 1. cancel directory fetches in flight — one that was answered before the commit
 *    would otherwise land the *old* name after the write below;
 * 2. write the new name into every cached `['workspace-members', *]` that has data
 *    (the user's own messages read it), and refetch any that has none because
 *    its fetch was just cancelled;
 * 3. `session.updateProfile` so the sidebar changes at once, and the profile cache.
 *
 * Nobody else's open window changes until their own directory is refetched; there
 * is no live push of a rename (Req 5).
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { me, updateMe, type Profile, type WorkspaceMember } from '../../lib/auth/api'
import * as session from '../../lib/auth/session'

export const profileKeys = {
  me: ['profile', 'me'] as const,
}

// The prefix of `directoryKeys.members(*)` in `channels/useWorkspaceMembers.ts`.
const DIRECTORIES = ['workspace-members'] as const

export function useProfile(accessToken: string) {
  return useQuery({
    queryKey: profileKeys.me,
    queryFn: () => me(accessToken),
    refetchOnMount: 'always',
  })
}

export function useUpdateDisplayName(accessToken: string) {
  const queryClient = useQueryClient()

  return useMutation<Profile, Error, string>({
    mutationFn: (displayName) => updateMe(accessToken, { displayName }),
    onSuccess: async (profile) => {
      await queryClient.cancelQueries({ queryKey: DIRECTORIES })
      queryClient.setQueriesData<WorkspaceMember[]>({ queryKey: DIRECTORIES }, (members) =>
        members?.map((member) =>
          member.user.id === profile.id
            ? { ...member, user: { ...member.user, displayName: profile.displayName } }
            : member,
        ),
      )
      void queryClient.refetchQueries({
        queryKey: DIRECTORIES,
        predicate: (query) => query.state.data === undefined,
      })
      session.updateProfile(profile)
      queryClient.setQueryData(profileKeys.me, profile)
    },
  })
}
