/**
 * Files in the composer (issue 4 R3, R5, R6, decisions 27, 33, 37): the picker,
 * a drop and a paste attach chips; Send waits for every chip to be ready; a
 * chip's ✕ takes it back out, cancelling what is still uploading.
 *
 * Its own file, apart from `MessageComposer.test.tsx`, because it imports modules
 * that do not exist yet — and a load failure there would hide that file's
 * existing tests. Controls are found by role and label (`Attach files`, `Send`,
 * `Remove <file name>`); the `data-testid`s are the BDD suite's.
 */

import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import * as session from '../../lib/auth/session'
import { useAttachmentStore } from '../../stores/attachments'
import { useChatStore } from '../../stores/chat'
import { asset, auth, requests, server } from '../../test/api'
import { aChip, aWorkspaceMember, WORKSPACE_ID } from '../../test/factories'
import { renderWithProviders } from '../../test/render'
import { FakeSocket } from '../../test/socket'
import { cancelAll } from '../attachments/uploads'
import { MessageComposer } from './MessageComposer'

const CHANNEL = 'channel-general'
const ADA = 'user-ada'

function renderComposer() {
  auth.members([aWorkspaceMember({ id: ADA, displayName: 'Ada Lovelace' })])
  useChatStore.getState().setConnectionStatus('connected')
  const socket = new FakeSocket('token')
  const view = renderWithProviders(
    <MessageComposer
      accessToken="token"
      workspaceId={WORKSPACE_ID}
      channelId={CHANNEL}
      channelTitle="#general"
      userId={ADA}
    />,
    { socket },
  )
  return { ...view, socket, input: screen.getByRole('textbox', { name: 'Message #general' }) }
}

const sends = (socket: FakeSocket) => socket.emitted.filter((e) => e.event === 'send_message')
const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))
const png = (name = 'diagram.png') => new File(['x'.repeat(100)], name, { type: 'image/png' })
const sendButton = () => screen.getByRole('button', { name: 'Send' })
const attachInput = () => screen.getByLabelText('Attach files')
const assetCalls = () => requests().filter((r) => r.url.pathname.startsWith('/api/v1/assets'))
const confirms = () => requests().filter((r) => r.url.pathname.endsWith('/confirm'))

function deferred() {
  let release!: () => void
  const promise = new Promise<void>((resolve) => {
    release = resolve
  })
  return { promise, release }
}

afterEach(() => {
  cancelAll()
  useAttachmentStore.getState().reset()
})

