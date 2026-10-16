/**
 * Settings: the name others see you by, and how times are written.
 *
 * Reached from the signed-in name in the sidebar, inside the chat shell, so the
 * shell's socket survives the round trip. Two independent forms:
 *
 * - **Profile** — the display name. It starts from what Auth holds *now*: the form
 *   does not exist until `GET /users/me` has answered since this page mounted, so
 *   a stale cached or session name is never offered as the value. Save is offered
 *   only for a changed name of a valid length; which characters are refused is the
 *   server's rule, shown on the field rather than mirrored here.
 * - **Clock** — Automatic, 12-hour or 24-hour. A choice saves at once. The radios
 *   are disabled until the server has answered since mount, for the same reason.
 *
 * An unsaved edit is component state and is dropped, without a warning, when the
 * page is left.
 */

import { type FormEvent, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'

import { type Clock, ProblemError } from '../../lib/auth/api'
import { useProfile, useUpdateDisplayName } from './useProfile'
import { usePreferences, useSetClock } from './usePreferences'

const MAX_LENGTH = 100

/** Where "Back to chat" goes: the channel the user came from, else the start. */
function backTarget(state: unknown): string {
  const from = (state as { from?: unknown } | null)?.from
  return typeof from === 'string' && from.startsWith('/c/') ? from : '/'
}

function ProfileForm({ accessToken, current }: { accessToken: string; current: string }) {
  const rename = useUpdateDisplayName(accessToken)
  const [value, setValue] = useState(current)
  const [saved, setSaved] = useState(false)

  const trimmed = value.trim()
  const valid = trimmed.length >= 1 && trimmed.length <= MAX_LENGTH
  const changed = trimmed !== current
  // The server's words when it gave field errors (a refused or taken name),
  // else the problem's own message.
  const error =
    rename.error instanceof ProblemError
      ? (rename.error.fieldError('displayName') ?? rename.error.message)
      : rename.error?.message

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!valid || !changed || rename.isPending) return
    rename.mutate(trimmed, {
      onSuccess: () => {
        setValue(trimmed)
        setSaved(true)
      },
    })
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-2">
      <label className="flex flex-col gap-1 text-sm text-ink">
        Display name
        <input
          type="text"
          data-testid="display-name-input"
          value={value}
          onChange={(event) => {
            setValue(event.target.value)
            setSaved(false)
            rename.reset()
          }}
          className="rounded border border-border px-2 py-1"
        />
      </label>
      {error && <p className="text-sm text-danger">{error}</p>}
      <div className="flex items-center gap-3">
        <button
          type="submit"
          data-testid="display-name-save"
          disabled={!valid || !changed || rename.isPending}
          className="rounded bg-accent px-3 py-1 text-sm font-medium text-accent-ink disabled:opacity-50"
        >
          Save
        </button>
        {saved && !error && (
          <p role="status" data-testid="display-name-saved" className="text-sm text-ink-muted">
            Saved
          </p>
        )}
      </div>
    </form>
  )
}

const CLOCK_CHOICES: { label: string; value: Clock | null }[] = [
  { label: 'Automatic', value: null },
  { label: '12-hour', value: '12h' },
  { label: '24-hour', value: '24h' },
]

export function SettingsPage({ accessToken }: { accessToken: string }) {
  const location = useLocation()
  const profile = useProfile(accessToken)
  const preferences = usePreferences(accessToken, { refetchOnMount: 'always' })
  const setClock = useSetClock(accessToken)

  const clock = preferences.data?.clock ?? null
  // Not offered until the server has answered since mount, so a stale cached
  // choice can neither be shown as the truth nor be the one that is clicked. A
  // failed read still unlocks them, or one bad request would lock the section.
  const clockReady = preferences.isFetchedAfterMount || preferences.isError

  return (
    <div className="mx-auto flex max-w-xl flex-col gap-6 p-6">
      <div className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold text-ink">Settings</h1>
        <Link to={backTarget(location.state)} className="text-sm text-accent underline">
          Back to chat
        </Link>
      </div>

      <section aria-labelledby="settings-profile" className="flex flex-col gap-2">
        <h2 id="settings-profile" className="text-lg font-medium text-ink">
          Profile
        </h2>
        {profile.isFetchedAfterMount && profile.data ? (
          <ProfileForm accessToken={accessToken} current={profile.data.displayName} />
        ) : profile.isError ? (
          <p className="text-sm text-danger">Your profile could not be loaded.</p>
        ) : (
          <p className="text-sm text-ink-muted">Loading…</p>
        )}
      </section>

      <fieldset className="flex flex-col gap-2">
        <legend className="text-lg font-medium text-ink">Clock</legend>
        {CLOCK_CHOICES.map((choice) => (
          <label key={choice.label} className="flex items-center gap-2 text-sm text-ink">
            <input
              type="radio"
              name="clock"
              checked={clock === choice.value}
              disabled={!clockReady}
              onChange={() => setClock.mutate(choice.value)}
            />
            {choice.label}
          </label>
        ))}
        {setClock.isError && (
          <p role="alert" className="text-sm text-danger">
            Your clock choice could not be saved.
          </p>
        )}
      </fieldset>
    </div>
  )
}
