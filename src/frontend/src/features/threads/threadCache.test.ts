/**
 * The thread cache writers (R8, R9, decision 28).
 *
 * The cache is the raw `InfiniteData<ThreadPage>`: each page carries the root and
 * its own slice of replies, newest first. A writer replaces by id, adds a reply
 * only to the newest page, and does nothing at all for a thread nobody has open.
 */

import type { InfiniteData, QueryClient } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'

import type { Message, MessagePage, ThreadPage } from '../../lib/api/messaging'
import { aMessage, aMessagePage, aThreadPage } from '../../test/factories'
import { createTestQueryClient } from '../../test/render'
import { messageKeys, type ReactionEvent } from '../channels/useMessages'
import {
  applyThreadReaction,
  applyThreadSummary,
  removeThreadMessage,
  threadKeys,
  upsertThreadMessage,
} from './threadCache'

const WORKSPACE = 'workspace-1'
const CHANNEL = 'channel-1'
const ADA = 'user-ada'
const GRACE = 'user-grace'

const root = aMessage({ channelId: CHANNEL, body: 'who is on call?', replyCount: 5 })
const key = threadKeys.detail(WORKSPACE, CHANNEL, root.id)
const historyKey = messageKeys.list(WORKSPACE, CHANNEL)

function reply(overrides: Partial<Message> = {}): Message {
  return aMessage({ channelId: CHANNEL, threadRootId: root.id, ...overrides })
}

function seeded(...pages: ThreadPage[]): QueryClient {
  const queryClient = createTestQueryClient()
  queryClient.setQueryData<InfiniteData<ThreadPage>>(key, {
    pages,
    pageParams: pages.map(() => undefined),
  })
  return queryClient
}

const pagesIn = (queryClient: QueryClient) =>
  queryClient.getQueryData<InfiniteData<ThreadPage>>(key)?.pages ?? []

const repliesIn = (queryClient: QueryClient) => pagesIn(queryClient).flatMap((page) => page.items)

function reaction(overrides: Partial<ReactionEvent> = {}): ReactionEvent {
  return {
    messageId: 'unset',
    channelId: CHANNEL,
    emoji: 'tada',
    count: 2,
    userId: GRACE,
    reacted: true,
    threadRootId: root.id,
    ...overrides,
  }
}

describe('upsertThreadMessage', () => {
  it('adds an unknown reply to the newest page once, applied twice', () => {
    const older = reply({ body: 'older' })
    const queryClient = seeded(aThreadPage(root, [older], 'c2'), aThreadPage(root, []))
    const arrived = reply({ body: 'arrived' })

    upsertThreadMessage(queryClient, key, arrived)
    upsertThreadMessage(queryClient, key, arrived)

    expect(pagesIn(queryClient)[0].items).toEqual([arrived, older])
    expect(pagesIn(queryClient)[1].items).toEqual([])
    // The cursor belongs to the page; a live reply must not reset it.
    expect(pagesIn(queryClient)[0].nextCursor).toBe('c2')
  })

  it('replaces the root on every page, and adds it to no page’s replies', () => {
    const queryClient = seeded(
      aThreadPage(root, [reply({ body: 'newer' })], 'c2'),
      aThreadPage(root, [reply({ body: 'older' })]),
    )

    upsertThreadMessage(queryClient, key, { ...root, body: 'who is on call this week?' })

    expect(pagesIn(queryClient).map((page) => page.root.body)).toEqual([
      'who is on call this week?',
      'who is on call this week?',
    ])
    expect(repliesIn(queryClient).map((m) => m.body)).toEqual(['newer', 'older'])
  })

  it('replaces a reply where it sits, on whichever page holds it', () => {
    const edited = reply({ body: 'before' })
    const queryClient = seeded(
      aThreadPage(root, [reply({ body: 'newest' })], 'c2'),
      aThreadPage(root, [edited]),
    )

    upsertThreadMessage(queryClient, key, { ...edited, body: 'after' })

    expect(repliesIn(queryClient).map((m) => m.body)).toEqual(['newest', 'after'])
  })

  it('does nothing when the thread is not cached', () => {
    const other = aMessage({ channelId: CHANNEL })
    const otherKey = threadKeys.detail(WORKSPACE, CHANNEL, other.id)
    const queryClient = seeded(aThreadPage(root, []))
    queryClient.setQueryData<InfiniteData<ThreadPage>>(otherKey, {
      pages: [aThreadPage(other, [])],
      pageParams: [undefined],
    })

    upsertThreadMessage(queryClient, threadKeys.detail(WORKSPACE, CHANNEL, 'never-opened'), reply())
    upsertThreadMessage(queryClient, otherKey, reply({ threadRootId: other.id }))

    expect(
      queryClient.getQueryData(threadKeys.detail(WORKSPACE, CHANNEL, 'never-opened')),
    ).toBeUndefined()
    // The cached one took its reply: the silence above is the missing entry.
    expect(queryClient.getQueryData<InfiniteData<ThreadPage>>(otherKey)?.pages[0].items).toHaveLength(
      1,
    )
  })
})

