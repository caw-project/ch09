import { act, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Channel } from '../../lib/api/messaging'
import { messaging, requests } from '../../test/api'
import { aChannel, WORKSPACE_ID } from '../../test/factories'
import { setPageAttention } from '../../test/page'
import { renderWithProviders } from '../../test/render'
import { useChatStore } from '../../stores/chat'
import { ChannelHeader } from './ChannelHeader'
import { ChannelList } from './ChannelList'
import { channelKeys } from './useChannels'

describe('ChannelList', () => {
  it('links to every channel the server returns, in its order', async () => {
    const general = aChannel({ name: 'general' })
    const random = aChannel({ name: 'random' })
    messaging.get('/api/v1/channels', { items: [general, random], nextCursor: null })

    renderWithProviders(<ChannelList accessToken="token" workspaceId={WORKSPACE_ID} />)

    const links = await screen.findAllByRole('link')
    expect(links.map((link) => link.textContent?.replace('#', '').trim())).toEqual([
      'general',
      'random',
    ])
    expect(links[1]).toHaveAttribute('href', `/c/${random.id}`)
  })

  it('invites the first channel when there are none', async () => {
    messaging.get('/api/v1/channels', { items: [], nextCursor: null })

    renderWithProviders(<ChannelList accessToken="token" workspaceId={WORKSPACE_ID} />)

    expect(await screen.findByText('No channels yet. Create the first one.')).toBeInTheDocument()
  })

  it('drops a channel an admin archives, and leaves its page', async () => {
    const general = aChannel({ name: 'general' })
    const random = aChannel({ name: 'random', myRole: 'admin' })
    let channels: Channel[] = [general, random]
    messaging.get('/api/v1/channels', () => ({ items: channels, nextCursor: null }))
    messaging.delete('/api/v1/channels/{channel_id}', ({ params }) => {
      channels = channels.filter((c) => c.id !== params.channel_id)
      return { ...random, archivedAt: '2026-09-15T10:00:00Z' }
    })
    const { user, location } = renderWithProviders(
      <>
        <ChannelList accessToken="token" workspaceId={WORKSPACE_ID} />
        <ChannelHeader accessToken="token" workspaceId={WORKSPACE_ID} channel={random} />
      </>,
      { route: `/c/${random.id}` },
    )
    expect(await screen.findByRole('link', { name: 'random' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Archive' }))
    const confirm = screen.getByText(/Nobody will be able to open it again/).parentElement
    await user.click(within(confirm as HTMLElement).getByRole('button', { name: 'Archive' }))

    // Wait on the path, not only the link: the list refetch removes the link
    // first, and `navigate('/')` runs after it in the mutation's `onSuccess`.
    await vi.waitFor(() => {
      expect(location().pathname).toBe('/')
      expect(screen.queryByRole('link', { name: 'random' })).not.toBeInTheDocument()
    })
    expect(screen.getByRole('link', { name: 'general' })).toBeInTheDocument()
  })
})

describe('ChannelList — unread counts', () => {
  const renderList = (...channels: Channel[]) => {
    messaging.get('/api/v1/channels', { items: channels, nextCursor: null })
    return renderWithProviders(<ChannelList accessToken="token" workspaceId={WORKSPACE_ID} />)
  }

  it('shows a count pill and a bold name for a channel with unread messages', async () => {
    renderList(aChannel({ name: 'general', unreadCount: 3 }), aChannel({ name: 'random' }))

    const pill = await screen.findByLabelText('3 unread messages')

    expect(pill).toHaveTextContent('3')
    const link = screen.getByRole('link', { name: /^general/ })
    expect(within(link).getByText('general')).toHaveClass('font-semibold')
    // The channel with none keeps an ordinary name.
    expect(within(screen.getByRole('link', { name: 'random' })).getByText('random')).not.toHaveClass(
      'font-semibold',
    )
  })

  it('shows no pill for a channel with none', async () => {
    renderList(aChannel({ name: 'general', unreadCount: 3 }), aChannel({ name: 'random' }))
    // The other channel's pill is found first, so the list has rendered.
    await screen.findByLabelText('3 unread messages')

    const random = screen.getByRole('link', { name: 'random' })

    expect(within(random).queryByLabelText(/unread message/)).not.toBeInTheDocument()
  })

  it('shows 99 as 99 and 100 as 99+', async () => {
    renderList(
      aChannel({ name: 'general', unreadCount: 99 }),
      aChannel({ name: 'random', unreadCount: 100 }),
    )

    expect(await screen.findByLabelText('99 unread messages')).toHaveTextContent(/^99$/)
    expect(screen.getByLabelText('99+ unread messages')).toHaveTextContent(/^99\+$/)
  })

  it('labels one unread message in the singular', async () => {
    renderList(aChannel({ name: 'general', unreadCount: 1 }))

    expect(await screen.findByLabelText('1 unread message')).toHaveTextContent('1')
  })

  it('hides the badge of the channel being read, and only that one', async () => {
    const general = aChannel({ name: 'general', unreadCount: 3 })
    const random = aChannel({ name: 'random', unreadCount: 2 })
    useChatStore.setState({ readingChannelId: general.id })
    renderList(general, random)

    // The other channel's badge is the positive half: the list has rendered.
    expect(await screen.findByLabelText('2 unread messages')).toBeInTheDocument()
    expect(screen.queryByLabelText('3 unread messages')).not.toBeInTheDocument()
  })
})

describe('ChannelList — refreshing the counts', () => {
  const listGets = () =>
    requests().filter((r) => r.method === 'GET' && r.url.pathname === '/api/v1/channels').length
  const sleep = (ms: number) => act(() => new Promise<void>((resolve) => setTimeout(resolve, ms)))

  function renderPolled() {
    messaging.get('/api/v1/channels', {
      items: [aChannel({ name: 'general' })],
      nextCursor: null,
    })
    return renderWithProviders(<ChannelList accessToken="token" workspaceId={WORKSPACE_ID} />)
  }

  afterEach(() => {
    vi.useRealTimers()
  })

  it('refetches every 30 seconds while visible', async () => {
    // Only the interval is fake: TanStack's notifications use `setTimeout`.
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    setPageAttention({ visible: true, focused: true })
    renderPolled()
    await screen.findByRole('link', { name: 'general' })
    expect(listGets()).toBe(1)

    await act(() => vi.advanceTimersByTimeAsync(29_999))
    await sleep(50)
    expect(listGets()).toBe(1)

    await act(() => vi.advanceTimersByTimeAsync(1))
    await sleep(100)
    expect(listGets()).toBe(2)
  })

  it('pauses the poll while hidden, refetches once on return, then polls again', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    setPageAttention({ visible: true, focused: true })
    renderPolled()
    await screen.findByRole('link', { name: 'general' })

    act(() => setPageAttention({ visible: false, focused: true }))
    await act(() => vi.advanceTimersByTimeAsync(30_000))
    await sleep(100)
    expect(listGets()).toBe(1)

    // The return fires visibilitychange and focus together: one refetch, not two.
    act(() => setPageAttention({ visible: true, focused: true }))
    await sleep(150)
    expect(listGets()).toBe(2)

    // And the poll is back: a tick 30 s on. (TanStack's own refetch on return
    // already makes the count above pass today; this is the half that doesn't.)
    await act(() => vi.advanceTimersByTimeAsync(30_000))
    await sleep(100)
    expect(listGets()).toBe(3)
  })

  it('refetches once when the window regains focus with the tab visible', async () => {
    setPageAttention({ visible: true, focused: false })
    renderPolled()
    await screen.findByRole('link', { name: 'general' })
    expect(listGets()).toBe(1)

    // Only `focus` fires: the tab was visible all along, so TanStack hears nothing.
    act(() => setPageAttention({ visible: true, focused: true }))
    await sleep(150)

    expect(listGets()).toBe(2)
  })

  it('keeps the list it shows when a refetch fails', async () => {
    const { queryClient } = renderPolled()
    await screen.findByRole('link', { name: 'general' })

    messaging.problem('get', '/api/v1/channels', 500, { title: 'Internal Server Error' })
    await act(() => queryClient.invalidateQueries({ queryKey: channelKeys.list(WORKSPACE_ID) }))
    await vi.waitFor(() => expect(listGets()).toBe(2))
    await sleep(100)

    expect(screen.getByRole('link', { name: 'general' })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows the error when the list never loaded', async () => {
    messaging.problem('get', '/api/v1/channels', 500, { title: 'Internal Server Error' })

    renderWithProviders(<ChannelList accessToken="token" workspaceId={WORKSPACE_ID} />)

    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })
})
