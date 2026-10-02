/**
 * The composer's chips — client state (register D24), keyed by channel so an
 * upload belongs to the draft it was started in (issue 4 R15).
 *
 * The two rules that are easy to get wrong are here: a late write to a chip that
 * is gone is a no-op (decision 37), and restoring a refused send never drops what
 * is already attached (decision 33).
 */

import { afterEach, describe, expect, it } from 'vitest'

import { aChip } from '../test/factories'
import { useAttachmentStore } from './attachments'

const A = 'channel-a'
const B = 'channel-b'

const store = () => useAttachmentStore.getState()
const names = (channelId: string) => (store().chips[channelId] ?? []).map((c) => c.fileName)

afterEach(() => store().reset())

describe('the attachment store', () => {
  it('keeps chips per channel, in the order they were added', () => {
    store().add(A, aChip({ fileName: 'one.png' }))
    store().add(A, aChip({ fileName: 'two.png' }))
    store().add(B, aChip({ fileName: 'other.png' }))

    expect(names(A)).toEqual(['one.png', 'two.png'])
    expect(names(B)).toEqual(['other.png'])
  })

  it('patches a known chip and nothing else', () => {
    const uploading = aChip({ localId: 'u1', status: 'uploading', progress: 0.2, assetId: null })
    const bystander = aChip({ localId: 'u2', status: 'uploading', progress: 0.2, assetId: null })
    store().add(A, uploading)
    store().add(A, bystander)

    store().update('u1', { status: 'ready', progress: 1, assetId: 'asset-1' })

    const [first, second] = store().chips[A]
    expect(first).toMatchObject({ status: 'ready', progress: 1, assetId: 'asset-1' })
    expect(second).toEqual(bystander)
  })

  it('ignores an update for a chip that is no longer there', () => {
    // A ✕ or a workspace switch can land between an upload's three steps; the
    // step that finishes later must not bring the chip back or write anywhere.
    store().add(A, aChip({ localId: 'kept' }))
    const before = store().chips

    store().update('gone', { status: 'ready' })

    expect(store().chips).toEqual(before)
    expect(Object.keys(store().chips)).toEqual([A])
  })

  it('removes one chip from one channel', () => {
    store().add(A, aChip({ localId: 'x', fileName: 'x.png' }))
    store().add(A, aChip({ localId: 'y', fileName: 'y.png' }))
    store().add(B, aChip({ localId: 'x2', fileName: 'x.png' }))

    store().remove(A, 'x')

    expect(names(A)).toEqual(['y.png'])
    expect(names(B)).toEqual(['x.png'])
  })

  it('puts restored chips before the current ones', () => {
    store().add(A, aChip({ fileName: 'new.png' }))

    store().restore(A, [aChip({ fileName: 'old-1.png' }), aChip({ fileName: 'old-2.png' })])

    expect(names(A)).toEqual(['old-1.png', 'old-2.png', 'new.png'])
  })

  it('keeps every chip when a restore takes a channel past ten', () => {
    // 8 restored meet 3 current: eleven, and none of them is dropped.
    for (let n = 0; n < 3; n++) store().add(A, aChip({ fileName: `current-${n}.png` }))

    store().restore(
      A,
      Array.from({ length: 8 }, (_, n) => aChip({ fileName: `restored-${n}.png` })),
    )

    expect(store().chips[A]).toHaveLength(11)
    expect(names(A).slice(0, 8)).toEqual(Array.from({ length: 8 }, (_, n) => `restored-${n}.png`))
    expect(names(A).slice(8)).toEqual(['current-0.png', 'current-1.png', 'current-2.png'])
  })

  it('restores into a channel that has no chips', () => {
    store().restore(A, [aChip({ fileName: 'only.png' })])

    expect(names(A)).toEqual(['only.png'])
  })

  it('clears one channel, and reset clears them all', () => {
    store().add(A, aChip())
    store().add(B, aChip())

    store().clear(A)
    expect(names(A)).toEqual([])
    expect(names(B)).toHaveLength(1)

    store().reset()
    expect(store().chips).toEqual({})
  })
})
