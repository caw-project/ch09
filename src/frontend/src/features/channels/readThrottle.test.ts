import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { messageIdAt } from '../../test/factories'
import { createReadThrottle } from './readThrottle'

const A = 'channel-a'
const B = 'channel-b'
const m = messageIdAt

/**
 * The window is the literal 1000 throughout, never `READ_WINDOW_MS`: before the
 * module exists that import is `undefined`, and a clock advanced by it moves by
 * `NaN`, which lets a "nothing is sent" half pass for the wrong reason.
 */
function setUp(emits = true) {
  const sent: Array<[string, string]> = []
  const send = vi.fn((channelId: string, messageId: string) => {
    sent.push([channelId, messageId])
    return emits
  })
  return { sent, send, throttle: createReadThrottle(send, 1000) }
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
})

afterEach(() => {
  vi.useRealTimers()
})

describe('createReadThrottle', () => {
  it('sends the first read at once', () => {
    const { sent, throttle } = setUp()

    throttle.request(A, m(2))

    expect(sent).toEqual([[A, m(2)]])
  })

  it('holds reads inside the window and sends the latest at its end', () => {
    const { sent, throttle } = setUp()
    throttle.request(A, m(2))

    vi.advanceTimersByTime(500)
    throttle.request(A, m(3))
    throttle.request(A, m(4))
    vi.advanceTimersByTime(499)
    expect(sent).toEqual([[A, m(2)]])

    vi.advanceTimersByTime(1)
    expect(sent).toEqual([
      [A, m(2)],
      [A, m(4)],
    ])
  })

  it('opens a new window from each send', () => {
    const { sent, throttle } = setUp()
    throttle.request(A, m(2))
    vi.advanceTimersByTime(500)
    throttle.request(A, m(4))
    vi.advanceTimersByTime(500) // t=1000: m4 sent, a new window opens
    expect(sent).toHaveLength(2)

    vi.advanceTimersByTime(400) // t=1400
    throttle.request(A, m(5))
    vi.advanceTimersByTime(599) // t=1999
    expect(sent).toHaveLength(2)

    vi.advanceTimersByTime(1) // t=2000
    expect(sent.at(-1)).toEqual([A, m(5)])
    expect(sent).toHaveLength(3)
  })

  it('closes the window when nothing new was asked', () => {
    const { sent, throttle } = setUp()
    throttle.request(A, m(2))
    vi.advanceTimersByTime(500)
    throttle.request(A, m(4))
    vi.advanceTimersByTime(500) // t=1000
    vi.advanceTimersByTime(400)
    throttle.request(A, m(5))
    vi.advanceTimersByTime(600) // t=2000: m5 sent, a new window opens
    expect(sent).toHaveLength(3)

    vi.advanceTimersByTime(1000) // t=3000: nothing held, the window closes
    expect(sent).toHaveLength(3)

    vi.advanceTimersByTime(100) // t=3100
    throttle.request(A, m(6))
    expect(sent.at(-1)).toEqual([A, m(6)])
    expect(sent).toHaveLength(4)
  })

  it('throttles each channel on its own', () => {
    const { sent, throttle } = setUp()

    throttle.request(A, m(1))
    throttle.request(B, m(2))
    expect(sent).toEqual([
      [A, m(1)],
      [B, m(2)],
    ])

    throttle.request(A, m(3))
    throttle.request(B, m(4))
    expect(sent).toHaveLength(2)

    vi.advanceTimersByTime(1000)
    expect(sent.slice(2)).toEqual([
      [A, m(3)],
      [B, m(4)],
    ])
  })

  it('flushes a held read at once, and closes that channel’s window', () => {
    const { sent, throttle } = setUp()
    throttle.request(A, m(1))
    throttle.request(A, m(2))
    expect(sent).toHaveLength(1)

    throttle.flush(A)
    expect(sent).toEqual([
      [A, m(1)],
      [A, m(2)],
    ])

    // The window is closed, so the next request is sent at once ...
    throttle.request(A, m(3))
    expect(sent.at(-1)).toEqual([A, m(3)])
    expect(sent).toHaveLength(3)
    // ... and the timer the flush cleared does not send anything later.
    vi.advanceTimersByTime(500)
    expect(sent).toHaveLength(3)
  })

  it('flushes nothing when nothing is held', () => {
    const { sent, throttle } = setUp()
    throttle.request(A, m(1))

    throttle.flush(A)
    throttle.flush(B)
    vi.advanceTimersByTime(2000)

    expect(sent).toEqual([[A, m(1)]])
  })

  it('drops a held read on dispose, and ignores later calls', () => {
    const { sent, throttle } = setUp()
    throttle.request(A, m(1))
    throttle.request(A, m(2))

    throttle.dispose()
    vi.advanceTimersByTime(2000)
    throttle.request(A, m(3))
    throttle.flush(A)
    vi.advanceTimersByTime(2000)

    expect(sent).toEqual([[A, m(1)]])
  })

  it('opens no window for a send that emits nothing', () => {
    const results = [false, true]
    const sent: string[] = []
    const throttle = createReadThrottle((_channelId: string, messageId: string) => {
      sent.push(messageId)
      return results.shift() ?? true
    }, 1000)

    throttle.request(A, m(1)) // emitted nothing
    throttle.request(A, m(2)) // so no window is open: tried at once, and emits
    expect(sent).toEqual([m(1), m(2)])

    throttle.request(A, m(3)) // this one is inside the window the emit opened
    expect(sent).toHaveLength(2)
    vi.advanceTimersByTime(1000)
    expect(sent).toEqual([m(1), m(2), m(3)])
  })
})
