/**
 * Settings: your display name, and the clock the app draws times with.
 *
 * Two sections, two kinds of save. The **name** is a form with a Save button,
 * because a rename can be refused (invalid, or taken) and the typed text has to
 * stay put while the reason shows. The **clock** saves the moment it is chosen —
 * it is a radio group with nothing to get wrong — shows at once and is put back
 * if the server refuses (`useUpdateClock`).
 *
 * **The form shows only what this visit fetched.** Both reads are `fresh`, and
 * nothing editable renders until both have answered (`isFetchedAfterMount`), so a
 * cached name from earlier in the session — or another tab's — is never offered
 * as the value to edit. The query keys carry no token: a workspace switch hands
 * the page a new one without refetching anything or disturbing an unsaved edit,
 * because the name and the clock belong to the person, not the workspace.
 *
 * Save is enabled for a name that is changed and possible. "Possible" is only
 * the cheap part of the server's rule — 1 to 100 *code points* after
 * `trim().normalize('NFC')`, counted as `[...s].length` as the server's `len()`
 * does, since `s.length` counts UTF-16 units and would disable names the server
 * accepts. Which characters are allowed is the server's to judge; its 400 shows
 * on the field.
 */

import { type FormEvent, useState } from 'react'
import { Link } from 'react-router-dom'

import { ProblemError } from '../../lib/api/client'
import type { Clock } from '../../lib/auth/api'
import { useChatStore } from '../../stores/chat'
import { usePreferences, useUpdateClock } from './usePreferences'
import { useProfile, useUpdateDisplayName } from './useProfile'

interface Props {
  accessToken: string
}

const MAX_LENGTH = 100

const CLOCK_CHOICES: { label: string; value: Clock | null }[] = [
  { label: 'Automatic', value: null },
  { label: '12-hour', value: '12h' },
  { label: '24-hour', value: '24h' },
]

export function SettingsPage({ accessToken }: Props) {
  const lastChannelId = useChatStore((state) => state.lastChannelId)
  const profile = useProfile(accessToken, { fresh: true })
  const preferences = usePreferences(accessToken, { fresh: true })
  const ready =
    profile.isFetchedAfterMount &&
    preferences.isFetchedAfterMount &&
    profile.data !== undefined &&
    preferences.data !== undefined

  return (
    <div data-testid="settings-page" className="mx-auto flex max-w-xl flex-col gap-8 p-6">
      <header className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold text-ink">Settings</h1>
        <Link
          to={lastChannelId ? `/c/${lastChannelId}` : '/'}
          data-testid="settings-back"
          className="text-sm text-accent hover:underline"
        >
          Back to chat
        </Link>
      </header>

      {ready ? (
        <>
          <NameSection accessToken={accessToken} storedName={profile.data.displayName} />
          <ClockSection accessToken={accessToken} clock={preferences.data.clock} />
        </>
      ) : profile.isError || preferences.isError ? (
        <p role="status" className="text-sm text-ink-muted">
          Your settings could not be loaded. Reload the page to try again.
        </p>
      ) : (
        <p className="text-sm text-ink-muted">Loading…</p>
      )}
    </div>
  )
}

function NameSection({ accessToken, storedName }: { accessToken: string; storedName: string }) {
  const [draft, setDraft] = useState(storedName)
  const rename = useUpdateDisplayName(accessToken)

  const typed = draft.trim().normalize('NFC')
  const length = [...typed].length
  const canSave =
    length >= 1 && length <= MAX_LENGTH && typed !== storedName && !rename.isPending

  const error =
    rename.error instanceof ProblemError
      ? (rename.error.fieldError('displayName') ?? rename.error.message)
      : rename.error?.message

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!canSave) return
    rename.mutate(typed, { onSuccess: (saved) => setDraft(saved.displayName) })
  }

  return (
    <section aria-labelledby="settings-profile" className="flex flex-col gap-3">
      <h2 id="settings-profile" className="text-lg font-medium text-ink">
        Profile
      </h2>
      <form onSubmit={submit} className="flex flex-col gap-2">
        <label htmlFor="settings-name" className="text-sm text-ink-muted">
          Display name
        </label>
        <input
          id="settings-name"
          data-testid="settings-display-name"
          type="text"
          value={draft}
          aria-invalid={error ? true : undefined}
          onChange={(event) => {
            setDraft(event.target.value)
            // Editing starts a new attempt: neither the last refusal nor "Saved" describes it.
            rename.reset()
          }}
          className="rounded border border-border bg-surface px-3 py-2 text-ink"
        />
        {error && (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        )}
        <div className="flex items-center gap-3">
          <button
            type="submit"
            data-testid="settings-save"
            disabled={!canSave}
            className="rounded bg-accent px-4 py-2 font-medium text-accent-ink disabled:opacity-50"
          >
            Save
          </button>
          {rename.isSuccess && (
            <span data-testid="settings-saved" role="status" className="text-sm text-ink-muted">
              Saved
            </span>
          )}
        </div>
      </form>
    </section>
  )
}

function ClockSection({ accessToken, clock }: { accessToken: string; clock: Clock | undefined }) {
  const updateClock = useUpdateClock(accessToken)

  return (
    <section aria-labelledby="settings-preferences" className="flex flex-col gap-3">
      <h2 id="settings-preferences" className="text-lg font-medium text-ink">
        Preferences
      </h2>
      <div role="radiogroup" aria-label="Clock" className="flex flex-col gap-1">
        {CLOCK_CHOICES.map((choice) => (
          <label key={choice.label} className="flex items-center gap-2 text-sm text-ink">
            <input
              type="radio"
              name="clock"
              checked={(clock ?? null) === choice.value}
              onChange={() => updateClock.mutate(choice.value)}
            />
            {choice.label}
          </label>
        ))}
      </div>
      {updateClock.isError && (
        <p role="alert" className="text-sm text-danger">
          {updateClock.error.message}
        </p>
      )}
    </section>
  )
}
