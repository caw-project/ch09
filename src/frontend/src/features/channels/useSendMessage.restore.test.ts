/**
 * A refused send comes back to its own channel (issue 4 R13, R14, decisions 33–35).
 *
 * TanStack Query v5 keeps one `mutate`-level `onError` — the latest call's — and
 * the hook's own `onError` runs for every mutation. So a restore written per call
 * misses an earlier send when a later one is in flight, and a cache write keyed on
 * the hook's `channelId` argument hits the wrong channel once the user has moved.
 * Each test here makes one of those the only thing that can pass it.
 *
 * Its own file because it imports `stores/attachments`, which does not exist yet:
 * every test here asserts on chips or on the send error, so a load failure hides
 * nothing that would have run (`useMessages.test.ts` keeps its tests loading).
 */

import type { InfiniteData, QueryClient } from '@tanstack/react-query'
import { act } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Message, MessagePage } from '../../lib/api/messaging'
import { useAttachmentStore } from '../../stores/attachments'
import { useChatStore } from '../../stores/chat'
import { aChip, aMessage, aMessagePage } from '../../test/factories'
import { createTestQueryClient, renderHookWithProviders } from '../../test/render'
import { asSocket, FakeSocket } from '../../test/socket'
import { messageKeys, useSendMessage } from './useMessages'

const WORKSPACE = 'workspace-1'
const A = 'channel-a'
const B = 'channel-b'
const ADA = 'user-ada'

const REFUSED = {
  ok: false,
  problem: {
    status: 409,
    title: 'Conflict',
    detail: 'An attachment is already on another message.',
  },
}

const draftOf = (channelId: string) => useChatStore.getState().drafts[channelId]
const errorOf = (channelId: string) => useChatStore.getState().sendErrors[channelId] ?? null
const chipsOf = (channelId: string) => useAttachmentStore.getState().chips[channelId] ?? []

function itemsIn(queryClient: QueryClient, channelId: string): Message[] {
  const data = queryClient.getQueryData<InfiniteData<MessagePage>>(
    messageKeys.list(WORKSPACE, channelId),
  )
  return (data?.pages ?? []).flatMap((page) => page.items)
}

function seeded(initial: Record<string, Message[]> = {}) {
  const queryClient = createTestQueryClient()
  for (const channelId of [A, B]) {
    queryClient.setQueryData<InfiniteData<MessagePage>>(messageKeys.list(WORKSPACE, channelId), {
      pages: [aMessagePage(initial[channelId] ?? [])],
      pageParams: [undefined],
    })
  }
  return queryClient
}

/** A socket whose acks the test settles by channel, one at a time. */
function heldSocket() {
  const socket = new FakeSocket('token')
  const settle: Record<string, (ack: unknown) => void> = {}
  socket.onEmit('send_message', (payload: { channelId: string }) => {
    return new Promise((resolve) => {
      settle[payload.channelId] = resolve
    })
  })
  return { socket, settle }
}

function renderSend(queryClient: QueryClient, socket: FakeSocket) {
  let channelId = A
  const view = renderHookWithProviders(
    () => useSendMessage(asSocket(socket), WORKSPACE, channelId, ADA),
    { queryClient },
  )
  return {
    ...view,
    moveTo(next: string) {
      channelId = next
      view.rerender()
    },
  }
}

afterEach(() => {
  useAttachmentStore.getState().reset()
})