describe('removeThreadMessage', () => {
  it('drops a row from every page and leaves the root', () => {
    const doomed = reply({ body: 'doomed' })
    const kept = reply({ body: 'kept' })
    const queryClient = seeded(aThreadPage(root, [doomed, kept]))

    removeThreadMessage(queryClient, key, doomed.id)

    expect(repliesIn(queryClient)).toEqual([kept])
    expect(pagesIn(queryClient)[0].root).toEqual(root)
  })
})

describe('applyThreadSummary', () => {
  const event = (overrides: Partial<{ replyCount: number; lastReplyAt: string | null }> = {}) => ({
    channelId: CHANNEL,
    rootId: root.id,
    replyCount: 2,
    lastReplyAt: '2026-09-15T10:00:00Z',
    ...overrides,
  })

  it('sets a summary in history and the open thread — root at 5, event 2, reads 2', () => {
    const queryClient = seeded(aThreadPage(root, []))
    queryClient.setQueryData<InfiniteData<MessagePage>>(
      historyKey,
      { pages: [aMessagePage([root])], pageParams: [undefined] },
    )

    applyThreadSummary(queryClient, WORKSPACE, event())
    applyThreadSummary(queryClient, WORKSPACE, event())

    const inHistory = queryClient.getQueryData<InfiniteData<MessagePage>>(historyKey)
      ?.pages[0].items[0]
    expect(inHistory).toMatchObject({ replyCount: 2, lastReplyAt: '2026-09-15T10:00:00Z' })
    expect(pagesIn(queryClient)[0].root).toMatchObject({
      replyCount: 2,
      lastReplyAt: '2026-09-15T10:00:00Z',
    })
  })

  it('goes down as well as up, and back to none', () => {
    const queryClient = seeded(aThreadPage(root, []))

    applyThreadSummary(queryClient, WORKSPACE, event({ replyCount: 0, lastReplyAt: null }))

    expect(pagesIn(queryClient)[0].root).toMatchObject({ replyCount: 0, lastReplyAt: null })
  })

  it('a summary for a root not in history leaves history unchanged', () => {
    // Decision 28: the panel works on a root nobody loaded into history.
    const other = aMessage({ channelId: CHANNEL, body: 'the only thing in history' })
    const queryClient = seeded(aThreadPage(root, []))
    queryClient.setQueryData(historyKey, {
      pages: [aMessagePage([other])],
      pageParams: [undefined],
    })

    applyThreadSummary(queryClient, WORKSPACE, event())

    const items = queryClient.getQueryData<InfiniteData<{ items: Message[] }>>(historyKey)?.pages[0]
      .items
    expect(items).toEqual([other])
    // The open thread's root is updated in the same call.
    expect(pagesIn(queryClient)[0].root.replyCount).toBe(2)
  })
})

describe('applyThreadReaction', () => {
  it('applies a reply’s reaction, lit for the actor only', () => {
    const answer = reply({ body: 'I am' })
    const queryClient = seeded(aThreadPage(root, [answer]))

    applyThreadReaction(queryClient, key, reaction({ messageId: answer.id }), ADA)
    applyThreadReaction(queryClient, key, reaction({ messageId: answer.id }), ADA)

    expect(repliesIn(queryClient)[0].reactions).toEqual([{ emoji: 'tada', count: 2, reacted: false }])

    applyThreadReaction(
      queryClient,
      key,
      reaction({ messageId: answer.id, userId: ADA, count: 3, reacted: true }),
      ADA,
    )

    expect(repliesIn(queryClient)[0].reactions).toEqual([{ emoji: 'tada', count: 3, reacted: true }])
  })

  it('applies a reaction on the root to the root on every page', () => {
    const queryClient = seeded(aThreadPage(root, [reply()], 'c2'), aThreadPage(root, [reply()]))

    applyThreadReaction(queryClient, key, reaction({ messageId: root.id, threadRootId: null }), ADA)

    expect(pagesIn(queryClient).map((page) => page.root.reactions)).toEqual([
      [{ emoji: 'tada', count: 2, reacted: false }],
      [{ emoji: 'tada', count: 2, reacted: false }],
    ])
  })
})
