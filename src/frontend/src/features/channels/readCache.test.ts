/**
 * The cache side of reading: what a local read writes, how it is held against
 * a fetch that started before the server moved the marker, and what a receipt
 * from another tab does. Real `QueryClient`, no component.
 */

import type { InfiniteData, QueryClient } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'

import type { Channel, ChannelPage, Message, MessagePage } from '../../lib/api/messaging'
import { aChannel, aMessage, aMessagePage, messageIdAt } from '../../test/factories'
import { createTestQueryClient } from '../../test/render'
import {
  applyReadReceipt,
  cachedLastReadId,
  holdLocalRead,
  writeLocalRead,
  type ReadReceiptEvent,
} from './readCache'
import { channelKeys } from './useChannels'
import { messageKeys } from './useMessages'

const WS = 'workspace-1'
const ME = 'user-ada'
const m = messageIdAt

const general = () => aChannel({ id: 'channel-general', name: 'general' })
const random = () => aChannel({ id: 'channel-random', name: 'random' })

function seed(qc: QueryClient, channels: Channel[], detail: Channel[] = channels) {
  qc.setQueryData<ChannelPage>(channelKeys.list(WS), { items: channels, nextCursor: null })
  for (const channel of detail) qc.setQueryData(channelKeys.detail(WS, channel.id), channel)
}

const inList = (qc: QueryClient, id: string) =>
  qc.getQueryData<ChannelPage>(channelKeys.list(WS))?.items.find((c) => c.id === id)
const inDetail = (qc: QueryClient, id: string) =>
  qc.getQueryData<Channel>(channelKeys.detail(WS, id))

function seedMessages(qc: QueryClient, channelId: string, newestFirst: Message[]) {
  qc.setQueryData<InfiniteData<MessagePage>>(messageKeys.list(WS, channelId), {
    pages: [aMessagePage(newestFirst)],
    pageParams: [undefined],
  })
}

/**
 * A fetch of `key` that has started and not answered. `land` answers it with
 * what the server read *before* the marker moved — the Timing section's t0–t2.
 */
function startFetch(qc: QueryClient, key: readonly unknown[]) {
  let release!: (value: unknown) => void
  const response = new Promise<unknown>((resolve) => {
    release = resolve
  })
  const done = qc.fetchQuery({ queryKey: key, queryFn: () => response, staleTime: 0 })
  return {
    async land(value: unknown) {
      release(value)
      await done
    },
  }
}

const page = (...items: Channel[]): ChannelPage => ({ items, nextCursor: null })

describe('writeLocalRead', () => {
  it('sets the marker and clears the count in the list and the detail', () => {
    const qc = createTestQueryClient()
    seed(qc, [aChannel({ ...general(), unreadCount: 3 })])

    writeLocalRead(qc, WS, 'channel-general', m(5))

    for (const channel of [inList(qc, 'channel-general'), inDetail(qc, 'channel-general')]) {
      expect(channel).toMatchObject({ lastReadId: m(5), unreadCount: 0 })
    }
  })

  it('never moves a marker back', () => {
    const qc = createTestQueryClient()
    const ahead = aChannel({ ...general(), lastReadId: m(9), unreadCount: 2 })
    const behind = aChannel({ ...general(), lastReadId: m(1), unreadCount: 4 })
    // The list entry is ahead of the id written; the detail entry is behind it.
    qc.setQueryData<ChannelPage>(channelKeys.list(WS), page(ahead))
    qc.setQueryData(channelKeys.detail(WS, 'channel-general'), behind)

    writeLocalRead(qc, WS, 'channel-general', m(5))

    expect(inList(qc, 'channel-general')).toMatchObject({ lastReadId: m(9), unreadCount: 2 })
    expect(inDetail(qc, 'channel-general')).toMatchObject({ lastReadId: m(5), unreadCount: 0 })
  })

  it('leaves other channels and absent entries alone', () => {
    const qc = createTestQueryClient()
    const other = aChannel({ ...random(), unreadCount: 7 })
    seed(qc, [aChannel({ ...general(), unreadCount: 3 }), other], [other])

    writeLocalRead(qc, WS, 'channel-general', m(5))

    expect(inList(qc, 'channel-random')).toEqual(other)
    expect(inDetail(qc, 'channel-random')).toEqual(other)
    expect(inList(qc, 'channel-general')).toMatchObject({ lastReadId: m(5), unreadCount: 0 })
    // No detail was cached for `general`, and none appears.
    expect(inDetail(qc, 'channel-general')).toBeUndefined()
  })
})

describe('cachedLastReadId', () => {
  it('reads the further of the list and the detail', () => {
    const qc = createTestQueryClient()
    qc.setQueryData<ChannelPage>(channelKeys.list(WS), page(aChannel({ ...general(), lastReadId: m(7) })))
    qc.setQueryData(channelKeys.detail(WS, 'channel-general'), aChannel({ ...general(), lastReadId: m(3) }))
    expect(cachedLastReadId(qc, WS, 'channel-general')).toBe(m(7))

    qc.setQueryData<ChannelPage>(channelKeys.list(WS), page(aChannel({ ...general(), lastReadId: m(2) })))
    expect(cachedLastReadId(qc, WS, 'channel-general')).toBe(m(3))

    expect(cachedLastReadId(qc, WS, 'channel-random')).toBeNull()
  })
})

