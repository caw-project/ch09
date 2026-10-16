/**
 * The path to come back to after signing in (issue gh-3, Req 8).
 *
 * It is a second short-lived `sessionStorage` key beside the PKCE verifier, and
 * it is an open-redirect surface: whatever is stored is navigated to after
 * sign-in, so anything that is not a plain path on this origin is dropped.
 */

import { afterEach, describe, expect, it } from 'vitest'

import { returnPath } from './storage'

const KEY = 'collabhub.returnTo'

afterEach(() => {
  window.sessionStorage.clear()
})

describe('returnPath', () => {
  it('is taken once', () => {
    returnPath.write('/settings')
    expect(window.sessionStorage.getItem(KEY)).toBe('/settings')

    expect(returnPath.take()).toBe('/settings')
    expect(returnPath.take()).toBeNull()
    expect(window.sessionStorage.getItem(KEY)).toBeNull()
  })

  it('forgets what it held when written null or undefined', () => {
    returnPath.write('/settings')
    returnPath.write(null)
    expect(returnPath.take()).toBeNull()

    returnPath.write('/settings')
    returnPath.write(undefined)
    expect(returnPath.take()).toBeNull()
  })

  it.each([
    '//evil.test',
    'https://evil.test',
    '/\\evil',
    '/sign-in',
    '/auth/callback?code=x',
    'settings',
    '',
  ])('keeps nothing for %j', (path) => {
    returnPath.write(path)

    expect(returnPath.take()).toBeNull()
  })

  it('keeps a channel link with its query', () => {
    returnPath.write('/c/abc?message=m')

    expect(returnPath.take()).toBe('/c/abc?message=m')
  })

  it('drops a bad value written straight to storage, on the way out', () => {
    window.sessionStorage.setItem(KEY, '//evil.test')

    expect(returnPath.take()).toBeNull()
    expect(window.sessionStorage.getItem(KEY)).toBeNull()
  })
})
