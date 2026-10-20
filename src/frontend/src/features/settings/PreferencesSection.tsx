/**
 * Preferences: the clock (issue gh-3, Req 7, 8).
 *
 * A choice shows at once and saves at once, sending only the key that changed so
 * a second tab's other preferences are not overwritten. How overlapping saves and
 * failures end is `useUpdatePreferences`'s; this component only draws the cached
 * value and reports the latest save's error. The read is fresh on every visit
 * and on window focus, which is how a second tab's change arrives.
 */

import { ProblemBanner } from '../../components/ProblemBanner'
import type { Clock } from '../../lib/auth/api'
import { usePreferences, useUpdatePreferences } from './usePreferences'

interface Props {
  accessToken: string
}

const OPTIONS: { value: Clock | null; label: string }[] = [
  { value: null, label: 'Automatic' },
  { value: '12h', label: '12-hour' },
  { value: '24h', label: '24-hour' },
]

export function PreferencesSection({ accessToken }: Props) {
  const { data } = usePreferences(accessToken, { refetchOnMount: 'always' })
  const save = useUpdatePreferences(accessToken)
  const clock = data?.clock ?? null

  return (
    <section aria-labelledby="preferences-heading" className="flex flex-col gap-3">
      <h2 id="preferences-heading" className="text-lg font-semibold text-ink">
        Preferences
      </h2>

      <div role="radiogroup" aria-labelledby="clock-label" className="flex flex-col gap-1">
        <span id="clock-label" className="text-sm font-medium text-ink">
          Clock
        </span>
        <p className="text-xs text-ink-muted">
          How times are shown on messages, thread summaries and search results.
        </p>
        {OPTIONS.map((option) => (
          <label key={option.label} className="flex items-center gap-2 text-sm text-ink">
            <input
              type="radio"
              name="clock"
              checked={clock === option.value}
              onChange={() => save.mutate({ clock: option.value })}
            />
            {option.label}
          </label>
        ))}
      </div>

      <ProblemBanner error={save.error} />
    </section>
  )
}
