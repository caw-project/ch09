/**
 * The clock preference in the query cache (issue gh-3, Req 7; register D28, D24).
 *
 * A choice applies before the server answers, a failed save puts the previous
 * choice back, and choices made in a row are sent in the order made while only
 * the latest one's outcome counts. A read that was already on its way must not
 * undo a choice — the cache key is written out literally, `['preferences']`.
 *
 * Real time throughout: TanStack's notifications are scheduled with `setTimeout`.
 */

import { act } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'

import type { Preferences } from '../../lib/auth/api'
import { auth, AUTH_URL, requests, server } from '../../test/api'
import { createTestQueryClient, renderHookWithProviders } from '../../test/render'
import { useClock, usePreferences, useSetClock } from './usePreferences'

function deferred<T = void>() {
  let release!: (value: T) => void
  const promise = new Promise<T>((resolve) => {
    release = resolve
  })
  return { promise, release }
}

const cached = (queryClient: { getQueryData: (key: string[]) => unknown }) =>
  queryClient.getQueryData(['preferences'])
const sent = (method: string) =>
  requests().filter(
    (r) => r.method === method && r.url.pathname === '/api/v1/users/me/preferences',
  )

describe('useSetClock', () => {
  it('applies a choice before the server answers', async () => {
    const reply = deferred()
    let answered = false
    auth.updatePreferences(async (patch) => {
      await reply.promise
      answered = true
      return { clock: patch.clock ?? undefined }
    })
    const queryClient = createTestQueryClient()
    queryClient.setQueryData(['preferences'], { clock: '12h' })
    const { result } = renderHookWithProviders(() => useSetClock('token'), { queryClient })

    act(() => {
      result.current.mutate('24h')
    })

    await vi.waitFor(() => expect(cached(queryClient)).toEqual({ clock: '24h' }))
    // The server has not answered: this is the optimistic value, not its reply.
    expect(answered).toBe(false)
    reply.release()
    await vi.waitFor(() => expect(sent('PATCH')).toHaveLength(1))
    expect(cached(queryClient)).toEqual({ clock: '24h' })
  })

  it('puts the previous choice back when the save fails, and exposes the error', async () => {
    auth.problem('patch', '/api/v1/users/me/preferences', 500, { title: 'Internal error' })
    const queryClient = createTestQueryClient()
    queryClient.setQueryData(['preferences'], { clock: '12h' })
    const { result } = renderHookWithProviders(() => useSetClock('token'), { queryClient })

    act(() => {
      result.current.mutate('24h')
    })

    await vi.waitFor(() => expect(result.current.error).not.toBeNull())
    expect(cached(queryClient)).toEqual({ clock: '12h' })
  })

  it('sends choices in the order made and ends on the second', async () => {
    const first = deferred()
    const second = deferred()
    auth.updatePreferences(async (patch) => {
      await (patch.clock === '24h' ? first.promise : second.promise)
      return { clock: patch.clock ?? undefined }
    })
    const queryClient = createTestQueryClient()
    queryClient.setQueryData(['preferences'], {})
    const { result } = renderHookWithProviders(() => useSetClock('token'), { queryClient })

    act(() => {
      result.current.mutate('24h')
      result.current.mutate('12h')
    })

    // Both apply at once; only the first has been sent.
    await vi.waitFor(() => expect(cached(queryClient)).toEqual({ clock: '12h' }))
    await vi.waitFor(() => expect(sent('PATCH')).toHaveLength(1))
    await act(() => new Promise<void>((resolve) => setTimeout(resolve, 30)))
    expect(sent('PATCH')).toHaveLength(1)

    // The first settles, the second is sent — and the first’s answer is not the last word.
    first.release()
    await vi.waitFor(() => expect(sent('PATCH')).toHaveLength(2))
    expect(sent('PATCH').map((r) => r.body)).toEqual([{ clock: '24h' }, { clock: '12h' }])
    expect(cached(queryClient)).toEqual({ clock: '12h' })

    second.release()
    await act(() => new Promise<void>((resolve) => setTimeout(resolve, 30)))
    expect(cached(queryClient)).toEqual({ clock: '12h' })
  })

  /** PATCH answers by call number: 500 where `failing` says so, else the held reply. */
  function patchesFailing(failing: number[], second = deferred()) {
    let calls = 0
    server.use(
      http.patch(`${AUTH_URL}/api/v1/users/me/preferences`, async ({ request }) => {
        calls += 1
        const body = (await request.json()) as { clock: '12h' | '24h' | null }
        if (failing.includes(calls)) {
          return HttpResponse.json(
            { status: 500, title: 'Internal error' },
            { status: 500, headers: { 'Content-Type': 'application/problem+json' } },
          )
        }
        await second.promise
        return HttpResponse.json(body.clock ? { clock: body.clock } : {})
      }),
    )
    return { second, calls: () => calls }
  }

  it('ignores a failure behind a later choice', async () => {
    const patching = patchesFailing([1])
    const queryClient = createTestQueryClient()
    queryClient.setQueryData(['preferences'], {})
    const { result } = renderHookWithProviders(() => useSetClock('token'), { queryClient })

    act(() => {
      result.current.mutate('24h')
      result.current.mutate('12h')
    })

    // The first has failed and the second is in flight: nothing was rolled back.
    await vi.waitFor(() => expect(patching.calls()).toBe(2))
    await act(() => new Promise<void>((resolve) => setTimeout(resolve, 30)))
    expect(cached(queryClient)).toEqual({ clock: '12h' })

    patching.second.release()
    await act(() => new Promise<void>((resolve) => setTimeout(resolve, 30)))
    expect(cached(queryClient)).toEqual({ clock: '12h' })
  })

  it('restores the starting value when every choice in the burst fails', async () => {
    const patching = patchesFailing([1, 2])
    const queryClient = createTestQueryClient()
    queryClient.setQueryData(['preferences'], { clock: '12h' })
    const { result } = renderHookWithProviders(() => useSetClock('token'), { queryClient })

    act(() => {
      result.current.mutate('24h')
      result.current.mutate(null)
    })

    await vi.waitFor(() => expect(patching.calls()).toBe(2))
    await vi.waitFor(() => expect(cached(queryClient)).toEqual({ clock: '12h' }))
  })

  it('is not undone by a read that was already in flight', async () => {
    // The server holds 12h until the PATCH lands. A refetch started before the
    // choice carries 12h home; the choice has to survive it.
    let serverHolds: Preferences = { clock: '12h' }
    const held = deferred()
    let reads = 0
    auth.preferences(async () => {
      reads += 1
      const answering = serverHolds
      if (reads === 2) await held.promise
      return answering
    })
    const patchHeld = deferred()
    auth.updatePreferences(async (patch) => {
      await patchHeld.promise
      serverHolds = patch.clock ? { clock: patch.clock } : {}
      return serverHolds
    })
    const queryClient = createTestQueryClient()
    // An active observer: only an active query is refetched by an invalidate.
    const { result } = renderHookWithProviders(
      () => ({ prefs: usePreferences('token'), set: useSetClock('token') }),
      { queryClient },
    )
    await vi.waitFor(() => expect(cached(queryClient)).toEqual({ clock: '12h' }))
    act(() => {
      void queryClient.refetchQueries({ queryKey: ['preferences'] })
    })
    await vi.waitFor(() => expect(reads).toBe(2))

    act(() => {
      result.current.set.mutate('24h')
    })
    await vi.waitFor(() => expect(cached(queryClient)).toEqual({ clock: '24h' }))

    // The old read lands with the old answer while the PATCH is still pending:
    // only the cancel in onMutate keeps it from showing 12h again meanwhile.
    await vi.waitFor(() => expect(sent('PATCH')).toHaveLength(1))
    held.release()
    await act(() => new Promise<void>((resolve) => setTimeout(resolve, 50)))
    expect(cached(queryClient)).toEqual({ clock: '24h' })

    patchHeld.release()
    await act(() => new Promise<void>((resolve) => setTimeout(resolve, 30)))
    expect(cached(queryClient)).toEqual({ clock: '24h' })

    // And once the PATCH has settled, the cache is checked against the server again.
    await vi.waitFor(() => expect(reads).toBeGreaterThanOrEqual(3))
    await vi.waitFor(() => expect(cached(queryClient)).toEqual({ clock: '24h' }))
  })
})

describe('useClock', () => {
  it('follows the cache without fetching anything', async () => {
    const queryClient = createTestQueryClient()
    const { result } = renderHookWithProviders(() => useClock(), { queryClient })
    expect(result.current).toBeUndefined()

    act(() => {
      queryClient.setQueryData(['preferences'], { clock: '24h' })
    })
    await vi.waitFor(() => expect(result.current).toBe('24h'))

    act(() => {
      queryClient.setQueryData(['preferences'], {})
    })
    await vi.waitFor(() => expect(result.current).toBeUndefined())

    act(() => {
      queryClient.setQueryData(['preferences'], { clock: '12h' })
    })
    await vi.waitFor(() => expect(result.current).toBe('12h'))
    expect(requests()).toHaveLength(0)
  })
})
