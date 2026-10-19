/**
 * The thread summary's "last reply" time follows the clock preference (issue gh-3,
 * Req 7) — one of the three times the preference reaches, beside a message's own
 * and a search result's. Read from the `['preferences']` cache; nothing is fetched.
 */

import { act, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { auth, requests } from '../../test/api'
import { createTestQueryClient, renderWithProviders } from '../../test/render'
import { ThreadSummary } from './ThreadSummary'

const AT = new Date(2026, 9, 19, 15, 5).toISOString()
const PREFERENCES = ['preferences']

function renderAt(prefs: { clock?: '12h' | '24h' }) {
  auth.preferences({})
  const queryClient = createTestQueryClient()
  queryClient.setQueryData(PREFERENCES, prefs)
  const view = renderWithProviders(
    <ThreadSummary replyCount={2} lastReplyAt={AT} onOpen={() => undefined} />,
    { queryClient },
  )
  return { ...view, queryClient }
}

describe('ThreadSummary with a clock preference', () => {
  it('shows the last reply as 24-hour when that is chosen', () => {
    renderAt({ clock: '24h' })

    expect(screen.getByText(/15:05/)).toBeInTheDocument()
    expect(screen.queryByText(/pm/i)).not.toBeInTheDocument()
  })

  it('shows the last reply as 12-hour when that is chosen', () => {
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
    expect(requests()).toEqual([])
  })
})
