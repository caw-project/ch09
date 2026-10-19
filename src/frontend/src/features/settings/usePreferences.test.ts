/**
 * The clock preference's cache: saving it, failing to, and fetches in flight
 * (issue gh-3, Req 7; plan Decisions 28, 30 and 42).
 *
 * Auth is stubbed at the network edge with a stateful fake: `stored` is what the
 * server holds, a PATCH stub changes it on success, and a GET answers it. So "ends
 * on what the server holds" is a thing the test can read, not just a cache value
 * the code put there itself. A held reply is how a request stays in flight.
 *
 * Every wait is on the last effect, not the first: a PATCH counted after the held
 * one was released, a cache read after a macrotask in which a wrong build would
 * already have written. Literal keys (`['preferences']`) so a wrong export name
 * fails a test and does not hide it.
 */

import type { QueryClient } from '@tanstack/react-query'
import { act } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Preferences } from '../../lib/auth/api'
import { auth, Refusal, requests } from '../../test/api'
import { createTestQueryClient, renderHookWithProviders } from '../../test/render'
import { useClock, usePreferences, useUpdateClock } from './usePreferences'

const TOKEN = 'token'
const PREFS = ['preferences']
const URL_PATH = '/api/v1/users/me/preferences'

const patches = () => requests().filter((r) => r.method === 'PATCH' && r.url.pathname === URL_PATH)
const gets = () => requests().filter((r) => r.method === 'GET' && r.url.pathname === URL_PATH)
const pause = () => act(() => new Promise<void>((resolve) => setTimeout(resolve, 25)))
const cached = (queryClient: QueryClient) => queryClient.getQueryData<Preferences>(PREFS)

function deferred() {
  let resolve!: () => void
  const promise = new Promise<void>((r) => {
    resolve = r
  })
  return { promise, release: () => act(async () => resolve()) }
}

/** What the server holds, after a PATCH that succeeded. */
function applied(stored: Preferences, patch: { clock?: '12h' | '24h' | null }): Preferences {
  const next = { ...stored }
  if (patch.clock === null) delete next.clock
  else if (patch.clock) next.clock = patch.clock
  return next
}

function mount() {
  const queryClient = createTestQueryClient()
  const view = renderHookWithProviders(
    () => ({
      prefs: usePreferences(TOKEN),
      update: useUpdateClock(TOKEN),
      clock: useClock(),
    }),
    { queryClient },
  )
  const choose = (value: '12h' | '24h' | null) =>
    act(() => {
      view.result.current.update.mutate(value)
    })
  return { ...view, choose }
}

async function loaded(queryClient: QueryClient, expected: Preferences) {
  await vi.waitFor(() => expect(cached(queryClient)).toEqual(expected))
}

