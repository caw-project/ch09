/**
 * The thread composer: a draft per root, apart from the channel's (R14), and the
 * same send, refusal and offline behaviour as the channel's own composer.
 */

import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useChatStore } from '../../stores/chat'
import { WORKSPACE_ID } from '../../test/factories'
import { renderWithProviders } from '../../test/render'
import { FakeSocket } from '../../test/socket'
import { ThreadComposer } from './ThreadComposer'

const CHANNEL = 'channel-general'
const ADA = 'user-ada'
const ROOT_A = 'root-a'
const ROOT_B = 'root-b'

function composer(rootId: string) {
  return (
    <ThreadComposer workspaceId={WORKSPACE_ID} channelId={CHANNEL} rootId={rootId} userId={ADA} />
  )
}

function renderComposer({ connected = true, rootId = ROOT_A } = {}) {
  useChatStore.getState().setConnectionStatus(connected ? 'connected' : 'disconnected')
  const socket = new FakeSocket('token')
  const view = renderWithProviders(composer(rootId), { socket })
  return { ...view, socket }
}

const box = () => screen.getByRole('textbox', { name: 'Reply' })
const sends = (socket: FakeSocket) => socket.emitted.filter((e) => e.event === 'send_message')

describe('ThreadComposer', () => {
  it('keeps a draft per root, apart from the channel’s', async () => {
    useChatStore.getState().setDraft(CHANNEL, 'the channel draft')
    const { user, rerender } = renderComposer({ rootId: ROOT_A })

    await user.type(box(), 'for thread a')
    rerender(composer(ROOT_B))
    expect(box()).toHaveValue('')
    await user.type(box(), 'for thread b')
    rerender(composer(ROOT_A))

    expect(box()).toHaveValue('for thread a')
    expect(useChatStore.getState().threadDrafts).toEqual({
      [ROOT_A]: 'for thread a',
      [ROOT_B]: 'for thread b',
    })
    expect(useChatStore.getState().drafts).toEqual({ [CHANNEL]: 'the channel draft' })
  })

  it('Enter sends with the root and clears', async () => {
    const { user, socket } = renderComposer()
    socket.onEmit('send_message', () => new Promise(() => undefined))

    await user.type(box(), 'I am{Enter}')

    expect(sends(socket)).toEqual([
      { event: 'send_message', args: [{ channelId: CHANNEL, body: 'I am', threadRootId: ROOT_A }] },
    ])
    expect(box()).toHaveValue('')
  })

  it('the Send reply button sends too', async () => {
    const { user, socket } = renderComposer()
    socket.onEmit('send_message', () => new Promise(() => undefined))

    await user.type(box(), 'I am')
    await user.click(screen.getByRole('button', { name: 'Send reply' }))

    expect(sends(socket)).toHaveLength(1)
    expect(box()).toHaveValue('')
  })

  it('a refusal puts the text back and says why', async () => {
    const { user, socket } = renderComposer()
    socket.onEmit('send_message', () => ({
      ok: false,
      problem: {
        status: 400,
        title: 'Validation error',
        detail: 'A message cannot be empty.',
        errors: { body: ['A message cannot be empty.'] },
      },
    }))

    await user.type(box(), '   {Enter}')

    expect(await screen.findByRole('alert')).toHaveTextContent('A message cannot be empty.')
    expect(box()).toHaveValue('   ')
  })

  it('is disabled, and says so, while the connection is down', () => {
    const { unmount } = renderComposer({ connected: true })
    expect(box()).toBeEnabled()
    unmount()

    renderComposer({ connected: false })

    expect(box()).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Send reply' })).toBeDisabled()
    expect(screen.getByText(/Not connected/)).toBeInTheDocument()
  })
})
