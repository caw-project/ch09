/**
 * Which thread is open, kept in the URL as `?thread=<rootId>`.
 *
 * The URL, not Zustand: a thread is something to link to, reload and go Back
 * from, and the panel it opens is a fact about the address rather than about the
 * client. **Opening pushes**, so Back steps from thread B to thread A and then
 * to no thread; **closing replaces** and deletes only `thread`, so Back does not
 * reopen what was just closed and any other param (`?message=`) survives.
 */

import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'

export function useThreadParam() {
  const [params, setParams] = useSearchParams()
  const threadId = params.get('thread')

  const openThread = useCallback(
    (rootId: string) =>
      setParams((current) => {
        const next = new URLSearchParams(current)
        next.set('thread', rootId)
        return next
      }),
    [setParams],
  )

  const closeThread = useCallback(
    () =>
      setParams(
        (current) => {
          const next = new URLSearchParams(current)
          next.delete('thread')
          return next
        },
        { replace: true },
      ),
    [setParams],
  )

  return { threadId, openThread, closeThread }
}
