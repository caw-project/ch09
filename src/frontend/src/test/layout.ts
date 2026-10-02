/**
 * Scroll geometry for jsdom, which does no layout: every scroll dimension reads
 * 0, so a list looks pinned to the bottom of nothing (0 − 0 − 0 is within any
 * threshold of the bottom).
 *
 * `giveLayout` stubs one element that already exists. `layoutEveryElement`
 * stubs every element, for a list that mounts *inside* the test — a remount
 * leaves no chance to stub the new node before its first measurement.
 */

import { onTestFinished, vi, type Mock } from 'vitest'

export type Layout = Record<'clientHeight' | 'scrollHeight' | 'scrollTop', number> & {
  /** `scrollTop` ignores writes — the list's own scroll-to-newest can't move it. */
  frozen?: boolean
}

/**
 * Give the element the geometry a browser would: a viewport inside a taller
 * content box, with a `scrollTop` that remembers what the component writes to
 * it. Calling it again redefines the properties (they are `configurable`).
 */
export function giveLayout(
  element: HTMLElement,
  { clientHeight, scrollHeight, scrollTop, frozen = false }: Layout,
) {
  let top = scrollTop
  Object.defineProperty(element, 'clientHeight', { configurable: true, get: () => clientHeight })
  Object.defineProperty(element, 'scrollHeight', { configurable: true, get: () => scrollHeight })
  Object.defineProperty(element, 'scrollTop', {
    configurable: true,
    get: () => top,
    set: (value: number) => {
      if (!frozen) top = value
    },
  })
}

/**
 * jsdom has no `Element.scrollIntoView`, so code that calls it throws. This
 * defines it on `HTMLElement.prototype` as a spy — `spy.mock.contexts` says
 * which element it was called on — and removes it when the test ends.
 */
export function stubScrollIntoView(): Mock {
  const spy = vi.fn()
  Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
    configurable: true,
    value: spy,
  })
  onTestFinished(() => {
    Reflect.deleteProperty(HTMLElement.prototype, 'scrollIntoView')
  })
  return spy
}

/**
 * The same getters on `HTMLElement.prototype`, so every element has them from
 * its first render. `scrollTop` is kept per element. Undone when the test ends;
 * the returned function undoes it sooner.
 */
export function layoutEveryElement(layout: Layout): () => void {
  const { clientHeight, scrollHeight, scrollTop, frozen = false } = layout
  const tops = new WeakMap<HTMLElement, number>()
  const proto = HTMLElement.prototype
  Object.defineProperty(proto, 'clientHeight', { configurable: true, get: () => clientHeight })
  Object.defineProperty(proto, 'scrollHeight', { configurable: true, get: () => scrollHeight })
  Object.defineProperty(proto, 'scrollTop', {
    configurable: true,
    get(this: HTMLElement) {
      return tops.get(this) ?? scrollTop
    },
    set(this: HTMLElement, value: number) {
      if (!frozen) tops.set(this, value)
    },
  })

  const restore = () => {
    Reflect.deleteProperty(proto, 'clientHeight')
    Reflect.deleteProperty(proto, 'scrollHeight')
    Reflect.deleteProperty(proto, 'scrollTop')
  }
  onTestFinished(restore)
  return restore
}
