/**
 * The chips under a message.
 *
 * Queried by role and accessible name — `data-testid` belongs to the acceptance
 * suite, and a Vitest test neither adds nor reads one. That the chips are
 * buttons with names a screen reader can say is part of what is being asserted,
 * not an accident of how the query was written.
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ReactionBar } from './ReactionBar'

describe('ReactionBar', () => {
  it('renders nothing when nobody has reacted', () => {
    // An unreacted message has to look exactly as it did before this feature.
    const { container } = render(<ReactionBar reactions={[]} onToggle={() => undefined} />)

    expect(container).toBeEmptyDOMElement()
  })

  it('shows a count per emoji', () => {
    render(
      <ReactionBar
        reactions={[
          { emoji: 'thumbsup', count: 3, reacted: false },
          { emoji: 'heart', count: 1, reacted: true },
        ]}
        onToggle={() => undefined}
      />,
    )

    expect(screen.getByRole('button', { name: /thumbs up/i })).toHaveTextContent('3')
    expect(screen.getByRole('button', { name: /heart/i })).toHaveTextContent('1')
  })

  it('says which reactions are mine, for a screen reader and not only in colour', () => {
    render(
      <ReactionBar
        reactions={[
          { emoji: 'heart', count: 1, reacted: true },
          { emoji: 'eyes', count: 2, reacted: false },
        ]}
        onToggle={() => undefined}
      />,
    )

    expect(screen.getByRole('button', { name: /heart/i })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: /eyes/i })).toHaveAttribute('aria-pressed', 'false')
  })

  it('toggles the emoji that was clicked', async () => {
    const onToggle = vi.fn()
    render(
      <ReactionBar
        reactions={[
          { emoji: 'heart', count: 1, reacted: true },
          { emoji: 'eyes', count: 2, reacted: false },
        ]}
        onToggle={onToggle}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: /eyes/i }))

    expect(onToggle).toHaveBeenCalledWith('eyes')
    expect(onToggle).toHaveBeenCalledTimes(1)
  })
})
