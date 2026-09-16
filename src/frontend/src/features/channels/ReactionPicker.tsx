/**
 * The six-emoji row, opened from a message's hover controls.
 *
 * Six things and no search box, so this is a disclosure rather than a popover
 * library: the set is the server's allowlist and it is small enough to show
 * whole.
 *
 * **It closes when you pick, or when you click the trigger again — not on
 * blur.** Closing on blur reads as tidier and races the option's own click:
 * focus leaves the row, the row unmounts, and the click lands on nothing. That
 * failure is intermittent rather than absolute, which is the worst kind to have
 * underneath an acceptance test.
 */

import { useState } from 'react'

import { REACTION_EMOJI, glyphFor, labelFor } from './reactions'

interface Props {
  onPick: (emoji: string) => void
}

export function ReactionPicker({ onPick }: Props) {
  const [open, setOpen] = useState(false)

  return (
    <span className="relative">
      <button
        type="button"
        data-testid="reaction-picker"
        aria-expanded={open}
        aria-label="Add a reaction"
        onClick={() => setOpen((was) => !was)}
        className="text-xs text-ink-muted underline"
      >
        React
      </button>

      {open && (
        <span className="absolute right-0 z-10 mt-1 flex gap-1 rounded border border-border bg-surface p-1 shadow">
          {REACTION_EMOJI.map((emoji) => (
            <button
              key={emoji}
              type="button"
              data-testid="reaction-option"
              data-emoji={emoji}
              aria-label={labelFor(emoji)}
              onClick={() => {
                onPick(emoji)
                setOpen(false)
              }}
              className="rounded px-1 text-base hover:bg-surface-sunken"
            >
              <span aria-hidden="true">{glyphFor(emoji)}</span>
            </button>
          ))}
        </span>
      )}
    </span>
  )
}
