import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { setPageAttention } from '../../test/page'
import { usePageAttention } from './usePageAttention'

describe('usePageAttention', () => {
  it('is true when the page is visible and focused', () => {
    setPageAttention({ visible: true, focused: true })
    expect(renderHook(() => usePageAttention()).result.current).toBe(true)
  })

  it('is false when the page is hidden', () => {
    setPageAttention({ visible: false, focused: true })
    expect(renderHook(() => usePageAttention()).result.current).toBe(false)
  })

  it('is false when the page is visible but blurred', () => {
    setPageAttention({ visible: true, focused: false })
    expect(renderHook(() => usePageAttention()).result.current).toBe(false)
  })

  it('follows visibilitychange, focus and blur, one event each', () => {
    setPageAttention({ visible: false, focused: true })
    const { result } = renderHook(() => usePageAttention())
    expect(result.current).toBe(false)

    act(() => setPageAttention({ visible: true, focused: true })) // visibilitychange only
    expect(result.current).toBe(true)

    act(() => setPageAttention({ visible: true, focused: false })) // blur only
    expect(result.current).toBe(false)

    act(() => setPageAttention({ visible: true, focused: true })) // focus only
    expect(result.current).toBe(true)

    act(() => setPageAttention({ visible: false, focused: true })) // visibilitychange only
    expect(result.current).toBe(false)
  })
})
