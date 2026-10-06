/**
 * What a direct message is called, and which channels are one (issue 5, R7).
 *
 * A DM is a `kind: 'dm'` channel whose stored `name` is a pair key nobody should
 * read (`dm:{id}:{id}`). Every place the SPA shows a channel's name goes through
 * one of the two helpers here, so a DM is named after the other person
 * everywhere and the pair key never reaches the screen.
 *
 * Two helpers, because the `#` is presentation. `channelLabel` is the **bare**
 * name — `general`, or the partner's display name — and is what `data-channel-name`
 * and the header carry, so every existing lookup of a channel by name still
 * matches. `channelTitle` adds the `#` for a channel only, for the places that
 * read as a sentence: the composer's `Message #general`, a search result.
 *
 * `nameFor` is the workspace directory's: it falls back to a shortened id for a
 * partner it doesn't know, so a DM never renders blank.
 */

import type { Channel } from '../../lib/api/messaging'

type NameFor = (userId: string) => string

export function isDm(channel: Channel): boolean {
  return channel.kind === 'dm'
}

/** The partner's id for a DM. A DM the server sent without one is a server bug. */
function partnerOf(channel: Channel): string {
  return channel.dmPartnerId ?? channel.id
}

export function channelLabel(channel: Channel, nameFor: NameFor): string {
  return isDm(channel) ? nameFor(partnerOf(channel)) : channel.name
}

export function channelTitle(channel: Channel, nameFor: NameFor): string {
  return isDm(channel) ? channelLabel(channel, nameFor) : `#${channel.name}`
}

/** The DMs only, by the partner's name — the server's order means nothing here. */
export function sortedDms(channels: Channel[], nameFor: NameFor): Channel[] {
  return channels
    .filter(isDm)
    .sort((a, b) => channelLabel(a, nameFor).localeCompare(channelLabel(b, nameFor)))
}
