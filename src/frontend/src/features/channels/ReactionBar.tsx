/**
 * The chips under a message: one per emoji anyone used, lit when it is yours.
 *
 * Renders nothing at all when nobody has reacted, so an unreacted message looks
 * exactly as it did before this feature existed — a bar of empty outlines under
 * every line of a conversation would be a permanent tax on reading it.
 *
 * `aria-pressed` and not only a colour. "Mine" is a state, and a chip that
 * differs by background alone says nothing to a screen reader and little to
 * anyone who cannot separate those two greys.
 *
 * The counts come from the server on every read and from `reaction_changed`
 * live; nothing here derives one, so two windows cannot disagree about a total.
 */

import type { Reaction } from '../../lib/api/messaging'
import { glyphFor, labelFor } from './reactions'

interface Props {
  reactions: Reaction[]
  onToggle: (emoji: string) => void
}

export function ReactionBar({ reactions, onToggle }: Props) {
  if (reactions.length === 0) return null

  return (
    <div className="mt-1 flex flex-wrap gap-1">
      {reactions.map((reaction) => (
        <button
          key={reaction.emoji}
          type="button"
          data-testid="reaction-chip"
          data-emoji={reaction.emoji}
          data-count={reaction.count}
          aria-pressed={reaction.reacted}
          aria-label={`${labelFor(reaction.emoji)}, ${reaction.count}`}
          onClick={() => onToggle(reaction.emoji)}
          className={`flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs ${
            reaction.reacted
              ? 'border-accent bg-accent/10 text-ink'
              : 'border-border text-ink-muted'
          }`}
        >
          <span aria-hidden="true">{glyphFor(reaction.emoji)}</span>
          <span>{reaction.count}</span>
        </button>
      ))}
    </div>
  )
}
