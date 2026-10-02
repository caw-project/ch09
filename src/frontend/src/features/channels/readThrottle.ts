/**
 * A per-channel leading-and-trailing throttle for `mark_read`.
 *
 * The first read for a channel goes out at once and opens a window; reads asked
 * for inside it are held, only the latest kept, and sent when the window ends —
 * which opens the next window. A window with nothing held closes. So a channel
 * sends at most once per window, and a reader who stops at the newest message
 * always has that message acknowledged.
 *
 * **A window opens only on an emit.** `send` says whether it emitted; a refusal
 * (disconnected, already read, another workspace) counts nothing, so the next
 * request is tried at once rather than waiting out a window nothing opened.
 *
 * A plain timer object with no React in it, so the timing is a fake-timer test.
 */

export const READ_WINDOW_MS = 1000

export interface ReadThrottle {
  request(channelId: string, messageId: string): void
  /** Send a held read now and close that channel's window. */
  flush(channelId: string): void
  /** Clear every timer and drop every held read; later calls do nothing. */
  dispose(): void
}

interface Window {
  timer: ReturnType<typeof setTimeout>
  held: string | null
}

export function createReadThrottle(
  send: (channelId: string, messageId: string) => boolean,
  windowMs: number = READ_WINDOW_MS,
): ReadThrottle {
  const windows = new Map<string, Window>()
  let disposed = false

  function open(channelId: string): void {
    const entry: Window = {
      held: null,
      timer: setTimeout(() => {
        const { held } = entry
        entry.held = null
        windows.delete(channelId)
        if (disposed || held === null) return
        if (send(channelId, held)) open(channelId)
      }, windowMs),
    }
    windows.set(channelId, entry)
  }

  return {
    request(channelId, messageId) {
      if (disposed) return
      const entry = windows.get(channelId)
      if (entry) {
        entry.held = messageId
        return
      }
      if (send(channelId, messageId)) open(channelId)
    },

    flush(channelId) {
      if (disposed) return
      const entry = windows.get(channelId)
      if (!entry) return
      clearTimeout(entry.timer)
      windows.delete(channelId)
      if (entry.held !== null) send(channelId, entry.held)
    },

    dispose() {
      disposed = true
      for (const entry of windows.values()) clearTimeout(entry.timer)
      windows.clear()
    },
  }
}
