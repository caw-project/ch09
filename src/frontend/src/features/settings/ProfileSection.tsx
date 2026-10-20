/**
 * Profile: the user's display name (issue gh-3, Req 1, 2, 5, 8).
 *
 * The field is seeded from the server **on every visit** and only once this
 * visit's fetch has landed (`isFetchedAfterMount`): showing the cached name and
 * then following the fetch would risk overwriting what the user has already
 * typed. Until then — and when the fetch failed — there is no field.
 *
 * The character rules are the server's alone, shown from its 400; this form
 * copies none of them. What it does check is only what it can check without
 * restating a rule: that Save would send something different from the stored name,
 * that is not empty and not over 100 code points (a length the form states in its
 * hint). Trimming and NFC are done here too, so a padded or decomposed copy of
 * the stored name is "unchanged".
 *
 * "Saved" stays until the field is edited. The rename's side effects (the sidebar,
 * the cached directories) live in `useUpdateDisplayName`, so they survive leaving
 * the page mid-save.
 */

import { useState } from 'react'

import { ProblemBanner } from '../../components/ProblemBanner'
import { ProblemError } from '../../lib/api/client'
import { useProfile, useUpdateDisplayName } from './useProfile'

const MAX_LENGTH = 100

interface Props {
  accessToken: string
}

function normalised(value: string): string {
  return value.trim().normalize('NFC')
}

export function ProfileSection({ accessToken }: Props) {
  const profile = useProfile(accessToken)

  return (
    <section aria-labelledby="profile-heading" className="flex flex-col gap-3">
      <h2 id="profile-heading" className="text-lg font-semibold text-ink">
        Profile
      </h2>
      {profile.isError ? (
        <ProblemBanner error={profile.error} />
      ) : !profile.isFetchedAfterMount || profile.data === undefined ? (
        <p className="text-sm text-ink-muted">Loading…</p>
      ) : (
        <NameForm
          accessToken={accessToken}
          storedName={profile.data.displayName.normalize('NFC')}
        />
      )}
    </section>
  )
}

function NameForm({ accessToken, storedName }: { accessToken: string; storedName: string }) {
  // Seeded once, from this visit's fetch; a later refetch does not touch the field.
  const [value, setValue] = useState(storedName)
  const [saved, setSaved] = useState(false)
  const rename = useUpdateDisplayName(accessToken)

  const candidate = normalised(value)
  const length = [...candidate].length
  const canSave =
    length > 0 && length <= MAX_LENGTH && candidate !== storedName && !rename.isPending

  const problem = rename.error
  const fieldMessage =
    problem instanceof ProblemError && problem.status < 500
      ? (problem.fieldError('displayName') ?? problem.message)
      : undefined

  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(event) => {
        event.preventDefault()
        if (!canSave) return
        setSaved(false)
        rename.mutate(candidate, { onSuccess: () => setSaved(true) })
      }}
    >
      <label htmlFor="display-name" className="text-sm font-medium text-ink">
        Display name
      </label>
      <input
        id="display-name"
        data-testid="profile-name-input"
        type="text"
        value={value}
        onChange={(event) => {
          setValue(event.target.value)
          setSaved(false)
        }}
        aria-invalid={fieldMessage ? true : undefined}
        aria-describedby="display-name-hint"
        className="rounded border border-border bg-surface px-3 py-2 text-sm text-ink"
      />
      <p id="display-name-hint" className="text-xs text-ink-muted">
        1 to 100 characters. Names are unique across CollabHub.
      </p>

      {fieldMessage ? (
        <p role="alert" className="text-sm text-danger">
          {fieldMessage}
        </p>
      ) : (
        problem && <ProblemBanner error={problem} />
      )}

      <div className="flex items-center gap-3">
        <button
          type="submit"
          data-testid="profile-save"
          disabled={!canSave}
          className="rounded bg-accent px-4 py-2 text-sm font-medium text-accent-ink disabled:opacity-50"
        >
          Save
        </button>
        {saved && !rename.isPending && (
          <span data-testid="profile-saved" className="text-sm text-ink-muted">
            Saved
          </span>
        )}
      </div>
    </form>
  )
}
