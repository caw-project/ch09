/**
 * The two time formats, and what the clock preference does to them (issue gh-3 Req 7).
 *
 * Dates are built as local time, so the machine's time zone cannot move 13:05
 * to another hour. The format is pinned by what a user reads: the digits, and
 * whether "PM" is on the end.
 */

import { describe, expect, it } from 'vitest'

import { dateAndTime, timeOfDay } from './time'

const afternoon = new Date(2026, 9, 17, 13, 5).toISOString()
const justAfterMidnight = new Date(2026, 9, 17, 0, 5).toISOString()

describe('timeOfDay', () => {
  it('is the browser’s own format when the clock is automatic', () => {
    const expected = new Date(afternoon).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
    })

    expect(timeOfDay(afternoon, null)).toBe(expected)
  })

  it('shows 13:05 on a 24-hour clock', () => {
    expect(timeOfDay(afternoon, '24h')).toBe('13:05')
  })

  it('shows no 13 on a 12-hour clock', () => {
    const shown = timeOfDay(afternoon, '12h')

    expect(shown).toMatch(/^0?1:05\s?PM$/i)
    expect(shown).not.toContain('13')
  })

  it('shows midnight as 00:05, never 24:05, on a 24-hour clock', () => {
    // `hour12: false` renders 24:05 in some locales; `hourCycle: 'h23'` does not.
    expect(timeOfDay(justAfterMidnight, '24h')).toBe('00:05')
  })

  it('shows midnight as 12:05 AM on a 12-hour clock', () => {
    expect(timeOfDay(justAfterMidnight, '12h')).toMatch(/^12:05\s?AM$/i)
  })
})

describe('dateAndTime', () => {
  it('is the browser’s own format when the clock is automatic', () => {
    const expected = new Date(afternoon).toLocaleString([], {
      dateStyle: 'medium',
      timeStyle: 'short',
    })

    expect(dateAndTime(afternoon, null)).toBe(expected)
  })

  it('follows the 24-hour clock', () => {
    const shown = dateAndTime(afternoon, '24h')

    expect(shown).toContain('13:05')
    expect(shown).not.toMatch(/PM/i)
  })

  it('follows the 12-hour clock', () => {
    const shown = dateAndTime(afternoon, '12h')

    expect(shown).toMatch(/1:05\s?PM/i)
    expect(shown).not.toContain('13')
  })

  it('keeps the date in both', () => {
    expect(dateAndTime(afternoon, '24h')).toContain('Oct')
    expect(dateAndTime(afternoon, '12h')).toContain('Oct')
  })
})
