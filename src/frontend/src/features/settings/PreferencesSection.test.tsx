/**
 * The Preferences section of `/settings`: the clock (issue gh-3, Req 7, 8).
 *
 * A choice saves at once and shows at once, so most of what is worth testing is
 * what happens when saves overlap or fail. The PATCH is held in the test (a
 * promise the stub awaits) and answered by hand, so each ordering is one the test
 * chose rather than one the timers happened to produce.
 *
 * Saves go out one at a time in click order, and the radio always ends on the
 * last choice the server accepted, or on the choice before them all if none was.
 * What the radio shows while a *refetch* lands mid-save is deliberately not pinned.
 */

import { act, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Clock, Preferences } from '../../lib/auth/api'
import { auth, failWith, requests } from '../../test/api'
import { aMessage } from '../../test/factories'
import { setPageAttention } from '../../test/page'
import { createTestQueryClient, renderWithProviders } from '../../test/render'
import { MessageItem } from '../channels/MessageItem'
import { PreferencesSection } from './PreferencesSection'
import { preferenceKeys } from './usePreferences'

const TOKEN = 'test-token'

const radio = (name: 'Automatic' | '12-hour' | '24-hour') =>
  screen.findByRole('radio', { name })
const checked = (name: 'Automatic' | '12-hour' | '24-hour') =>
  screen.getByRole('radio', { name }) as HTMLInputElement

const patches = () => requests().filter((r) => r.method === 'PATCH')
const gets = () =>
  requests().filter((r) => r.method === 'GET' && r.url.pathname === '/api/v1/users/me/preferences')

const sleep = (ms: number) => act(() => new Promise<void>((resolve) => setTimeout(resolve, ms)))

/** Every PATCH is held until the test answers it; `held[i]` exists once request `i` arrived. */
function holdPatches() {
  const held: { body: { clock: Clock | null }; answer: (reply: Preferences | ReturnType<typeof failWith>) => Promise<void> }[] = []
  auth.updatePreferences(
    ({ body }) =>
      new Promise((resolve) => {
        held.push({
          body: body as { clock: Clock | null },
          answer: (reply) => act(async () => resolve(reply)),
        })
      }),
  )
  return held
}

const idle = (queryClient: ReturnType<typeof createTestQueryClient>) =>
  vi.waitFor(() => expect(queryClient.isMutating()).toBe(0))

describe('PreferencesSection — reading', () => {
  it('shows the stored clock, read from the server', async () => {
    const queryClient = createTestQueryClient()
    queryClient.setQueryData(preferenceKeys.mine, { clock: '12h' })
    auth.preferences({ clock: '24h' })

    renderWithProviders(<PreferencesSection accessToken={TOKEN} />, { queryClient })

    // The cache said 12-hour; this visit's answer wins.
    await vi.waitFor(() => expect(checked('24-hour').checked).toBe(true))
    expect(checked('12-hour').checked).toBe(false)
    expect(screen.getByRole('radiogroup', { name: 'Clock' })).toBeInTheDocument()
  })

  it('refetches on window focus', async () => {
    let call = 0
    auth.preferences(() => (++call === 1 ? {} : { clock: '24h' }))
    renderWithProviders(<PreferencesSection accessToken={TOKEN} />)
    await vi.waitFor(() => expect(checked('Automatic').checked).toBe(true))
    expect(gets()).toHaveLength(1)

    // TanStack hears `visibilitychange` only, so the tab has to leave and come back.
    act(() => setPageAttention({ visible: false, focused: false }))
    act(() => setPageAttention({ visible: true, focused: true }))

    await vi.waitFor(() => expect(checked('24-hour').checked).toBe(true))
    expect(gets()).toHaveLength(2)
  })
})

