/**
 * Settings: the signed-in user's name and their one preference so far, the clock
 * (issue gh-3 Req 5 to 8; registers D28 and D46).
 *
 * The form is drawn from the server's copy of the profile, fetched on every visit
 * (`refetchOnMount: 'always'`) and not drawn until that fetch has landed, so the
 * session's or the cache's older name is never briefly editable. The draft lives
 * in this component only: leaving drops it without asking, and a workspace switch
 * changes nothing here because nothing on the page is keyed by the token.
 *
 * Save is gated on the rules the browser can know without a copy of the Unicode
 * tables: not empty, not over 100 code points, and different from the stored
 * name once trimmed and composed. Which characters are refused is the server's
 * 400, shown on the field.
 */

import { type FormEvent, useState } from 'react'
import { Link } from 'react-router-dom'

import { ProblemBanner } from '../../components/ProblemBanner'
import { ProblemError } from '../../lib/api/client'
import type { Clock } from '../../lib/auth/api'
import { useChatStore } from '../../stores/chat'
import { usePreferences, useSetClock } from './usePreferences'
import { useProfile, useUpdateDisplayName } from './useProfile'

const MAX_NAME_LENGTH = 100

interface Props {
  accessToken: string
  userId: string
}

const CLOCK_CHOICES: { value: Clock | null; label: string }[] = [
  { value: null, label: 'Automatic' },
  { value: '12h', label: '12-hour' },
  { value: '24h', label: '24-hour' },
]

export function SettingsPage({ accessToken, userId }: Props) {
  const lastChannelId = useChatStore((state) => state.lastChannelId)
  const profile = useProfile(accessToken, userId)
  const preferences = usePreferences(accessToken, userId)
  const rename = useUpdateDisplayName(accessToken, userId)
  const setClock = useSetClock(accessToken, userId)
  const [draft, setDraft] = useState<string | null>(null)

  const stored = profile.isFetchedAfterMount ? profile.data : undefined
  const value = draft ?? stored?.displayName ?? ''
  const candidate = value.trim().normalize('NFC')
  const canSave =
    stored !== undefined &&
    candidate !== '' &&
    [...candidate].length <= MAX_NAME_LENGTH &&
    candidate !== stored.displayName &&
    !rename.isPending

  const problem = rename.error instanceof ProblemError ? rename.error : undefined
  const nameError = problem?.fieldError('displayName')
  const clock = preferences.data?.clock ?? null

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!canSave) return
    rename.mutate(candidate, { onSuccess: () => setDraft(null) })
  }

  return (
    <div className="mx-auto flex max-w-xl flex-col gap-8 p-6">
      <header className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold text-ink">Settings</h1>
        <Link
          to={lastChannelId ? `/c/${lastChannelId}` : '/'}
          data-testid="settings-back"
          className="text-sm text-accent underline"
        >
          Back to chat
        </Link>
      </header>

      <section className="flex flex-col gap-3">
        <h2 className="text-base font-semibold text-ink">Profile</h2>
        {stored === undefined ? (
          // No form until the server has answered: the session's or the cache's
          // older name must never be briefly editable.
          profile.isError ? (
            <ProblemBanner error={profile.error} />
          ) : (
            <p className="text-sm text-ink-muted">Loading…</p>
          )
        ) : (
          <form onSubmit={submit} className="flex flex-col gap-2">
            <label className="flex flex-col gap-1 text-sm text-ink">
              <span>Display name</span>
              <input
                aria-label="Display name"
                data-testid="settings-display-name"
                value={value}
                onChange={(event) => {
                  if (rename.isError || rename.isSuccess) rename.reset()
                  setDraft(event.target.value)
                }}
                autoComplete="off"
                className="rounded border border-border bg-surface px-2 py-1 text-ink"
              />
            </label>
            {nameError && (
              <p
                data-testid="settings-display-name-error"
                role="alert"
                className="text-sm text-danger"
              >
                {nameError}
              </p>
            )}
            {!nameError && <ProblemBanner error={rename.error} />}
            <div className="flex items-center gap-3">
              <button
                type="submit"
                data-testid="settings-save"
                disabled={!canSave}
                className="rounded bg-accent px-3 py-1 text-sm font-medium text-accent-ink disabled:opacity-60"
              >
                Save
              </button>
              {rename.isSuccess && draft === null && (
                <p role="status" data-testid="settings-saved" className="text-sm text-ink-muted">
                  Saved
                </p>
              )}
            </div>
          </form>
        )}
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-base font-semibold text-ink">Preferences</h2>
        <fieldset className="flex flex-col gap-1">
          <legend className="text-sm text-ink">Clock</legend>
          {CLOCK_CHOICES.map((choice) => (
            <label key={choice.label} className="flex items-center gap-2 text-sm text-ink">
              <input
                type="radio"
                name="clock"
                checked={clock === choice.value}
                onChange={() => setClock.mutate(choice.value)}
              />
              {choice.label}
            </label>
          ))}
        </fieldset>
        <ProblemBanner error={setClock.error} />
      </section>
    </div>
  )
}
