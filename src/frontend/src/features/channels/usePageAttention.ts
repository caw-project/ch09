/**
 * Whether the user could be looking at the page: the tab is visible and the
 * window has focus. Either alone is not enough — a visible tab behind another
 * window is not being read.
 */

import { useEffect, useState } from 'react'

function attending(): boolean {
  return document.visibilityState === 'visible' && document.hasFocus()
}

export function usePageAttention(): boolean {
  const [value, setValue] = useState(attending)

  useEffect(() => {
    const update = () => setValue(attending())
    document.addEventListener('visibilitychange', update)
    window.addEventListener('focus', update)
    window.addEventListener('blur', update)
    update()
    return () => {
      document.removeEventListener('visibilitychange', update)
      window.removeEventListener('focus', update)
      window.removeEventListener('blur', update)
    }
  }, [])

  return value
}
