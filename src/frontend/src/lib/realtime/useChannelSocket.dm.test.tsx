/**
 * `channel_added` — a direct message appearing in the sidebar live (issue 5, R10).
 *
 * The server sends `{ channelId }` to both members' personal rooms when a DM gets
 * its first message, and the SPA answers by refetching the channel list. The
 * three orders that matter are the issue's *Timing*: an event with a cached list,
 * an event while a poll is already in flight (both ways round), and an event
 * while the *first* load is in flight, which TanStack reuses rather than cancels.
 *
 * `useChannels` is mounted beside the socket, as `ChatLayout` does: `invalidate`
 * refetches only a query somebody is observing.
 */

import { act } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { channelKeys, useChannels } from '../../features/channels/useChannels'
import { messaging, requests, resetRequests } from '../../test/api'
import { aChannel } from '../../test/factories'
import { createTestQueryClient, renderHookWithProviders } from '../../test/render'
import { latestSocket } from '../../test/socket'
import type { ChannelPage } from '../api/messaging'
import { useChannelSocket } from './useChannelSocket'

const WORKSPACE = 'workspace-1'
const ADA = 'user-ada'
const GRACE = 'user-grace'

const general = aChannel({ name: 'general' })
const dm = aChannel({ kind: 'dm', name: `dm:${ADA}:${GRACE}`, dmPartnerId: GRACE, unreadCount: 1 })

const without: ChannelPage = { items: [general], nextCursor: null }
const withDm: ChannelPage = { items: [general, dm], nextCursor: null }

const listRequests = () =>
  requests().filter((r) => r.method === 'GET' && r.url.pathname === '/api/v1/channels')

/** A promise a test settles when it chooses — holds a stubbed reply in flight. */
function gate() {
  let open!: () => void
  const promise = new Promise<void>((resolve) => {
    open = resolve
  })
  return { promise, open: () => act(async () => open()) }
}

function mount() {
  const queryClient = createTestQueryClient()
  renderHookWithProviders(
    () => {
      useChannels('token', WORKSPACE)
      return useChannelSocket('token', WORKSPACE, null, ADA)
    },
    { queryClient },
  )
  const cached = () => queryClient.getQueryData<ChannelPage>(channelKeys.list(WORKSPACE))
  const hasDm = () => cached()?.items.some((c) => c.id === dm.id) ?? false
  return { queryClient, socket: latestSocket(), cached, hasDm }
}

describe('useChannelSocket — channel_added', () => {
  it('refetches the channel list, and the DM lands in the cache', async () => {
    let page = without
    messaging.get('/api/v1/channels', () => page)
    const { socket, cached, hasDm } = mount()
    await vi.waitFor(() => expect(cached()).toBeDefined())
    expect(hasDm()).toBe(false)
    resetRequests()
    page = withDm

    act(() => socket.serverEmit('channel_added', { channelId: dm.id }))

    await vi.waitFor(() => expect(hasDm()).toBe(true))
    expect(listRequests()).toHaveLength(1)
  })

  describe('while a poll is in flight', () => {
    /**
     * The poll started before the message committed (`without`); the event starts a second
     * fetch (`withDm`). The old one is held, then the new, in the order the test names.
     */
    async function pollThenEvent() {
      const old = gate()
      const next = gate()
      let calls = 0
      messaging.get('/api/v1/channels', async () => {
        const n = calls++
        if (n === 0) return without
        if (n === 1) {
          await old.promise
          return without
        }
        await next.promise
        return withDm
      })
      const mounted = mount()
      await vi.waitFor(() => expect(mounted.cached()).toBeDefined())

      act(() => {
        void mounted.queryClient.refetchQueries({ queryKey: channelKeys.list(WORKSPACE) })
      })
      await vi.waitFor(() => expect(listRequests()).toHaveLength(2))
      act(() => mounted.socket.serverEmit('channel_added', { channelId: dm.id }))
      // A new request, not the poll's own: the event must not join a fetch that predates it.
      await vi.waitFor(() => expect(listRequests()).toHaveLength(3))
      return { ...mounted, old, next }
    }

    it('keeps the DM when the old fetch answers first', async () => {
      const { old, next, hasDm } = await pollThenEvent()

      await old.open()
      await next.open()

      await vi.waitFor(() => expect(hasDm()).toBe(true))
    })

    it('keeps the DM when the new fetch answers first', async () => {
      const { old, next, hasDm } = await pollThenEvent()

      await next.open()
      await vi.waitFor(() => expect(hasDm()).toBe(true))
      await old.open()

      // The poll's stale answer, landing late, must not take it away again.
      await act(async () => {})
      expect(hasDm()).toBe(true)
    })
  })

  it('fetches again when it arrives during the first load, which may predate the message', async () => {
    const first = gate()
    let calls = 0
    messaging.get('/api/v1/channels', async () => {
      if (calls++ === 0) {
        await first.promise
        return without
      }
      return withDm
    })
    const { socket, cached, hasDm } = mount()
    await vi.waitFor(() => expect(listRequests()).toHaveLength(1))
    expect(cached()).toBeUndefined()

    act(() => socket.serverEmit('channel_added', { channelId: dm.id }))
    await first.open()

    // The first load answered without the DM; a second GET is what brings it in.
    await vi.waitFor(() => expect(listRequests()).toHaveLength(2))
    await vi.waitFor(() => expect(hasDm()).toBe(true))
  })
})