describe('holdLocalRead', () => {
  const unread = () => aChannel({ ...general(), unreadCount: 3 })

  it('re-applies the read to a list fetch that lands with the old count', async () => {
    const qc = createTestQueryClient()
    seed(qc, [unread()])
    const fetch = startFetch(qc, channelKeys.list(WS))

    writeLocalRead(qc, WS, 'channel-general', m(5))
    holdLocalRead(qc, WS, 'channel-general', m(5))
    await fetch.land(page(unread()))

    expect(inList(qc, 'channel-general')).toMatchObject({ lastReadId: m(5), unreadCount: 0 })
  })

  it('re-applies the read to a detail fetch that lands with the old count', async () => {
    const qc = createTestQueryClient()
    seed(qc, [unread()])
    const fetch = startFetch(qc, channelKeys.detail(WS, 'channel-general'))

    writeLocalRead(qc, WS, 'channel-general', m(5))
    holdLocalRead(qc, WS, 'channel-general', m(5))
    await fetch.land(unread())

    expect(inDetail(qc, 'channel-general')).toMatchObject({ lastReadId: m(5), unreadCount: 0 })
  })

  it('takes a fetch as it comes after release', async () => {
    const qc = createTestQueryClient()
    seed(qc, [unread()])
    const fetch = startFetch(qc, channelKeys.list(WS))
    writeLocalRead(qc, WS, 'channel-general', m(5))
    const release = holdLocalRead(qc, WS, 'channel-general', m(5))

    release()
    await fetch.land(page(unread()))

    expect(inList(qc, 'channel-general')).toMatchObject({ lastReadId: null, unreadCount: 3 })
  })

  it('leaves a fetch whose marker is already past it', async () => {
    const qc = createTestQueryClient()
    seed(qc, [unread()])
    const fetch = startFetch(qc, channelKeys.list(WS))
    writeLocalRead(qc, WS, 'channel-general', m(2))
    holdLocalRead(qc, WS, 'channel-general', m(2))

    await fetch.land(page(aChannel({ ...general(), lastReadId: m(5), unreadCount: 1 })))

    expect(inList(qc, 'channel-general')).toMatchObject({ lastReadId: m(5), unreadCount: 1 })
  })
})

describe('applyReadReceipt', () => {
  const receipt = (messageId: string, overrides: Partial<ReadReceiptEvent> = {}) => ({
    channelId: 'channel-general',
    userId: ME,
    messageId,
    ...overrides,
  })
  const listInvalidated = (qc: QueryClient) =>
    qc.getQueryState(channelKeys.list(WS))?.isInvalidated

  function seeded() {
    const qc = createTestQueryClient()
    seed(qc, [aChannel({ ...general(), unreadCount: 3 })])
    seedMessages(qc, 'channel-general', [aMessage({ id: m(3) }), aMessage({ id: m(2) })])
    return qc
  }

  it('writes the list and the detail for a receipt at the newest cached message', () => {
    const qc = seeded()

    applyReadReceipt(qc, WS, receipt(m(3)), ME)

    expect(inList(qc, 'channel-general')).toMatchObject({ lastReadId: m(3), unreadCount: 0 })
    expect(inDetail(qc, 'channel-general')).toMatchObject({ lastReadId: m(3), unreadCount: 0 })
    expect(listInvalidated(qc)).toBe(false)
  })

  it('writes the list and the detail for a receipt after it', () => {
    const qc = seeded()

    applyReadReceipt(qc, WS, receipt(m(4)), ME)

    expect(inList(qc, 'channel-general')).toMatchObject({ lastReadId: m(4), unreadCount: 0 })
    expect(inDetail(qc, 'channel-general')).toMatchObject({ lastReadId: m(4), unreadCount: 0 })
    expect(listInvalidated(qc)).toBe(false)
  })

  it('refetches the list for a receipt older than the newest cached message, and writes nothing', () => {
    const qc = seeded()

    applyReadReceipt(qc, WS, receipt(m(2)), ME)

    expect(listInvalidated(qc)).toBe(true)
    expect(inList(qc, 'channel-general')).toMatchObject({ lastReadId: null, unreadCount: 3 })
    expect(inDetail(qc, 'channel-general')).toMatchObject({ lastReadId: null, unreadCount: 3 })
  })

  it('refetches the list for a channel with no cached messages', () => {
    const qc = createTestQueryClient()
    seed(qc, [aChannel({ ...general(), unreadCount: 3 })])

    applyReadReceipt(qc, WS, receipt(m(3)), ME)

    expect(listInvalidated(qc)).toBe(true)
    expect(inList(qc, 'channel-general')).toMatchObject({ lastReadId: null, unreadCount: 3 })
  })

  it('takes the newest cached message to be the newest confirmed one, not a pending send', () => {
    const qc = createTestQueryClient()
    seed(qc, [aChannel({ ...general(), unreadCount: 3 })])
    // `temp:` sorts after every UUIDv7, so counting the pending row would make
    // this receipt look older than the newest message.
    seedMessages(qc, 'channel-general', [
      aMessage({ id: 'temp:0f0f' }),
      aMessage({ id: m(3) }),
      aMessage({ id: m(2) }),
    ])

    applyReadReceipt(qc, WS, receipt(m(3)), ME)

    expect(inList(qc, 'channel-general')).toMatchObject({ lastReadId: m(3), unreadCount: 0 })
    expect(listInvalidated(qc)).toBe(false)
  })

  it('changes nothing for a receipt for another user', () => {
    const qc = seeded()

    applyReadReceipt(qc, WS, receipt(m(3), { userId: 'user-grace' }), ME)

    expect(inList(qc, 'channel-general')).toMatchObject({ lastReadId: null, unreadCount: 3 })
    expect(listInvalidated(qc)).toBe(false)

    // The same receipt for the signed-in user is applied, so the guard above
    // was the user check and not an unrelated no-op.
    applyReadReceipt(qc, WS, receipt(m(3)), ME)
    expect(inList(qc, 'channel-general')).toMatchObject({ lastReadId: m(3), unreadCount: 0 })
  })
})
