/**
 * The clock preference reaches every place a time is drawn (issue gh-3, Req 7):
 * a message, a thread summary, a search result.
 *
 * The preference is seeded into the query cache the way the app's own fetch
 * leaves it, and then **changed** in place, so each test also proves the time on
 * screen re-renders without anything being refetched. Both directions are
 * checked, because a site that ignores the clock shows the browser's format
 * either way and passes whichever single direction it is given.
 */

import { act, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { aMessage } from '../../test/factories'
import { createTestQueryClient, renderWithProviders } from '../../test/render'
import { MessageItem } from '../channels/MessageItem'
import { SearchResult } from '../search/SearchResult'
import { preferenceKeys } from './usePreferences'

const at = (hour: number, minute: number) => new Date(2026, 8, 15, hour, minute).toISOString()

function clientWith(clock: '12h' | '24h') {
  const queryClient = createTestQueryClient()
  queryClient.setQueryData(preferenceKeys.mine, { clock })
  return queryClient
}

/**
 * TanStack tells its observers on a `setTimeout(0)` batch, which a synchronous `act`
 * does not flush — so the change is made, then a macrotask is let through inside `act`
 * before the test looks at the screen.
 */
async function choose(queryClient: ReturnType<typeof clientWith>, clock: '12h' | '24h') {
  await act(async () => {
    queryClient.setQueryData(preferenceKeys.mine, { clock })
    await new Promise<void>((resolve) => setTimeout(resolve, 20))
  })
}

function row(message: ReturnType<typeof aMessage>, withThread = false) {
  return (
    <MessageItem
      message={message}
      authorName="Ada Lovelace"
      userId="someone-else"
      myRole={null}
      editError={undefined}
      editPending={false}
      onEdit={vi.fn()}
      onDelete={vi.fn()}
      onToggleReaction={vi.fn()}
      onOpenThread={withThread ? vi.fn() : undefined}
    />
  )
}

describe('the clock preference', () => {
  it('a message time follows the stored clock', async () => {
    const queryClient = clientWith('24h')
    renderWithProviders(row(aMessage({ createdAt: at(15, 7) })), { queryClient })
    const time = () => screen.getByText(/:07/)

    expect(time()).toHaveTextContent(/\b15:07\b/)

    await choose(queryClient, '12h')
    expect(time()).toHaveTextContent(/\b0?3:07\b/)
    expect(time()).not.toHaveTextContent(/15:07/)

    await choose(queryClient, '24h')
    expect(time()).toHaveTextContent(/\b15:07\b/)
  })

  it('a thread summary time follows it', async () => {
    const queryClient = clientWith('24h')
    // The message's own time is the morning, so the afternoon digits are the summary's alone.
    renderWithProviders(
      row(aMessage({ createdAt: at(8, 0), replyCount: 2, lastReplyAt: at(15, 7) }), true),
      { queryClient },
    )
    const summary = () => screen.getByRole('button', { name: /2 replies/ })

    expect(within(summary()).getByText(/:07/)).toHaveTextContent(/\b15:07\b/)

    await choose(queryClient, '12h')
    expect(within(summary()).getByText(/:07/)).toHaveTextContent(/\b0?3:07\b/)
    expect(within(summary()).getByText(/:07/)).not.toHaveTextContent(/15:07/)
  })

  it('a search result time follows it', async () => {
    const queryClient = clientWith('24h')
    renderWithProviders(
      <SearchResult
        message={aMessage({ createdAt: at(15, 7), body: 'the zeppelin lands' })}
        channelTitle="#general"
        authorName="Ada Lovelace"
      />,
      { queryClient },
    )
    const time = () => screen.getByText(/:07/)

    expect(time()).toHaveTextContent(/\b15:07\b/)
    expect(time()).toHaveTextContent(/2026/)

    await choose(queryClient, '12h')
    expect(time()).toHaveTextContent(/\b0?3:07\b/)
    expect(time()).not.toHaveTextContent(/15:07/)
  })

  it('with no stored clock a message shows the browser’s own format', () => {
    const queryClient = createTestQueryClient()
    queryClient.setQueryData(preferenceKeys.mine, {})
    const iso = at(15, 7)
    renderWithProviders(row(aMessage({ createdAt: iso })), { queryClient })

    expect(screen.getByText(/:07/).textContent).toBe(
      new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    )
  })
})
