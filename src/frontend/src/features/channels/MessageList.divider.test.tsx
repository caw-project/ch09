/**
 * The "New messages" divider: where it sits, and what leaves it where it is.
 *
 * It is captured once per visit from the marker the server held at open, and
 * placed above the first loaded message after it that someone else wrote and
 * that was not deleted. Positions are counted in articles above the separator,
 * so a test does not depend on a message's text or how a tombstone renders.
 */

import type { QueryClient } from '@tanstack/react-query'
import { act, fireEvent, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { Message } from '../../lib/api/messaging'
import { auth, messaging } from '../../test/api'
import {
  aMessage,
  aMessagePage,
  aWorkspaceMember,
  messageIdAt,
  WORKSPACE_ID,
} from '../../test/factories'
import { setPageAttention } from '../../test/page'
import { renderWithProviders } from '../../test/render'
import { FakeSocket } from '../../test/socket'
import { MessageList } from './MessageList'
import { messageKeys, upsertMessage } from './useMessages'

const CHANNEL = 'channel-general'
const ADA = 'user-ada'
const GRACE = 'user-grace'

const m = (n: number, overrides: Partial<Message> = {}) =>
  aMessage({
    id: messageIdAt(n),
    channelId: CHANNEL,
    authorId: GRACE,
    body: `message ${n}`,
    ...overrides,
  })

function stubHistory(...oldestFirst: Message[]) {
  messaging.get('/api/v1/channels/{channel_id}/messages', aMessagePage([...oldestFirst].reverse()))
}

interface ListProps {
  lastReadId?: string | null
  channelFetching?: boolean
}

const list = ({ lastReadId = null, channelFetching = false }: ListProps = {}) => (
  <MessageList
    accessToken="token"
    workspaceId={WORKSPACE_ID}
    channelId={CHANNEL}
    userId={ADA}
    myRole={null}
    lastReadId={lastReadId}
    channelFetching={channelFetching}
  />
)

function renderList(props: ListProps = {}) {
  auth.members([aWorkspaceMember({ id: ADA }), aWorkspaceMember({ id: GRACE })])
  // Not visible, not focused: nothing here marks anything read, so the marker
  // a test hands in is the only one in play.
  setPageAttention({ visible: false, focused: false })
  return renderWithProviders(list(props), { socket: new FakeSocket('token') })
}

const divider = () => screen.queryByRole('separator', { name: 'New messages' })

/** How many messages sit above the divider; null when there is none. */
function messagesAboveDivider(): number | null {
  const separator = divider()
  if (!separator) return null
  const rows = [...document.querySelectorAll('article')]
  return rows.filter(
    (row) => row.compareDocumentPosition(separator) & Node.DOCUMENT_POSITION_FOLLOWING,
  ).length
}

const arrives = (queryClient: QueryClient, message: Message) =>
  act(() => upsertMessage(queryClient, messageKeys.list(WORKSPACE_ID, CHANNEL), message))

const settle = () => act(async () => new Promise((resolve) => setTimeout(resolve, 0)))

describe('MessageList — the New messages divider', () => {
  it('is drawn above the first message after the marker by someone else', async () => {
    stubHistory(m(1), m(2), m(3), m(4, { authorId: ADA }), m(5))
    renderList({ lastReadId: messageIdAt(2) })

    await screen.findByRole('separator', { name: 'New messages' })

    // Above m3, the first unread — not m5, the last.
    expect(messagesAboveDivider()).toBe(2)
  })

  it('is absent for a null marker and present for the same history with a marker', async () => {
    stubHistory(m(1), m(2), m(3))
    const first = renderList({ lastReadId: null })
    await screen.findByText('message 3')
    await settle()
    expect(divider()).not.toBeInTheDocument()
    first.unmount()

    renderList({ lastReadId: messageIdAt(1) })
    await screen.findByRole('separator', { name: 'New messages' })
    expect(messagesAboveDivider()).toBe(1)
  })

  it('grows no divider for a message that arrives during the visit', async () => {
    stubHistory(m(1), m(2))
    const unread = renderList({ lastReadId: messageIdAt(1) })
    await screen.findByRole('separator', { name: 'New messages' })

    arrives(unread.queryClient, m(3))
    await screen.findByText('message 3')

    // Still the one divider, still above m2.
    expect(screen.getAllByRole('separator', { name: 'New messages' })).toHaveLength(1)
    expect(messagesAboveDivider()).toBe(1)
    unread.unmount()

    // Read to the end: an arrival draws none, though it qualifies by author.
    const readToEnd = renderList({ lastReadId: messageIdAt(2) })
    await screen.findByText('message 2')
    await settle()
    expect(divider()).not.toBeInTheDocument()

    arrives(readToEnd.queryClient, m(3))
    await screen.findByText('message 3')
    await settle()
    expect(divider()).not.toBeInTheDocument()
  })

  it('stays where it is as the marker moves', async () => {
    stubHistory(m(1), m(2), m(3))
    const { rerender } = renderList({ lastReadId: messageIdAt(1) })
    await screen.findByRole('separator', { name: 'New messages' })

    rerender(list({ lastReadId: messageIdAt(3) }))
    await settle()

    expect(messagesAboveDivider()).toBe(1)
  })

  it('stays above its message once that message is deleted', async () => {
    stubHistory(m(1), m(2), m(3))
    const { queryClient } = renderList({ lastReadId: messageIdAt(1) })
    await screen.findByRole('separator', { name: 'New messages' })

    arrives(queryClient, m(2, { deletedAt: '2026-09-15T10:00:00Z', body: '' }))
    await settle()

    expect(screen.queryByText('message 2')).not.toBeInTheDocument()
    expect(messagesAboveDivider()).toBe(1)
  })

  it('waits for scrolling back to load the page holding the boundary', async () => {
    // Two pages, newest first on the wire. The marker is in the older one.
    messaging.get('/api/v1/channels/{channel_id}/messages', ({ request }) =>
      new URL(request.url).searchParams.get('cursor') === 'older'
        ? aMessagePage([m(3), m(2), m(1)])
        : aMessagePage([m(6), m(5), m(4)], 'older'),
    )
    renderList({ lastReadId: messageIdAt(2) })
    await screen.findByText('message 6')
    await settle()
    expect(divider()).not.toBeInTheDocument()

    // jsdom's scrollTop is 0, so a scroll event reaches for the next page.
    fireEvent.scroll(screen.getAllByRole('article')[0].parentElement as HTMLElement)
    await screen.findByText('message 1')

    // Above m3, the first message after the marker — m1 and m2 sit above it.
    await screen.findByRole('separator', { name: 'New messages' })
    expect(messagesAboveDivider()).toBe(2)
  })

  it('waits for the channel to settle', async () => {
    stubHistory(m(1), m(2))
    const { rerender } = renderList({ lastReadId: messageIdAt(1), channelFetching: true })
    await screen.findByText('message 2')
    await settle()
    expect(divider()).not.toBeInTheDocument()

    rerender(list({ lastReadId: messageIdAt(1), channelFetching: false }))

    await screen.findByRole('separator', { name: 'New messages' })
    expect(messagesAboveDivider()).toBe(1)
  })
})
