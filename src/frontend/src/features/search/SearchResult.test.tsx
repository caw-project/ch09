/**
 * A search result's time follows the clock preference (issue gh-3, Req 7) — the
 * third of the three times it reaches. Read from the `['preferences']` cache;
 * nothing is fetched.
 */

import { act, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { auth, requests } from '../../test/api'
import { aMessage } from '../../test/factories'
import { createTestQueryClient, renderWithProviders } from '../../test/render'
import { SearchResult } from './SearchResult'

const AT = new Date(2026, 9, 19, 15, 5).toISOString()
const PREFERENCES = ['preferences']

function renderAt(prefs: { clock?: '12h' | '24h' }) {
  auth.preferences({})
  const queryClient = createTestQueryClient()
  queryClient.setQueryData(PREFERENCES, prefs)
  const view = renderWithProviders(
    <SearchResult
      message={aMessage({ createdAt: AT, body: 'the zeppelin lands' })}
      channelTitle="#general"
      authorName="Ada Lovelace"
    />,
    { queryClient },
  )
  return { ...view, queryClient }
}

describe('SearchResult with a clock preference', () => {
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
    expect(requests()).toEqual([])
  })
})
