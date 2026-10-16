/**
 * The clock preference, applied to the three formatters (issue gh-3, Req 7).
 *
 * Every instant is built from local-time parts, so it reads 13:05 on the wall
 * wherever the suite runs. `hourCycle` is what makes 12 or 24 hours hold in
 * every locale — `hour12: false` can print 24:05 after midnight in some ICU builds.
 */

import { describe, expect, it } from 'vitest'

import { dateAndTime, timeOfDay } from './time'

const AFTERNOON = new Date(2026, 9, 16, 13, 5).toISOString()
const MIDNIGHT = new Date(2026, 9, 17, 0, 5).toISOString()
const LOCALES = ['en-US', 'en-GB', 'de-DE']

describe('timeOfDay', () => {
  it.each(LOCALES)('follows the clock in %s', (locale) => {
    const twentyFour = timeOfDay(AFTERNOON, '24h', locale)
    const twelve = timeOfDay(AFTERNOON, '12h', locale)

    expect(twentyFour).toContain('13:05')
    expect(twentyFour).not.toMatch(/AM|PM/i)
    expect(twelve).not.toContain('13')
    expect(twelve).toContain('1:05')
  })

  it('writes 12-hour time as 01:05 PM in en-US', () => {
    expect(timeOfDay(AFTERNOON, '12h', 'en-US')).toMatch(/01:05\sPM/)
  })

  it('never prints 24:05 for just after midnight', () => {
    expect(timeOfDay(MIDNIGHT, '24h', 'en-US')).toContain('00:05')
    expect(timeOfDay(MIDNIGHT, '24h', 'en-US')).not.toContain('24:05')
  })

  it('is the browser’s own format when no clock is chosen', () => {
    expect(timeOfDay(AFTERNOON)).toBe(
      new Date(AFTERNOON).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    )
  })
})

describe('dateAndTime', () => {
  it.each(LOCALES)('follows the clock in %s', (locale) => {
    expect(dateAndTime(AFTERNOON, '24h', locale)).toContain('13:05')
    expect(dateAndTime(AFTERNOON, '12h', locale)).not.toContain('13')
    expect(dateAndTime(AFTERNOON, '12h', locale)).toContain('1:05')
  })

  it('is the browser’s own format when no clock is chosen', () => {
    expect(dateAndTime(AFTERNOON)).toBe(
      new Date(AFTERNOON).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }),
    )
  })
})
