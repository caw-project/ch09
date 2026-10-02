/**
 * The jump's step rule, pure: given what history holds right now, what the jump
 * does next. Precedence is failed → wait → found → give-up at the cap → fetch →
 * give-up when exhausted.
 *
 * The plan's constants are written as literals here (10 pages), not imported:
 * an import that doesn't exist yet is `undefined`, and a boundary computed from
 * it would be `NaN`.
 */

import { describe, expect, it } from 'vitest'

import { aMessage, messageIdAt } from '../../test/factories'
import { nextJumpStep } from './jump'

const TARGET = messageIdAt(5)
const loaded = [aMessage({ id: messageIdAt(6) }), aMessage({ id: messageIdAt(7) })]
const withTarget = [aMessage({ id: TARGET }), ...loaded]

const base = {
  target: TARGET,
  messages: loaded,
  loadedPages: 3,
  hasNextPage: true,
  fetching: false,
  failed: false,
}

describe('nextJumpStep', () => {
  it('fetches while under the cap and more history exists', () => {
    expect(nextJumpStep({ ...base, loadedPages: 9 })).toBe('fetch')
    // The positive's neighbour: nothing more to fetch is not a fetch.
    expect(nextJumpStep({ ...base, loadedPages: 9, hasNextPage: false })).not.toBe('fetch')
  })

  it('gives up at ten loaded pages without the target', () => {
    expect(nextJumpStep({ ...base, loadedPages: 10 })).toBe('give-up')
    expect(nextJumpStep({ ...base, loadedPages: 11 })).toBe('give-up')
    expect(nextJumpStep({ ...base, loadedPages: 9 })).toBe('fetch')
  })

  it('finds a target on the tenth page', () => {
    expect(nextJumpStep({ ...base, messages: withTarget, loadedPages: 10 })).toBe('found')
  })

  it('waits while history is fetching, even with the target loaded', () => {
    expect(nextJumpStep({ ...base, messages: withTarget, fetching: true })).toBe('wait')
    expect(nextJumpStep({ ...base, messages: withTarget, fetching: false })).toBe('found')
    // And waiting beats fetching and giving up as well.
    expect(nextJumpStep({ ...base, fetching: true })).toBe('wait')
    expect(nextJumpStep({ ...base, loadedPages: 10, fetching: true })).toBe('wait')
  })

  it('fails on a failed fetch before anything else', () => {
    expect(nextJumpStep({ ...base, failed: true, fetching: true })).toBe('failed')
    expect(nextJumpStep({ ...base, failed: true, messages: withTarget })).toBe('failed')
    expect(nextJumpStep({ ...base, failed: false, messages: withTarget })).toBe('found')
  })

  it('gives up when history is exhausted under the cap', () => {
    expect(nextJumpStep({ ...base, hasNextPage: false, loadedPages: 3 })).toBe('give-up')
    expect(nextJumpStep({ ...base, hasNextPage: true, loadedPages: 3 })).toBe('fetch')
  })

  it('finds a tombstone', () => {
    const tombstone = aMessage({ id: TARGET, body: '', deletedAt: '2026-09-15T10:00:00Z' })

    expect(nextJumpStep({ ...base, messages: [tombstone, ...loaded] })).toBe('found')
  })
})
