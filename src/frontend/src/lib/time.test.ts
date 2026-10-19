/**
 * The clock preference, as the formatters apply it (issue gh-3, Req 7).
 *
 * `clock` overrides the locale's own habit in both directions: a 24-hour choice in
 * a 12-hour locale, and a 12-hour one in a 24-hour locale. Absent means the
 * browser's locale, as every time was formatted before the preference existed.
 * 15:05 local is built from its parts, so it is 15:05 in any time zone.
 */

import { describe, expect, it } from 'vitest'

import { formatDateTime, formatTime } from './time'

const AT = new Date(2026, 9, 19, 15, 5).toISOString()
const THREE_FIVE_PM = /3:05\s?pm/i

describe('formatTime', () => {
  it('shows 24-hour time in a locale that defaults to 12-hour', () => {
    const shown = formatTime(AT, '24h', 'en-US')

    expect(shown).toBe('15:05')
    expect(shown).not.toMatch(/PM/i)
  })

  it('shows 12-hour time in a locale that defaults to 24-hour', () => {
    expect(formatTime(AT, '12h', 'en-GB')).toMatch(THREE_FIVE_PM)
  })

  it('leaves the locale alone when no clock is chosen', () => {
    expect(formatTime(AT, undefined, 'en-GB')).toBe('15:05')
    expect(formatTime(AT, undefined, 'en-US')).toMatch(/PM/)
  })

  it('takes no locale to mean the browser’s own', () => {
    expect(formatTime(AT)).toBe(new Date(AT).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }))
    expect(formatTime(AT, '24h')).toContain('15:05')
  })
})

describe('formatDateTime', () => {
  it('shows 24-hour time in a locale that defaults to 12-hour', () => {
    const shown = formatDateTime(AT, '24h', 'en-US')

    expect(shown).toContain('15:05')
    expect(shown).not.toMatch(/PM/i)
  })

  it('shows 12-hour time in a locale that defaults to 24-hour', () => {
    expect(formatDateTime(AT, '12h', 'en-GB')).toMatch(THREE_FIVE_PM)
  })

  it('leaves the locale alone when no clock is chosen', () => {
    expect(formatDateTime(AT, undefined, 'en-GB')).toContain('15:05')
    expect(formatDateTime(AT, undefined, 'en-US')).toMatch(/PM/)
  })

  it('keeps the medium date beside the time', () => {
    expect(formatDateTime(AT, '24h', 'en-US')).toContain('Oct 19, 2026')
  })

  it('takes no locale to mean the browser’s own', () => {
    expect(formatDateTime(AT)).toBe(
      new Date(AT).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }),
    )
  })
})
