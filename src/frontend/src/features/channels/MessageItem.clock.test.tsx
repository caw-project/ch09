/**
 * The clock preference reaches a message's time (issue gh-3, Req 7).
 *
 * The preference lives in the `['preferences']` query, so a row reads it from the
 * cache and a cache write re-renders it — nothing is fetched. Seeded with
 * `setQueryData`, which is all the row ever sees of it: `ChatLayout` is what
 * fetches. A GET stub is installed so that "nothing is fetched" is something a
 * request would have shown. A separate file from `MessageItem.test.tsx`, which
 * holds that no clock means today's output.
 */

import { act, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { auth, requests } from '../../test/api'
import { aMessage } from '../../test/factories'
import { createTestQueryClient, renderWithProviders } from '../../test/render'
import { MessageItem } from './MessageItem'

const AT = new Date(2026, 9, 19, 15, 5).toISOString()
const PREFERENCES = ['preferences']

function renderAt(prefs: { clock?: '12h' | '24h' }) {
  auth.preferences({})
  const queryClient = createTestQueryClient()
  queryClient.setQueryData(PREFERENCES, prefs)
  const view = renderWithProviders(
    <MessageItem
      message={aMessage({ createdAt: AT })}
      authorName="Ada Lovelace"
      userId="someone-else"
      myRole={null}
      editError={undefined}
      editPending={false}
      onEdit={() => undefined}
      onDelete={() => undefined}
      onToggleReaction={() => undefined}
    />,
    { queryClient },
  )
  return { ...view, queryClient }
}

describe('MessageItem with a clock preference', () => {
  it('shows the time as 24-hour when that is chosen', () => {
    renderAt({ clock: '24h' })

    expect(screen.getByText(/15:05/)).toBeInTheDocument()
    expect(screen.queryByText(/pm/i)).not.toBeInTheDocument()
  })

  it('shows the time as 12-hour when that is chosen', () => {
    renderAt({ clock: '12h' })

    expect(screen.getByText(/3:05\s?pm/i)).toBeInTheDocument()
    expect(screen.queryByText(/15:05/)).not.toBeInTheDocument()
  })

  it('re-renders from a cache write and fetches nothing', () => {
    const { queryClient } = renderAt({ clock: '12h' })
    expect(screen.getByText(/3:05\s?pm/i)).toBeInTheDocument()

    act(() => {
      queryClient.setQueryData(PREFERENCES, { clock: '24h' })
    })

    expect(screen.getByText(/15:05/)).toBeInTheDocument()
    expect(screen.queryByText(/pm/i)).not.toBeInTheDocument()
    expect(requests()).toEqual([])
  })
})
