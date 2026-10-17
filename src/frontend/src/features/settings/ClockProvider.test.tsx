/**
 * The clock reaching the three places a time is shown (issue gh-3 Req 7).
 *
 * `MessageItem`, `ThreadSummary` and `SearchResult` are rendered under the
 * provider the shell mounts, with the preference stubbed at the network edge.
 * Times are local 13:05, so "24-hour" and the browser's automatic format (a
 * 12-hour clock in the locale Vitest runs in) read differently.
 */

import { act, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Clock } from '../../lib/auth/api'
import { auth, requests } from '../../test/api'
import { aMessage } from '../../test/factories'
import { renderWithProviders } from '../../test/render'
import { MessageItem } from '../channels/MessageItem'
import { SearchResult } from '../search/SearchResult'
import { ThreadSummary } from '../threads/ThreadSummary'
import { ClockProvider } from './ClockProvider'

const USER = 'user-ada'
const SENT = new Date(2026, 9, 17, 13, 5).toISOString()
const AUTOMATIC_TIME = new Date(SENT).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
const AUTOMATIC_DATE = new Date(SENT).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })

const preferenceRequests = () =>
  requests().filter((r) => r.url.pathname === '/api/v1/users/me/preferences')

const macrotask = () => act(() => new Promise<void>((resolve) => setTimeout(resolve, 0)))

function message() {
  return aMessage({ authorId: USER, createdAt: SENT })
}

const inRow = () => (
  <MessageItem
    message={message()}
    authorName="Ada Lovelace"
    userId={USER}
    myRole={null}
    editError={undefined}
    editPending={false}
    onEdit={vi.fn()}
    onDelete={vi.fn()}
    onToggleReaction={vi.fn()}
  />
)
const inSummary = () => <ThreadSummary replyCount={2} lastReplyAt={SENT} onOpen={vi.fn()} />
const inResult = () => (
  <SearchResult message={message()} channelTitle="#general" authorName="Ada Lovelace" />
)

const places: [string, () => React.ReactElement, string][] = [
  ['a message row', inRow, AUTOMATIC_TIME],
  ['a thread summary', inSummary, AUTOMATIC_TIME],
  ['a search result', inResult, AUTOMATIC_DATE],
]

function renderUnderClock(ui: React.ReactElement) {
  return renderWithProviders(
    <ClockProvider accessToken="token" userId={USER}>
      {ui}
    </ClockProvider>,
  )
}

describe('the clock in each formatter', () => {
  it.each(places)('%s follows a 24-hour clock', async (_name, build) => {
    auth.preferences({ clock: '24h' })

    renderUnderClock(build())

    expect(await screen.findByText(/13:05/)).toBeInTheDocument()
    expect(screen.queryByText(/PM/i)).not.toBeInTheDocument()
  })

  it.each(places)('%s follows a 12-hour clock', async (_name, build) => {
    auth.preferences({ clock: '12h' })

    renderUnderClock(build())

    expect(await screen.findByText(/1:05\s?PM/i)).toBeInTheDocument()
    expect(screen.queryByText(/13:05/)).not.toBeInTheDocument()
  })

  it.each(places)('%s keeps the browser’s format with no choice made', async (_name, build, automatic) => {
    auth.preferences({})

    renderUnderClock(build())

    // The preference has been read and has said nothing, so this is not "not yet".
    await vi.waitFor(() => expect(preferenceRequests()).toHaveLength(1))
    await macrotask()
    expect(screen.getByText(automatic)).toBeInTheDocument()
    expect(screen.queryByText(/13:05/)).not.toBeInTheDocument()
  })
})

describe('a changed clock', () => {
  it('re-renders cached messages from the cache and fetches nothing', async () => {
    auth.preferences({})
    const { queryClient } = renderUnderClock(inRow())
    await vi.waitFor(() => expect(preferenceRequests()).toHaveLength(1))
    await macrotask()
    expect(screen.getByText(AUTOMATIC_TIME)).toBeInTheDocument()
    const sent = requests().length

    // What a successful save writes: the cache entry the provider reads.
    const choice: { clock: Clock } = { clock: '24h' }
    act(() => {
      queryClient.setQueryData(['user-preferences', USER], choice)
    })

    expect(await screen.findByText('13:05')).toBeInTheDocument()
    await macrotask()
    expect(requests()).toHaveLength(sent)
  })
})
