/**
 * Whether the page is in front of the user: visible, and holding focus.
 *
 * jsdom reports `visibilityState === 'visible'` and `hasFocus() === false`, and
 * has no way to change either, so a test sets them here. Only what **changed**
 * fires an event, as in a browser: `visibilitychange` on `document` and
 * `focus` / `blur` on `window`.
 *
 * `visibilitychange` **bubbles**, as browsers fire it, so it reaches TanStack
 * Query's listener on `window` (`query-core/src/focusManager.ts`; jsdom makes the
 * window the document's parent). A non-bubbling event would never reach it and a
 * "refetch on return" test would pass or fail for the wrong reason.
 *
 * `setup.ts` calls `resetPageAttention()` after every test.
 */

import { vi, type MockInstance } from 'vitest'

interface Attention {
  visible: boolean
  focused: boolean
}

let current: Attention | null = null
let focusSpy: MockInstance<() => boolean> | null = null

export function setPageAttention({ visible, focused }: Attention): void {
  const before = current ?? {
    visible: document.visibilityState === 'visible',
    focused: document.hasFocus(),
  }
  current = { visible, focused }

  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    get: () => (visible ? 'visible' : 'hidden'),
  })
  focusSpy?.mockRestore()
  focusSpy = vi.spyOn(document, 'hasFocus').mockReturnValue(focused)

  if (before.visible !== visible) {
    document.dispatchEvent(new Event('visibilitychange', { bubbles: true }))
  }
  if (before.focused !== focused) {
    window.dispatchEvent(new Event(focused ? 'focus' : 'blur'))
  }
}

export function resetPageAttention(): void {
  // The own property shadows jsdom's prototype getter; removing it restores it.
  Reflect.deleteProperty(document, 'visibilityState')
  focusSpy?.mockRestore()
  focusSpy = null
  current = null
}
