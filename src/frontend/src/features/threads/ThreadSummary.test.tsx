/**
 * The thread summary's "last reply" time follows the clock preference (issue gh-3, Req 7).
 */

import { act, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { requests } from '../../test/api'
import { createTestQueryClient, renderWithProviders } from '../../test/render'
import { ThreadSummary } from './ThreadSummary'

describe('ThreadSummary', () => {
  it('shows the last reply’s time as the cached preference says', async () => {
    const lastReplyAt = new Date(2026, 9, 16, 13, 5).toISOString()
    const queryClient = createTestQueryClient()
    queryClient.setQueryData(['preferences'], { clock: '24h' })
    renderWithProviders(
      <ThreadSummary replyCount={2} lastReplyAt={lastReplyAt} onOpen={vi.fn()} />,
      { queryClient },
    )

    const time = screen.getByText('13:05').closest('time')
    expect(time).toHaveAttribute('dateTime', lastReplyAt)

    act(() => {
      queryClient.setQueryData(['preferences'], { clock: '12h' })
    })

    await vi.waitFor(() => expect(time?.textContent).not.toContain('13'))
    expect(time?.textContent).toContain('1:05')
    expect(requests()).toHaveLength(0)
  })

  it('shows nothing at zero replies', () => {
    renderWithProviders(<ThreadSummary replyCount={0} lastReplyAt={null} onOpen={vi.fn()} />)

    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
