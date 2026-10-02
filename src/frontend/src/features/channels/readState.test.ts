import { describe, expect, it } from 'vitest'

import type { State } from '../../lib/auth/session'
import { aMessage, aSession, messageIdAt } from '../../test/factories'
import {
  badgeLabel,
  badgeText,
  captureFor,
  findDivider,
  isAtOrPast,
  isLiveWorkspace,
  readTarget,
} from './readState'

const ADA = 'user-ada'
const GRACE = 'user-grace'

const m = (n: number, overrides: Parameters<typeof aMessage>[0] = {}) =>
  aMessage({ id: messageIdAt(n), authorId: GRACE, ...overrides })
const mine = (n: number) => m(n, { authorId: ADA })
const deleted = (n: number) => m(n, { deletedAt: '2026-09-15T10:00:00Z', body: '' })
const pending = () => aMessage({ id: 'temp:0f0f', authorId: ADA })

describe('badgeText and badgeLabel', () => {
  it('shows 99 as 99 and 100 as 99+', () => {
    expect(badgeText(1)).toBe('1')
    expect(badgeText(99)).toBe('99')
    expect(badgeText(100)).toBe('99+')
    expect(badgeText(4821)).toBe('99+')
  })

  it('is singular for one and plural otherwise', () => {
    expect(badgeLabel(1)).toBe('1 unread message')
    expect(badgeLabel(2)).toBe('2 unread messages')
  })

  it('uses the number displayed', () => {
    expect(badgeLabel(99)).toBe('99 unread messages')
    expect(badgeLabel(100)).toBe('99+ unread messages')
  })
})

describe('isAtOrPast', () => {
  it('treats no marker as never past, and equal as past, older as not and newer as past', () => {
    expect(isAtOrPast(null, messageIdAt(1))).toBe(false)
    expect(isAtOrPast(undefined, messageIdAt(1))).toBe(false)
    expect(isAtOrPast(messageIdAt(3), messageIdAt(3))).toBe(true)
    expect(isAtOrPast(messageIdAt(2), messageIdAt(3))).toBe(false)
    expect(isAtOrPast(messageIdAt(4), messageIdAt(3))).toBe(true)
  })
})

describe('readTarget', () => {
  it('skips a pending send at the end', () => {
    expect(readTarget([m(1), m(2), pending()])).toBe(messageIdAt(2))
  })

  it('includes the user’s own message and a tombstone, each newest in turn', () => {
    expect(readTarget([m(1), mine(2)])).toBe(messageIdAt(2))
    expect(readTarget([m(1), deleted(2)])).toBe(messageIdAt(2))
  })

  it('is null with nothing confirmed loaded', () => {
    expect(readTarget([])).toBeNull()
    expect(readTarget([pending()])).toBeNull()
  })
})

describe('captureFor', () => {
  it('keeps the marker and takes the newest confirmed message as the ceiling', () => {
    expect(captureFor(messageIdAt(1), [m(1), m(2), m(3), pending()])).toEqual({
      lastReadId: messageIdAt(1),
      ceilingId: messageIdAt(3),
    })
    expect(captureFor(null, [])).toEqual({ lastReadId: null, ceilingId: null })
  })
})

describe('findDivider', () => {
  const capture = (lastRead: number | null, ceiling: number) => ({
    lastReadId: lastRead === null ? null : messageIdAt(lastRead),
    ceilingId: messageIdAt(ceiling),
  })

  it('sits above the first message after the marker by someone else', () => {
    const messages = [m(1), m(2), m(3), m(4), m(5)]
    expect(findDivider(messages, capture(2, 5), ADA, false)).toBe(messageIdAt(3))
  })

  it('skips the user’s own messages', () => {
    const messages = [m(1), m(2), mine(3), m(4), m(5)]
    expect(findDivider(messages, capture(2, 5), ADA, false)).toBe(messageIdAt(4))
  })

  it('skips tombstones', () => {
    const messages = [m(1), m(2), deleted(3), m(4), m(5)]
    expect(findDivider(messages, capture(2, 5), ADA, false)).toBe(messageIdAt(4))
  })

  it('has no divider for a null marker, though messages would qualify', () => {
    const messages = [m(1), m(2), m(3)]
    expect(findDivider(messages, capture(null, 3), ADA, false)).toBeNull()
    // The same messages with a marker do qualify.
    expect(findDivider(messages, capture(1, 3), ADA, false)).toBe(messageIdAt(2))
  })

  it('draws nothing above the ceiling: a message that arrived during the visit', () => {
    const messages = [m(1), m(2), mine(3), m(4)]
    // Marker at 2; the only message by someone else after it is 4, past the ceiling at 3.
    expect(findDivider(messages, capture(2, 3), ADA, false)).toBeNull()
    // With the ceiling at 4 the same message qualifies.
    expect(findDivider(messages, capture(2, 4), ADA, false)).toBe(messageIdAt(4))
  })

  it('has none while the boundary is older than the loaded pages', () => {
    const messages = [m(5), m(6), m(7)]
    expect(findDivider(messages, capture(2, 7), ADA, true)).toBeNull()
  })

  it('finds it once a page holding the boundary has loaded', () => {
    const messages = [m(2), m(3), m(4), m(5)]
    expect(findDivider(messages, capture(2, 5), ADA, true)).toBe(messageIdAt(3))
  })

  it('finds it with no older page, even if the marker precedes everything loaded', () => {
    const messages = [m(5), m(6), m(7)]
    expect(findDivider(messages, capture(2, 7), ADA, false)).toBe(messageIdAt(5))
  })

  it('has none when the channel was read to the end', () => {
    const messages = [m(1), m(2), m(3), m(4)]
    expect(findDivider(messages, capture(4, 4), ADA, false)).toBeNull()
    // One message short of the end, there is one.
    expect(findDivider(messages, capture(3, 4), ADA, false)).toBe(messageIdAt(4))
  })
})

describe('isLiveWorkspace', () => {
  it('is true for this workspace, false for another, false signed out, true while loading', () => {
    const signedIn = (workspaceId: string | null): State => ({
      status: 'signedIn',
      session: aSession({ activeWorkspaceId: workspaceId }),
    })

    expect(isLiveWorkspace(signedIn('ws-1'), 'ws-1')).toBe(true)
    expect(isLiveWorkspace(signedIn('ws-2'), 'ws-1')).toBe(false)
    expect(isLiveWorkspace({ status: 'signedOut' }, 'ws-1')).toBe(false)
    expect(isLiveWorkspace({ status: 'loading' }, 'ws-1')).toBe(true)
  })
})