describe('MessageComposer — attaching files', () => {
  it('attaches a picked file as a chip, and Send waits until it has uploaded', async () => {
    const gate = deferred()
    asset.acceptUploads({ hold: { put: gate.promise } })
    const { user } = renderComposer()

    await user.upload(attachInput(), png('diagram.png'))

    expect(await screen.findByText('diagram.png')).toBeInTheDocument()
    // Still uploading: a chip that is not ready keeps Send off.
    expect(sendButton()).toBeDisabled()

    gate.release()

    // The same chip, ready: Send is on, with no text typed (a file is a message).
    await vi.waitFor(() => expect(sendButton()).toBeEnabled())
  })

  it('attaches a dropped file', async () => {
    asset.acceptUploads()
    const { input } = renderComposer()

    fireEvent.drop(input, { dataTransfer: { files: [png('dropped.png')], types: ['Files'] } })

    expect(await screen.findByText('dropped.png')).toBeInTheDocument()
    await vi.waitFor(() => expect(sendButton()).toBeEnabled())
  })

  it('sends only chips as an empty body with the asset ids, in chip order', async () => {
    asset.acceptUploads()
    const { user, socket } = renderComposer()
    socket.onEmit('send_message', () => new Promise(() => undefined))
    await user.upload(attachInput(), [png('b.png'), png('a.png')])
    await vi.waitFor(() => expect(sendButton()).toBeEnabled())

    await user.click(sendButton())

    expect(sends(socket)).toEqual([
      {
        event: 'send_message',
        args: [{ channelId: CHANNEL, body: '', attachmentIds: ['asset-b.png', 'asset-a.png'] }],
      },
    ])
    // Sent, so they leave the composer: a refusal is what brings them back.
    expect(screen.queryByText('b.png')).not.toBeInTheDocument()
  })

  it('sends text and files together', async () => {
    asset.acceptUploads()
    const { user, socket, input } = renderComposer()
    socket.onEmit('send_message', () => new Promise(() => undefined))
    await user.upload(attachInput(), png('diagram.png'))
    await vi.waitFor(() => expect(sendButton()).toBeEnabled())
    await user.type(input, 'the plans')

    await user.click(sendButton())

    expect(sends(socket)[0].args).toEqual([
      { channelId: CHANNEL, body: 'the plans', attachmentIds: ['asset-diagram.png'] },
    ])
  })

  it('removes a ready chip with its ✕, leaving the others', async () => {
    asset.acceptUploads()
    const { user } = renderComposer()
    await user.upload(attachInput(), [png('one.png'), png('two.png')])
    await vi.waitFor(() => expect(sendButton()).toBeEnabled())

    await user.click(screen.getByRole('button', { name: /remove one\.png/i }))

    expect(screen.queryByText('one.png')).not.toBeInTheDocument()
    expect(screen.getByText('two.png')).toBeInTheDocument()
  })

  it('removes an uploading chip with its ✕, and no confirm follows for it', async () => {
    const gate = deferred()
    asset.acceptUploads({ hold: { put: gate.promise } })
    const { user } = renderComposer()
    await user.upload(attachInput(), [png('cancelled.png'), png('kept.png')])
    await screen.findByText('cancelled.png')

    await user.click(screen.getByRole('button', { name: /remove cancelled\.png/i }))
    gate.release()

    // The other file, held at the same step and released with it, does confirm.
    await vi.waitFor(() => expect(confirms()).toHaveLength(1))
    await sleep(150)
    expect(confirms().map((r) => r.url.pathname)).toEqual(['/api/v1/assets/asset-kept.png/confirm'])
    expect(screen.queryByText('cancelled.png')).not.toBeInTheDocument()
  })

  it('keeps Send off while a chip has failed, and on again once it is removed', async () => {
    asset.acceptUploads({
      confirmAs: { status: 'failed', failureReason: 'The upload did not arrive.' },
    })
    const { user, input } = renderComposer()
    await user.type(input, 'with a broken file')
    await user.upload(attachInput(), png('broken.png'))

    // The reason is shown on the chip.
    expect(await screen.findByText('The upload did not arrive.')).toBeInTheDocument()
    expect(sendButton()).toBeDisabled()

    await user.click(screen.getByRole('button', { name: /remove broken\.png/i }))

    await vi.waitFor(() => expect(sendButton()).toBeEnabled())
  })

  it('refuses Send over ten chips, says how many to remove, and lets it through at ten', async () => {
    useAttachmentStore.getState().restore(
      CHANNEL,
      Array.from({ length: 11 }, (_, n) => aChip({ fileName: `file-${n}.png` })),
    )
    const { user } = renderComposer()

    expect(sendButton()).toBeDisabled()
    expect(screen.getByText('At most 10 files per message — remove 1.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /remove file-0\.png/i }))

    expect(screen.queryByText(/remove 1\./)).not.toBeInTheDocument()
    expect(sendButton()).toBeEnabled()
  })

  it('takes a batch that makes ten, and refuses the next file with the counts', async () => {
    asset.acceptUploads()
    useAttachmentStore.getState().restore(
      CHANNEL,
      Array.from({ length: 3 }, (_, n) => aChip({ fileName: `old-${n}.png` })),
    )
    const { user } = renderComposer()

    await user.upload(
      attachInput(),
      Array.from({ length: 7 }, (_, n) => png(`new-${n}.png`)),
    )
    await vi.waitFor(() => expect(screen.getByText('new-6.png')).toBeInTheDocument())
    expect(screen.queryByText(/At most 10 files/)).not.toBeInTheDocument()

    await user.upload(attachInput(), png('one-too-many.png'))

    expect(
      await screen.findByText('At most 10 files per message — 10 attached, 1 added.'),
    ).toBeInTheDocument()
    expect(screen.queryByText('one-too-many.png')).not.toBeInTheDocument()
  })

  it('refuses a batch that would pass ten, attaching none of it', async () => {
    asset.acceptUploads()
    useAttachmentStore.getState().restore(
      CHANNEL,
      Array.from({ length: 3 }, (_, n) => aChip({ fileName: `old-${n}.png` })),
    )
    const { user } = renderComposer()

    await user.upload(
      attachInput(),
      Array.from({ length: 8 }, (_, n) => png(`new-${n}.png`)),
    )

    expect(
      await screen.findByText('At most 10 files per message — 3 attached, 8 added.'),
    ).toBeInTheDocument()
    expect(screen.queryByText('new-0.png')).not.toBeInTheDocument()
    await sleep(50)
    expect(assetCalls()).toEqual([])
  })

  describe('the token an upload confirms with (R15, Task 8: read per step)', () => {
    /** Each Asset request's Authorization header, in order, seen as the request starts. */
    function recordAuthorization() {
      const seen: { path: string; authorization: string | null }[] = []
      const listener = ({ request }: { request: Request }) => {
        const path = new URL(request.url).pathname
        if (path.startsWith('/api/v1/assets'))
          seen.push({ path, authorization: request.headers.get('authorization') })
      }
      server.events.on('request:start', listener)
      return {
        confirms: () => seen.filter((s) => s.path.endsWith('/confirm')).map((s) => s.authorization),
        stop: () => server.events.removeListener('request:start', listener),
      }
    }

    const composer = (channelId: string, accessToken: string) => (
      <MessageComposer
        key={`composer-${channelId}`}
        accessToken={accessToken}
        workspaceId={WORKSPACE_ID}
        channelId={channelId}
        channelTitle={`#${channelId}`}
        userId={ADA}
      />
    )

    /**
     * The token is renewed the way the app renews it: the real session module signs
     * in with T1, then renews to T2 while the PUT is held; the composer's
     * `accessToken` prop follows (as `ChatLayout` feeds it from the session). Either
     * source a correct build reads — the session, or the prop kept somewhere that
     * outlives a composer — now says T2. Only a token captured when the upload
     * started still says T1, which is the bug.
     */
    async function signInAs(accessToken: string) {
      auth.me({ id: ADA, email: 'ada@collabhub.dev', displayName: 'Ada Lovelace', avatarAsset: null })
      auth.workspaces([{ id: WORKSPACE_ID, name: 'Home', role: 'owner' }])
      auth.refresh({ accessToken, tokenType: 'Bearer', expiresIn: 900 })
      auth.logout()
      await session.restore()
      const state = session.snapshot()
      // The precondition the test rests on: the session really holds this token.
      expect(state.status === 'signedIn' && state.session.accessToken).toBe(accessToken)
    }

    it('confirms with the renewed token when the session renews during the PUT', async () => {
      const gate = deferred()
      asset.acceptUploads({ hold: { put: gate.promise } })
      auth.members([aWorkspaceMember({ id: ADA, displayName: 'Ada Lovelace' })])
      await signInAs('T1')
      const { user, rerender } = renderWithProviders(composer('a', 'T1'))
      const log = recordAuthorization()
      try {
        await user.upload(screen.getByLabelText('Attach files'), png('big.png'))
        await screen.findByText('big.png')

        await signInAs('T2')
        rerender(composer('a', 'T2'))
        gate.release()

        await vi.waitFor(() => expect(log.confirms()).toHaveLength(1))
        expect(log.confirms()).toEqual(['Bearer T2'])
      } finally {
        log.stop()
        await session.signOut()
      }
    })

    it('confirms with the renewed token when the user has switched channel during the PUT', async () => {
      const gate = deferred()
      asset.acceptUploads({ hold: { put: gate.promise } })
      auth.members([aWorkspaceMember({ id: ADA, displayName: 'Ada Lovelace' })])
      await signInAs('T1')
      const { user, rerender } = renderWithProviders(composer('a', 'T1'))
      const log = recordAuthorization()
      try {
        await user.upload(screen.getByLabelText('Attach files'), png('big.png'))
        await screen.findByText('big.png')

        // Channel b: a's composer unmounts (it is keyed by channel) and the token renews.
        await signInAs('T2')
        rerender(composer('b', 'T2'))
        expect(screen.queryByText('big.png')).not.toBeInTheDocument()
        gate.release()

        // The upload carries on across the switch (R15), and its confirm is current.
        await vi.waitFor(() => expect(log.confirms()).toHaveLength(1))
        expect(log.confirms()).toEqual(['Bearer T2'])
      } finally {
        log.stop()
        await session.signOut()
      }
    })
  })

  it('pastes text as text, and a lone screenshot as a chip named for the time', async () => {
    asset.acceptUploads()
    const { user, input } = renderComposer()
    // What a browser hands a paste handler. `user.paste` runs user-event's default
    // insert unless the handler prevents it, which is what a real paste does.
    const clipboard = (files: File[], text: string) =>
      ({
        types: [...(text ? ['text/plain'] : []), ...(files.length ? ['Files'] : [])],
        files: Object.assign([...files], { item: (n: number) => files[n] ?? null }),
        getData: (format: string) => (format === 'text' || format === 'text/plain' ? text : ''),
      }) as unknown as DataTransfer
    await user.click(input)

    // Text beside a file (Excel, Word): the text pastes, nothing attaches.
    await user.paste(clipboard([png('image.png')], 'a cell'))
    expect(input).toHaveValue('a cell')
    await sleep(50)
    expect(screen.queryByText(/Pasted image/)).not.toBeInTheDocument()
    expect(assetCalls()).toEqual([])

    // A screenshot alone: no text, so the file attaches under a generated name.
    await user.paste(clipboard([png('image.png')], ''))

    expect(
      await screen.findByText(/^Pasted image \d{4}-\d{2}-\d{2} \d{2}\.\d{2}\.\d{2}\.png$/),
    ).toBeInTheDocument()
    expect(input).toHaveValue('a cell')
  })
})
