/**
 * `/settings`: Profile and Preferences, inside the chat shell so the sidebar (and
 * the name it shows) stays on screen while the name is changed.
 *
 * Leaving drops an unsaved edit without asking — it is one field, and nothing
 * else on the page can lose work. A workspace switch leaves the page mounted: a
 * profile and a preference are the user's, not the workspace's.
 *
 * "Back to chat" goes to the last channel opened **in the active workspace**,
 * else the start: after a switch the old channel belongs to another tenant.
 */

import { Link } from 'react-router-dom'

import { useChatStore } from '../../stores/chat'
import { PreferencesSection } from './PreferencesSection'
import { ProfileSection } from './ProfileSection'

interface Props {
  accessToken: string
  workspaceId: string | null
}

export function SettingsPage({ accessToken, workspaceId }: Props) {
  const lastChannel = useChatStore((state) => state.lastChannel)
  const back =
    lastChannel && lastChannel.workspaceId === workspaceId ? `/c/${lastChannel.channelId}` : '/'

  return (
    <div data-testid="settings-page" className="mx-auto flex max-w-xl flex-col gap-8 p-6">
      <header className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold text-ink">Settings</h1>
        <Link to={back} className="text-sm text-accent underline">
          Back to chat
        </Link>
      </header>
      <ProfileSection accessToken={accessToken} />
      <PreferencesSection accessToken={accessToken} />
    </div>
  )
}
