/**
 * Switching the active workspace.
 *
 * Not a UI filter: an access token carries exactly one workspace in its `wsp`
 * claim, so switching exchanges the refresh token for a token scoped to the
 * other one (Conventions §5.4). Everything fetched under the old token belongs
 * to the old workspace, which is why the query keys carry the workspace id —
 * see `useChannels`.
 */

import { Link, useLocation } from 'react-router-dom'

import * as session from '../../lib/auth/session'
import type { Session } from '../../lib/auth/session'
import { useWorkspaceMembers } from './useWorkspaceMembers'

interface Props {
  current: Session
}

export function WorkspaceSwitcher({ current }: Props) {
  const active = current.workspaces.find((w) => w.id === current.activeWorkspaceId)
  const location = useLocation()
  // The name comes from the workspace directory, the same place every author line
  // reads, so the sidebar and one's own messages change on the same fetch. The
  // session's copy is only as fresh as the last renewal; it is the fallback while
  // the directory has no entry.
  const { members } = useWorkspaceMembers(current.accessToken, current.activeWorkspaceId)
  const ownName =
    members.find((member) => member.user.id === current.profile.id)?.user.displayName ??
    current.profile.displayName

  return (
    <div className="border-b border-border px-3 py-4">
      <p data-testid="workspace-name" className="text-sm font-semibold text-ink">
        {active?.name ?? 'No workspace'}
      </p>
      <Link
        to="/settings"
        // Remembered so Settings can send the user back to the channel they left.
        state={{ from: location.pathname + location.search }}
        data-testid="current-user"
        className="text-xs text-ink-muted underline"
      >
        {ownName}
      </Link>

      {current.workspaces.length > 1 && (
        <ul data-testid="workspace-switcher" className="mt-2 flex flex-col gap-1">
          {current.workspaces.map((workspace) => (
            <li key={workspace.id}>
              <button
                type="button"
                data-testid="workspace-option"
                data-workspace-name={workspace.name}
                disabled={workspace.id === current.activeWorkspaceId}
                onClick={() => void session.changeWorkspace(workspace.id)}
                className="text-xs text-ink-muted underline disabled:no-underline disabled:opacity-50"
              >
                {workspace.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