describe('PreferencesSection — choosing', () => {
  it('choosing saves at once with only that key', async () => {
    auth.preferences({})
    auth.updatePreferences(({ body }) => {
      const clock = (body as { clock: Clock | null }).clock
      return clock === null ? {} : { clock }
    })
    const { user, queryClient } = renderWithProviders(<PreferencesSection accessToken={TOKEN} />)

    await user.click(await radio('24-hour'))
    await vi.waitFor(() => expect(patches()).toHaveLength(1))
    await idle(queryClient)
    await user.click(checked('Automatic'))
    await vi.waitFor(() => expect(patches()).toHaveLength(2))
    await idle(queryClient)

    expect(patches().map((p) => p.body)).toEqual([{ clock: '24h' }, { clock: null }])
    expect(checked('Automatic').checked).toBe(true)
    expect(checked('24-hour').checked).toBe(false)
  })

  it('a failed save puts the previous choice back and shows the error', async () => {
    auth.preferences({ clock: '12h' })
    const held = holdPatches()
    const { user } = renderWithProviders(<PreferencesSection accessToken={TOKEN} />)
    await vi.waitFor(() => expect(checked('12-hour').checked).toBe(true))

    await user.click(checked('24-hour'))
    await vi.waitFor(() => expect(held).toHaveLength(1))
    // In flight: the choice already shows.
    expect(checked('24-hour').checked).toBe(true)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()

    await held[0].answer(failWith(500, { title: 'Internal error' }))

    await vi.waitFor(() => expect(checked('12-hour').checked).toBe(true))
    expect(checked('24-hour').checked).toBe(false)
    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })

  describe('with two saves in a row', () => {
    /** Start from Automatic, choose 12-hour then 24-hour, and wait for the first PATCH to arrive. */
    async function chooseTwice() {
      auth.preferences({})
      const held = holdPatches()
      const view = renderWithProviders(<PreferencesSection accessToken={TOKEN} />)
      await vi.waitFor(() => expect(checked('Automatic').checked).toBe(true))
      await view.user.click(checked('12-hour'))
      await vi.waitFor(() => expect(held).toHaveLength(1))
      await view.user.click(checked('24-hour'))
      return { held, ...view }
    }

    it('a second choice waits for the first save, and the tab and the server end on the last', async () => {
      const { held, queryClient } = await chooseTwice()

      // The second save is not sent while the first is open — a parallel build has
      // sent it by now — and the radio already shows the latest choice.
      await sleep(60)
      expect(patches()).toHaveLength(1)
      expect(checked('24-hour').checked).toBe(true)

      await held[0].answer({ clock: '12h' })
      await vi.waitFor(() => expect(held).toHaveLength(2))
      // The first answer is the older choice's: it must not move the radio back.
      await sleep(60)
      expect(checked('24-hour').checked).toBe(true)
      expect(checked('12-hour').checked).toBe(false)

      await held[1].answer({ clock: '24h' })
      await idle(queryClient)
      expect(checked('24-hour').checked).toBe(true)
      expect(patches().map((p) => p.body)).toEqual([{ clock: '12h' }, { clock: '24h' }])
    })

    it('a failed second save goes back to the first, which was saved', async () => {
      const { held, queryClient } = await chooseTwice()

      await held[0].answer({ clock: '12h' })
      await vi.waitFor(() => expect(held).toHaveLength(2))
      await held[1].answer(failWith(500, { title: 'Internal error' }))
      await idle(queryClient)

      await vi.waitFor(() => expect(checked('12-hour').checked).toBe(true))
      expect(checked('24-hour').checked).toBe(false)
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })

    it('a failed first save under a successful second ends on the second, with no error', async () => {
      const { held, queryClient } = await chooseTwice()

      await held[0].answer(failWith(500, { title: 'Internal error' }))
      await vi.waitFor(() => expect(held).toHaveLength(2))
      await held[1].answer({ clock: '24h' })
      await idle(queryClient)

      expect(checked('24-hour').checked).toBe(true)
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    })

    it('two failed saves go back to the choice before either', async () => {
      const { held, queryClient } = await chooseTwice()

      await held[0].answer(failWith(500, { title: 'Internal error' }))
      await vi.waitFor(() => expect(held).toHaveLength(2))
      await held[1].answer(failWith(500, { title: 'Internal error' }))
      await idle(queryClient)

      // Automatic, where it started — not 12-hour, the snapshot the second click saw.
      await vi.waitFor(() => expect(checked('Automatic').checked).toBe(true))
      expect(checked('12-hour').checked).toBe(false)
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
  })

  it('choosing re-renders a time already on screen without refetching', async () => {
    const instant = new Date(2026, 8, 15, 15, 7).toISOString()
    auth.preferences({})
    auth.updatePreferences(({ body }) => ({ clock: (body as { clock: Clock }).clock }))
    const { user, queryClient } = renderWithProviders(
      <>
        <PreferencesSection accessToken={TOKEN} />
        <MessageItem
          message={aMessage({ createdAt: instant })}
          authorName="Grace Hopper"
          userId="someone-else"
          myRole={null}
          editError={undefined}
          editPending={false}
          onEdit={vi.fn()}
          onDelete={vi.fn()}
          onToggleReaction={vi.fn()}
        />
      </>,
    )
    await vi.waitFor(() => expect(checked('Automatic').checked).toBe(true))
    const time = () => screen.getByText(/:07/)

    await user.click(checked('24-hour'))
    await vi.waitFor(() => expect(time()).toHaveTextContent(/\b15:07\b/))
    await idle(queryClient)
    await user.click(checked('12-hour'))
    await vi.waitFor(() => expect(time()).toHaveTextContent(/\b0?3:07\b/))
    await idle(queryClient)
    await sleep(60)

    // The list on screen was redrawn from the cache: nothing was asked for again.
    expect(gets()).toHaveLength(1)
    expect(patches()).toHaveLength(2)
  })
})
