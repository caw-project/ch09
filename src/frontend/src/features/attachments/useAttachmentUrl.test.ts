/**
 * Download-URL freshness (issue 4 R11, decision 36).
 *
 * A URL lives 900 s and goes stale at 780 s, but staleness only matters at three
 * moments: when a mount finds it stale, and when someone clicks. A mounted image
 * keeps its URL — the browser has already loaded it — so nothing refetches on a
 * focus, a reconnect or a re-render.
 *
 * Only `Date` is faked: TanStack reads staleness from it. `vi.waitFor` is NOT
 * clock-neutral here: with any fake timer installed it advances the fake clock
 * on each retry (about 50 ms), so the instant data lands is T0 plus a little.
 * The boundary tests therefore read the cache's own `dataUpdatedAt` after the
 * first fetch and set the clock to that `+ 779_999` / `+ 780_001`, and never
 * `waitFor` between `setSystemTime` and the mount. The boundaries are literals:
 * an imported constant that does not exist yet would make the arithmetic `NaN`.
 */

import { focusManager, onlineManager, type QueryClient } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { messaging, requests } from '../../test/api'
import { createTestQueryClient, renderHookWithProviders } from '../../test/render'
import { attachmentUrlKeys, freshAttachmentUrl, useAttachmentUrl } from './useAttachmentUrl'

const WORKSPACE = 'workspace-1'
const MESSAGE = 'message-1'
const ASSET = 'asset-1'
const T0 = new Date('2026-10-01T09:00:00Z').getTime()

const downloads = () => requests().filter((r) => r.url.pathname.endsWith('/download-url'))
const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

/** Each answer carries a URL numbered by how many the server has issued. */
function serveUrls() {
  let issued = 0
  messaging.get('/api/v1/messages/{message_id}/attachments/{asset_id}/download-url', () => {
    issued += 1
    return { url: `http://garage.test/get/${issued}`, expiresAt: '2026-10-01T09:15:00Z' }
  })
}

/** When the cache says the URL landed — the instant staleness is measured from. */
function landedAt(queryClient: QueryClient): number {
  const state = queryClient.getQueryCache().find({
    queryKey: attachmentUrlKeys.one(WORKSPACE, MESSAGE, ASSET),
  })?.state
  expect(state?.data).toBeDefined()
  return state!.dataUpdatedAt
}

function mount(queryClient: QueryClient) {
  return renderHookWithProviders(
    () => useAttachmentUrl('token', WORKSPACE, MESSAGE, ASSET),
    { queryClient },
  )
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(T0)
})

afterEach(() => {
  vi.useRealTimers()
  focusManager.setFocused(undefined)
  onlineManager.setOnline(true)
})

describe('useAttachmentUrl', () => {
  it('fetches the URL when first mounted', async () => {
    serveUrls()

    const { result } = mount(createTestQueryClient())

    await vi.waitFor(() => expect(result.current.url).toBe('http://garage.test/get/1'))
    expect(downloads()).toHaveLength(1)
  })

  it('uses the cached URL on a remount 1 ms before it goes stale, with no request', async () => {
    serveUrls()
    const queryClient = createTestQueryClient()
    const first = mount(queryClient)
    await vi.waitFor(() => expect(first.result.current.url).toBe('http://garage.test/get/1'))
    first.unmount()

    vi.setSystemTime(landedAt(queryClient) + 779_999)
    const again = mount(queryClient)
    // On the very first render: nothing to wait for.
    expect(again.result.current.url).toBe('http://garage.test/get/1')
    await sleep(100)

    expect(downloads()).toHaveLength(1)
    expect(again.result.current.url).toBe('http://garage.test/get/1')
  })

  it('requests a fresh URL first when a mount finds it stale, and shows none until it lands', async () => {
    serveUrls()
    const queryClient = createTestQueryClient()
    const first = mount(queryClient)
    await vi.waitFor(() => expect(first.result.current.url).toBe('http://garage.test/get/1'))
    first.unmount()

    vi.setSystemTime(landedAt(queryClient) + 780_001)
    const again = mount(queryClient)

    // The stale URL must not reach an <img>: it may have expired.
    expect(again.result.current.url).toBeNull()
    await vi.waitFor(() => expect(again.result.current.url).toBe('http://garage.test/get/2'))
    expect(downloads()).toHaveLength(2)
  })

  it('keeps a URL on screen past 780 s: a re-render, a focus and a reconnect fetch nothing', async () => {
    serveUrls()
    const queryClient = createTestQueryClient()
    const { result, rerender } = mount(queryClient)
    await vi.waitFor(() => expect(result.current.url).toBe('http://garage.test/get/1'))

    vi.setSystemTime(T0 + 781_000)
    rerender()
    focusManager.setFocused(false)
    focusManager.setFocused(true)
    onlineManager.setOnline(false)
    onlineManager.setOnline(true)
    // Anchored on the last thing that could have fetched: give it room to.
    await sleep(150)

    expect(downloads()).toHaveLength(1)
    expect(result.current.url).toBe('http://garage.test/get/1')
  })

  it('is keyed by workspace, message and asset', () => {
    expect(attachmentUrlKeys.one('w', 'm', 'a')).not.toEqual(attachmentUrlKeys.one('x', 'm', 'a'))
    expect(attachmentUrlKeys.one('w', 'm', 'a')).not.toEqual(attachmentUrlKeys.one('w', 'n', 'a'))
    expect(attachmentUrlKeys.one('w', 'm', 'a')).not.toEqual(attachmentUrlKeys.one('w', 'm', 'b'))
  })
})

describe('freshAttachmentUrl', () => {
  it('reuses a URL that is not stale and fetches one that is', async () => {
    serveUrls()
    const queryClient = createTestQueryClient()

    const first = await freshAttachmentUrl(queryClient, 'token', WORKSPACE, MESSAGE, ASSET)
    vi.setSystemTime(T0 + 1_000)
    const second = await freshAttachmentUrl(queryClient, 'token', WORKSPACE, MESSAGE, ASSET)

    expect(first).toBe('http://garage.test/get/1')
    expect(second).toBe(first)
    expect(downloads()).toHaveLength(1)

    vi.setSystemTime(T0 + 781_000)
    const third = await freshAttachmentUrl(queryClient, 'token', WORKSPACE, MESSAGE, ASSET)

    expect(third).toBe('http://garage.test/get/2')
    expect(downloads()).toHaveLength(2)
  })

  it('shares one cache with the hook, so a click after a mount costs no second request', async () => {
    serveUrls()
    const queryClient = createTestQueryClient()
    const { result } = mount(queryClient)
    await vi.waitFor(() => expect(result.current.url).toBe('http://garage.test/get/1'))

    const url = await freshAttachmentUrl(queryClient, 'token', WORKSPACE, MESSAGE, ASSET)

    expect(url).toBe('http://garage.test/get/1')
    expect(downloads()).toHaveLength(1)
  })
})
