/**
 * The pure rules of how a direct message is named and ordered in the SPA (issue 5,
 * R6, R7, plan decision 18).
 *
 * Two helpers, because the `#` is presentation: `channelLabel` is the bare name
 * (`general`, or the partner's display name) and feeds `data-channel-name`, which
 * every page object matches against; `channelTitle` adds the `#` for a channel and
 * is what the composer and a search result show.
 *
 * Red: `Failed to resolve import "./directMessages"` — every test needs the module.
 */

import { describe, expect, it, vi } from 'vitest'

import { aChannel } from '../../test/factories'
import { channelLabel, channelTitle, isDm, sortedDms } from './directMessages'

const GRACE = '0199a000-0000-7000-8000-00000000aaaa'
const names: Record<string, string> = {
  [GRACE]: 'Grace Hopper',
  'user-zed': 'Zed',
  'user-alice': 'alice',
  'user-mia': 'Mia',
}
/** `useWorkspaceMembers`'s `nameFor`: a display name, or the 8-character stub. */
const nameFor = (id: string) => names[id] ?? id.slice(0, 8)

const dmWith = (partner: string, id = `dm-${partner}`) =>
  aChannel({ id, kind: 'dm', name: `dm:self:${partner}`, dmPartnerId: partner })

describe('isDm', () => {
  it('is true for a dm and false for every other kind', () => {
    expect(isDm(dmWith(GRACE))).toBe(true)
    expect(isDm(aChannel({ kind: 'public' }))).toBe(false)
    expect(isDm(aChannel({ kind: 'private' }))).toBe(false)
  })
})

describe('channelLabel and channelTitle', () => {
  it('give a channel its bare name and its #name', () => {
    const channel = aChannel({ name: 'general' })

    expect(channelLabel(channel, nameFor)).toBe('general')
    expect(channelTitle(channel, nameFor)).toBe('#general')
  })

  it('give a dm the partner’s display name, with no # in either, never the stored name', () => {
    const dm = dmWith(GRACE)

    expect(channelLabel(dm, nameFor)).toBe('Grace Hopper')
    expect(channelTitle(dm, nameFor)).toBe('Grace Hopper')
  })

  it('ask the directory about the partner, not about the caller or the stored name', () => {
    const lookup = vi.fn(nameFor)

    channelLabel(dmWith(GRACE), lookup)
    channelTitle(dmWith(GRACE), lookup)

    expect(lookup.mock.calls).toEqual([[GRACE], [GRACE]])
  })

  it('label a partner missing from the directory with the shortId stub', () => {
    const stranger = '0199a000-0000-7000-8000-00000000ffff'

    expect(channelLabel(dmWith(stranger), nameFor)).toBe('0199a000')
    expect(channelTitle(dmWith(stranger), nameFor)).toBe('0199a000')
  })
})

describe('sortedDms', () => {
  it('returns only the dms, by the partner’s name, whatever order the server and the ids give', () => {
    // Server order is Zed, Mia, alice; id order is Zed, alice, Mia; name order (localeCompare)
    // is alice, Mia, Zed — and plain code-point order would put `alice` last.
    const zed = dmWith('user-zed', 'id-1')
    const alice = dmWith('user-alice', 'id-2')
    const mia = dmWith('user-mia', 'id-3')
    const channels = [zed, aChannel({ name: 'general', id: 'id-0' }), mia, alice]

    const sorted = sortedDms(channels, nameFor)

    expect(sorted.map((c) => channelLabel(c, nameFor))).toEqual(['alice', 'Mia', 'Zed'])
    expect(sorted).toHaveLength(3)
  })

  it('is empty when there are no dms, and leaves its input as it was', () => {
    const channels = [aChannel({ name: 'general' }), aChannel({ name: 'random' })]
    const before = [...channels]

    expect(sortedDms(channels, nameFor)).toEqual([])
    expect(channels).toEqual(before)
  })
})