describe('useSendMessage — a refused send restores its own draft', () => {
  it('puts the refused send back in its own channel while a later send is in flight', async () => {
    const queryClient = seeded()
    const { socket, settle } = heldSocket()
    const { result } = renderSend(queryClient, socket)
    const chipA = aChip({ fileName: 'a.png' })
    const chipB = aChip({ fileName: 'b.png' })

    act(() => result.current.mutate({ channelId: A, body: 'for A', attachments: [chipA] }))
    act(() => result.current.mutate({ channelId: B, body: 'for B', attachments: [chipB] }))
    await vi.waitFor(() => expect(socket.emitted).toHaveLength(2))
    await act(async () => settle[A](REFUSED))

    // A's own text and chips are back in A's composer…
    await vi.waitFor(() => expect(draftOf(A)).toBe('for A'))
    expect(chipsOf(A)).toEqual([chipA])
    expect(errorOf(A)).toBe('An attachment is already on another message.')
    // …and B, whose send is still pending, has been given nothing.
    expect(draftOf(B)).toBeUndefined()
    expect(chipsOf(B)).toEqual([])
    expect(errorOf(B)).toBeNull()
    expect(itemsIn(queryClient, A)).toEqual([])
    expect(itemsIn(queryClient, B)).toHaveLength(1)
    expect(socket.emitted.map((e) => e.args[0])).toEqual([
      { channelId: A, body: 'for A', attachmentIds: [chipA.assetId] },
      { channelId: B, body: 'for B', attachmentIds: [chipB.assetId] },
    ])
  })

  it('cleans up the channel the send was for after the user has moved to another', async () => {
    const kept = aMessage({ channelId: B, body: 'already in B' })
    const queryClient = seeded({ [B]: [kept] })
    const { socket, settle } = heldSocket()
    const { result, moveTo } = renderSend(queryClient, socket)
    const chip = aChip({ fileName: 'a.png' })

    act(() => result.current.mutate({ channelId: A, body: 'for A', attachments: [chip] }))
    await vi.waitFor(() => expect(itemsIn(queryClient, A)).toHaveLength(1))
    // The hook now renders for B, as it does when the user switches channel mid-send.
    moveTo(B)
    await act(async () => settle[A](REFUSED))

    await vi.waitFor(() => expect(draftOf(A)).toBe('for A'))
    expect(chipsOf(A)).toEqual([chip])
    expect(errorOf(A)).toBe('An attachment is already on another message.')
    expect(errorOf(B)).toBeNull()
    // The `temp:` row leaves A's cache; B's cache is exactly as it was.
    expect(itemsIn(queryClient, A)).toEqual([])
    expect(itemsIn(queryClient, B)).toEqual([kept])
  })

  it('writes the confirmed message into the channel it was sent to, not the one on screen', async () => {
    const queryClient = seeded()
    const { socket, settle } = heldSocket()
    const { result, moveTo } = renderSend(queryClient, socket)
    const confirmed = aMessage({ channelId: A, authorId: ADA, body: 'for A' })

    act(() => result.current.mutate({ channelId: A, body: 'for A', attachments: [] }))
    await vi.waitFor(() => expect(itemsIn(queryClient, A)).toHaveLength(1))
    moveTo(B)
    await act(async () => settle[A]({ ok: true, data: confirmed }))

    await vi.waitFor(() => expect(itemsIn(queryClient, A)).toEqual([confirmed]))
    expect(itemsIn(queryClient, B)).toEqual([])
    // A send that worked restores nothing and shows no error.
    expect(draftOf(A)).toBeUndefined()
    expect(chipsOf(A)).toEqual([])
    expect(errorOf(A)).toBeNull()
  })

  it('puts the refused text and chips in front of what was typed since, losing neither', async () => {
    const queryClient = seeded()
    const { socket, settle } = heldSocket()
    const { result } = renderSend(queryClient, socket)
    const typedSince = aChip({ fileName: 'new.png' })
    const [old1, old2] = [aChip({ fileName: 'old-1.png' }), aChip({ fileName: 'old-2.png' })]
    useChatStore.getState().setDraft(A, 'new')
    useAttachmentStore.getState().add(A, typedSince)

    act(() => result.current.mutate({ channelId: A, body: 'old', attachments: [old1, old2] }))
    await vi.waitFor(() => expect(socket.emitted).toHaveLength(1))
    await act(async () => settle[A](REFUSED))

    await vi.waitFor(() => expect(draftOf(A)).toBe('old\nnew'))
    expect(chipsOf(A)).toEqual([old1, old2, typedSince])
  })

  it('gives an empty draft the refused text exactly, with no stray line break', async () => {
    const queryClient = seeded()
    const { socket, settle } = heldSocket()
    const { result } = renderSend(queryClient, socket)

    act(() => result.current.mutate({ channelId: A, body: 'old', attachments: [] }))
    await vi.waitFor(() => expect(socket.emitted).toHaveLength(1))
    await act(async () => settle[A](REFUSED))

    await vi.waitFor(() => expect(draftOf(A)).toBe('old'))
  })

  it('clears a channel’s send error when the next send for that channel starts, and no other’s', async () => {
    const queryClient = seeded()
    const { socket } = heldSocket()
    const { result } = renderSend(queryClient, socket)
    useChatStore.getState().setSendError(A, 'the earlier refusal in A')
    useChatStore.getState().setSendError(B, 'the earlier refusal in B')
    expect(errorOf(A)).toBe('the earlier refusal in A')

    act(() => result.current.mutate({ channelId: A, body: 'trying again', attachments: [] }))
    await vi.waitFor(() => expect(socket.emitted).toHaveLength(1))

    expect(errorOf(A)).toBeNull()
    expect(errorOf(B)).toBe('the earlier refusal in B')
  })
})
