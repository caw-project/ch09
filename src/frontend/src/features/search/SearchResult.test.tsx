/**
 * A search hit's date-and-time follows the clock preference (issue gh-3, Req 7).
 */

import { act, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { requests } from '../../test/api'
import { aMessage } from '../../test/factories'
import { createTestQueryClient, renderWithProviders } from '../../test/render'
import { SearchResult } from './SearchResult'

describe('SearchResult', () => {
  it('shows the time as the cached preference says', async () => {
    const message = aMessage({
      body: 'the zeppelin lands',
      createdAt: new Date(2026, 9, 16, 13, 5).toISOString(),
    })
    const queryClient = createTestQueryClient()
    queryClient.setQueryData(['preferences'], { clock: '24h' })
    renderWithProviders(
      <SearchResult message={message} channelTitle="#general" authorName="Ada Lovelace" />,
      { queryClient },
    )

    const time = screen.getByText(/13:05/).closest('time')
    expect(time).toHaveAttribute('dateTime', message.createdAt)

    act(() => {
      queryClient.setQueryData(['preferences'], { clock: '12h' })
    })

    await vi.waitFor(() => expect(time?.textContent).not.toContain('13'))
    expect(time?.textContent).toContain('1:05')
    expect(requests()).toHaveLength(0)
  })
})
