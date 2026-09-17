import { describe, expect, it } from 'vitest'

import { baseUrlFrom } from './config'

describe('baseUrlFrom', () => {
  it('falls back to the dev address when the variable was never set', () => {
    expect(baseUrlFrom(undefined, 'http://localhost:8001')).toBe('http://localhost:8001')
  })

  it('keeps an empty value, so every call is relative to the page origin', () => {
    expect(baseUrlFrom('', 'http://localhost:8001')).toBe('')
  })

  it('uses a value that was set', () => {
    expect(baseUrlFrom('http://localhost:8011', 'http://localhost:8001')).toBe(
      'http://localhost:8011',
    )
  })

  it('drops a trailing slash, which would otherwise double up before /api', () => {
    expect(baseUrlFrom('http://auth.example/', 'http://localhost:8001')).toBe('http://auth.example')
  })
})
