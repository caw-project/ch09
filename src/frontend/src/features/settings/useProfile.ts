/**
 * The signed-in user's own profile, and renaming it (issue gh-3, Req 1 and 5).
 *
 * `useProfile` reads `GET /users/me` under `['profile', 'me']` and refetches on
 * every mount, so the Settings form starts from what Auth holds — the session's
 * copy is only as fresh as the last renewal.
 *
 * A rename is not optimistic: the server may refuse the name, and the field then
 * shows why. When it succeeds, *this* tab's view is brought up to date at once —
 * the session's profile and every cached workspace directory — so the sidebar and
 * the user's own message authors never disagree. Other people see it on their next
 * directory fetch; there is no broadcast. These are hook-level callbacks, which
 * run with no component mounted: a rename started and then navigated away from
 * still lands.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { me, updateMe, type Profile, type WorkspaceMember } from '../../lib/auth/api'
import * as session from '../../lib/auth/session'
import { directoryKeys } from '../channels/useWorkspaceMembers'

export const profileKeys = {
  me: () => ['profile', 'me'] as const,
}

export function useProfile(accessToken: string) {
  return useQuery({
    queryKey: profileKeys.me(),
    // The user comes from the token's `sub`, so the key needs no id.
    queryFn: () => me(accessToken),
    refetchOnMount: 'always',
  })
}

export function useUpdateDisplayName(accessToken: string) {
  const queryClient = useQueryClient()

  return useMutation<Profile, Error, string>({
    mutationFn: (displayName) => updateMe(accessToken, { displayName }),
    // A read of the profile already on its way carries the old name; stop it
    // landing after the write below.
    onMutate: () => queryClient.cancelQueries({ queryKey: profileKeys.me() }),
    onSuccess: (profile) => {
      session.updateProfile(profile)
      queryClient.setQueryData(profileKeys.me(), profile)
      queryClient.setQueriesData<WorkspaceMember[]>(
        { queryKey: directoryKeys.all() },
        (members) =>
          members?.map((member) =>
            member.user.id === profile.id
              ? { ...member, user: { ...member.user, displayName: profile.displayName } }
              : member,
          ),
      )
      // Written above, and now marked stale too: invalidating cancels a fetch that
      // left with the old name and replaces it with one that asks again, so the
      // old answer cannot be the last word. Observers refetch; the rest wait.
      void queryClient.invalidateQueries({ queryKey: profileKeys.me() })
      void queryClient.invalidateQueries({ queryKey: directoryKeys.all() })
    },
  })
}