describe('a failed save', () => {
  it('is reverted only if nothing newer was chosen — a newer choice stays', async () => {
    let stored: Preferences = {}
    const firstSave = deferred()
    const secondSave = deferred()
    auth.preferencesBy(() => ({ ...stored }))
    auth.updatePreferencesBy(async (call, body) => {
      if (call === 1) {
        await firstSave.promise
        return new Refusal(500)
      }
      await secondSave.promise
      stored = applied(stored, body)
      return { ...stored }
    })
    const h = mount()
    await loaded(h.queryClient, {})

    h.choose('24h')
    await vi.waitFor(() => expect(patches()).toHaveLength(1))
    expect(cached(h.queryClient)).toEqual({ clock: '24h' })
    h.choose('12h')
    await vi.waitFor(() => expect(cached(h.queryClient)).toEqual({ clock: '12h' }))

    // 24h fails while 12h is already on screen: putting {} back would undo 12h.
    await firstSave.release()
    await vi.waitFor(() => expect(patches()).toHaveLength(2))
    expect(patches()[1].body).toEqual({ clock: '12h' })
    expect(cached(h.queryClient)).toEqual({ clock: '12h' })

    await secondSave.release()
    await vi.waitFor(() => expect(h.result.current.clock).toBe('12h'))
    expect(stored).toEqual({ clock: '12h' })
  })

  it('goes back to the last saved choice when it was the newest, and shows the error', async () => {
    let stored: Preferences = { clock: '12h' }
    const secondSave = deferred()
    const settlingRead = deferred()
    auth.preferencesBy(async (call) => {
      // Call 1 is the mount and call 2 the read after the first save. Call 3 is the read
      // after the failure: held, so the revert is seen on its own and not as the
      // server's answer landing.
      if (call === 3) await settlingRead.promise
      return { ...stored }
    })
    auth.updatePreferencesBy(async (call, body) => {
      if (call === 1) {
        stored = applied(stored, body)
        return { ...stored }
      }
      await secondSave.promise
      return new Refusal(500, { title: 'Internal error', detail: 'Could not save.' })
    })
    const h = mount()
    await loaded(h.queryClient, { clock: '12h' })

    h.choose('24h')
    await vi.waitFor(() => expect(h.result.current.update.isSuccess).toBe(true))
    expect(cached(h.queryClient)).toEqual({ clock: '24h' })

    h.choose(null)
    await vi.waitFor(() => expect(cached(h.queryClient)).toEqual({}))
    await secondSave.release()
    await vi.waitFor(() => expect(h.result.current.update.isError).toBe(true))

    expect(h.result.current.update.error?.message).toBe('Could not save.')
    expect(cached(h.queryClient)).toEqual({ clock: '24h' })
    expect(h.result.current.clock).toBe('24h')
    await settlingRead.release()
  })

  it('two failed choices end on what the server holds, not on a choice that was never saved', async () => {
    const stored: Preferences = {}
    const firstSave = deferred()
    auth.preferencesBy(() => ({ ...stored }))
    auth.updatePreferencesBy(async (call) => {
      if (call === 1) await firstSave.promise
      return new Refusal(500)
    })
    const h = mount()
    await loaded(h.queryClient, {})

    h.choose('24h')
    await vi.waitFor(() => expect(patches()).toHaveLength(1))
    h.choose('12h')
    await vi.waitFor(() => expect(cached(h.queryClient)).toEqual({ clock: '12h' }))
    await firstSave.release()

    // 12h's own failure puts back 24h, which was never saved; the read that follows
    // the last settled save is what puts the server's {} back.
    await vi.waitFor(() => expect(patches()).toHaveLength(2))
    await vi.waitFor(() => expect(cached(h.queryClient)).toEqual({}))
    await pause()
    expect(cached(h.queryClient)).toEqual({})
    expect(h.result.current.clock).toBeUndefined()
    expect(gets().length).toBeGreaterThanOrEqual(2)
  })
})

