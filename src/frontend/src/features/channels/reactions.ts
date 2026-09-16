/**
 * What the server's shortcodes look like on screen.
 *
 * The server sends `"thumbsup"`, never `"👍"`, so there is no unicode
 * normalisation anywhere in the wire format and this file is the only place
 * that decides what gets drawn.
 *
 * **The order is the server's allowlist order, and that is also display order.**
 * Counts change constantly, and chips sorted by count would move under the
 * pointer between somebody deciding to click and clicking.
 *
 * Keep in step with `REACTION_EMOJI` in `messaging/reactions.py`. A shortcode
 * missing from here renders as its own name rather than a blank, so a server
 * that widens the set before the SPA does degrades legibly instead of showing
 * an empty chip.
 */

export const REACTION_EMOJI = ['thumbsup', 'heart', 'tada', 'smile', 'eyes', 'check'] as const

const GLYPHS: Record<string, string> = {
  thumbsup: '👍',
  heart: '❤️',
  tada: '🎉',
  smile: '😄',
  eyes: '👀',
  check: '✅',
}

/** What a screen reader says: an emoji on its own is announced inconsistently. */
const LABELS: Record<string, string> = {
  thumbsup: 'thumbs up',
  heart: 'heart',
  tada: 'celebrate',
  smile: 'smile',
  eyes: 'eyes',
  check: 'check',
}

const ORDER = new Map<string, number>(REACTION_EMOJI.map((emoji, index) => [emoji, index]))

/** Where an unknown shortcode sorts: after everything known, in a stable place. */
const LAST = Number.MAX_SAFE_INTEGER

export function glyphFor(emoji: string): string {
  return GLYPHS[emoji] ?? emoji
}

export function labelFor(emoji: string): string {
  return LABELS[emoji] ?? emoji
}

export function inAllowlistOrder<T extends { emoji: string }>(reactions: T[]): T[] {
  return [...reactions].sort((a, b) => (ORDER.get(a.emoji) ?? LAST) - (ORDER.get(b.emoji) ?? LAST))
}
