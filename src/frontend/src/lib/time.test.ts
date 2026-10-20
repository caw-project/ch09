/**
 * The two time formats and the clock preference that picks between them
 * (issue gh-3, Req 7).
 *
 * Dates are built from **local** parts, so the test holds in any time zone. The
 * 12/24-hour results are asserted on the digits, not the whole string, because the
 * suite runs in one ICU locale and the point is the hour cycle, not that locale's
 * punctuation. "Automatic" is asserted against the browser's own formatter, which
 * is what it is defined to be.
 */

import { describe, expect, it } from 'vitest'

import { dateAndTime, timeOfDay } from './time'

const afternoon = new Date(2026, 8, 15, 15, 7).toISOString()
const morning = new Date(2026, 8, 15, 9, 5).toISOString()

describe.each([
  ['timeOfDay', timeOfDay],
  ['dateAndTime', dateAndTime],
])('%s', (_name, format) => {
  it('Automatic follows the browser locale', () => {
    const expected =
      format === timeOfDay
        ? new Date(afternoon).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        : new Date(afternoon).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })

    expect(format(afternoon, null)).toBe(expected)
    expect(format(afternoon, undefined)).toBe(expected)
  })

  it('24-hour shows 15:07 for a local 15:07', () => {
    expect(format(afternoon, '24h')).toMatch(/\b15:07\b/)
  })

  it('12-hour shows 3:07 and not 15:07', () => {
    const shown = format(afternoon, '12h')

    expect(shown).toMatch(/\b0?3:07\b/)
    expect(shown).not.toMatch(/15:07/)
  })

  it('a morning time reads 9:05 either way', () => {
    expect(format(morning, '24h')).toMatch(/\b0?9:05\b/)
    expect(format(morning, '12h')).toMatch(/\b0?9:05\b/)
  })

  it('the two settings differ for the same instant', () => {
    expect(format(afternoon, '12h')).not.toBe(format(afternoon, '24h'))
  })
})

describe('dateAndTime', () => {
  it('keeps the date beside the time', () => {
    expect(dateAndTime(afternoon, '24h')).toMatch(/2026/)
    expect(dateAndTime(afternoon, '12h')).toMatch(/2026/)
  })
})