describe('a save and the reads around it', () => {
  it('is not undone by a read in flight when the choice is made', async () => {
    let stored: Preferences = {}
    const slowRead = deferred()
    const save = deferred()
    auth.preferencesBy(async (call) => {
      if (call === 2) {
        await slowRead.promise
        return {} // what the server held before the choice
      }
      return { ...stored }
    })
    auth.updatePreferencesBy(async (_call, body) => {
      await save.promise
      stored = applied(stored, body)
      return { ...stored }
    })
    const h = mount()
    await loaded(h.queryClient, {})
    act(() => {
      void h.queryClient.refetchQueries({ queryKey: PREFS })
    })
    await vi.waitFor(() => expect(gets()).toHaveLength(2))

    h.choose('24h')
    await vi.waitFor(() => expect(patches()).toHaveLength(1))
    await slowRead.release()
    await pause()

    // The save is still in flight, and the read that began before it has answered {}.
    expect(patches()).toHaveLength(1)
    expect(cached(h.queryClient)).toEqual({ clock: '24h' })

    await save.release()
    await vi.waitFor(() => expect(h.result.current.update.isSuccess).toBe(true))
    await vi.waitFor(() => expect(cached(h.queryClient)).toEqual({ clock: '24h' }))
  })

  it('is followed by a read, so a read started mid-save cannot leave the old choice', async () => {
    let stored: Preferences = {}
    const save = deferred()
    auth.preferencesBy(() => ({ ...stored }))
    auth.updatePreferencesBy(async (_call, body) => {
      await save.promise
      stored = applied(stored, body)
      return { ...stored }
    })
    const h = mount()
    await loaded(h.queryClient, {})

    h.choose('24h')
    await vi.waitFor(() => expect(patches()).toHaveLength(1))
    // A read starts while the save is in flight and the server still says {}.
    act(() => {
      void h.queryClient.refetchQueries({ queryKey: PREFS })
    })
    await vi.waitFor(() => expect(gets()).toHaveLength(2))
    await vi.waitFor(() => expect(cached(h.queryClient)).toEqual({}))

    await save.release()

    // The read after the save is what puts the server's value on screen.
    await vi.waitFor(() => expect(gets()).toHaveLength(3))
    await vi.waitFor(() => expect(cached(h.queryClient)).toEqual({ clock: '24h' }))
    expect(h.result.current.clock).toBe('24h')
  })

  it('does not send the second choice until the first has settled', async () => {
    let stored: Preferences = {}
    const firstSave = deferred()
    auth.preferencesBy(() => ({ ...stored }))
    auth.updatePreferencesBy(async (call, body) => {
      if (call === 1) await firstSave.promise
      stored = applied(stored, body)
      return { ...stored }
    })
    const h = mount()
    await loaded(h.queryClient, {})

    h.choose('24h')
    await vi.waitFor(() => expect(patches()).toHaveLength(1))
    h.choose('12h')
    await vi.waitFor(() => expect(cached(h.queryClient)).toEqual({ clock: '12h' }))
    await pause()
    expect(patches()).toHaveLength(1)

    await firstSave.release()
    await vi.waitFor(() => expect(patches()).toHaveLength(2))
    expect(patches().map((r) => r.body)).toEqual([{ clock: '24h' }, { clock: '12h' }])
    await vi.waitFor(() => expect(stored).toEqual({ clock: '12h' }))
  })

  it('sends null for Automatic', async () => {
    let stored: Preferences = { clock: '24h' }
    auth.preferencesBy(() => ({ ...stored }))
    auth.updatePreferencesBy(async (_call, body) => {
      stored = applied(stored, body)
      return { ...stored }
    })
    const h = mount()
    await loaded(h.queryClient, { clock: '24h' })

    h.choose(null)

    await vi.waitFor(() => expect(patches()).toHaveLength(1))
    expect(patches()[0].body).toEqual({ clock: null })
    await vi.waitFor(() => expect(h.result.current.clock).toBeUndefined())
  })
})

describe('reading the clock', () => {
  it('useClock reads the cache and sends no request of its own', async () => {
    auth.preferences({})
    const queryClient = createTestQueryClient()
    queryClient.setQueryData(PREFS, { clock: '24h' })

    const { result } = renderHookWithProviders(() => useClock(), { queryClient })
    await pause()

    expect(result.current).toBe('24h')
    expect(requests()).toEqual([])
  })

  it('a reader that rendered on its own leaves the next refetch able to fetch', async () => {
    // Two observers share one query. If the reader leaves its own options on it, the
    // refetch an invalidation starts runs with them: it must still reach the server.
    let stored: Preferences = {}
    auth.preferencesBy(() => ({ ...stored }))
    const queryClient = createTestQueryClient()
    renderHookWithProviders(() => usePreferences(TOKEN), { queryClient })
    const reader = renderHookWithProviders(() => useClock(), { queryClient })
    await vi.waitFor(() => expect(cached(queryClient)).toEqual({}))
    expect(gets()).toHaveLength(1)

    reader.rerender()
    stored = { clock: '24h' }
    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: PREFS })
    })

    expect(gets()).toHaveLength(2)
    expect(queryClient.getQueryState(PREFS)?.status).toBe('success')
    expect(cached(queryClient)).toEqual({ clock: '24h' })
  })
})

describe('usePreferences', () => {
  it('fetches nothing without a token', async () => {
    const { result } = renderHookWithProviders(() => usePreferences(null))

    await pause()

    expect(result.current.data).toBeUndefined()
    expect(requests()).toEqual([])
  })

  it('asks the server again on a visit, however fresh the cache looks', async () => {
    auth.preferencesBy(() => ({ clock: '24h' }))
    const queryClient = createTestQueryClient()
    queryClient.setDefaultOptions({ queries: { retry: false, gcTime: Infinity, staleTime: Infinity } })
    queryClient.setQueryData(PREFS, { clock: '12h' })

    const { result } = renderHookWithProviders(() => usePreferences(TOKEN, { fresh: true }), {
      queryClient,
    })

    await vi.waitFor(() => expect(result.current.data).toEqual({ clock: '24h' }))
    expect(gets()).toHaveLength(1)
  })
})
