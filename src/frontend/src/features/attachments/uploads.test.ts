/**
 * The upload runner (issue 4 R2, R4, R5, R15): upload-url → PUT → confirm, outside
 * React, so a channel switch cannot stop it and nothing in a component owns it.
 *
 * MSW answers all three steps (`asset.acceptUploads`), and a step can be held, so
 * a test can look at — or cancel — an upload *between* two of them. Every "nothing
 * happened after the cancel" test is paired with the same held step released with
 * no cancel, which ends `ready`: without that half, nothing proves the late write
 * would have happened.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import { useChatStore } from '../../stores/chat'
import { useAttachmentStore } from '../../stores/attachments'
import { asset, requests } from '../../test/api'
import { addFiles, cancel, cancelAll } from './uploads'

const A = 'channel-a'
const B = 'channel-b'
const token = () => 'token'

const chips = (channelId: string) => useAttachmentStore.getState().chips[channelId] ?? []
const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

function png(name = 'diagram.png', bytes = 100) {
  return new File([new Uint8Array(bytes)], name, { type: 'image/png' })
}

function deferred() {
  let release!: () => void
  const promise = new Promise<void>((resolve) => {
    release = resolve
  })
  return { promise, release }
}

const calls = () => requests().map((r) => `${r.method} ${r.url.pathname}`)
const confirms = () => requests().filter((r) => r.url.pathname.endsWith('/confirm'))
const puts = () => requests().filter((r) => r.method === 'PUT')

afterEach(() => {
  cancelAll()
  useAttachmentStore.getState().reset()
})

describe('addFiles', () => {
  it('runs a file through upload-url, the PUT and confirm, and ends ready with its asset id', async () => {
    asset.acceptUploads()

    const refusal = addFiles(A, [png('diagram.png', 100)], token)

    expect(refusal).toBeNull()
    expect(chips(A)).toHaveLength(1)
    expect(chips(A)[0]).toMatchObject({ fileName: 'diagram.png', contentType: 'image/png', sizeBytes: 100 })
    await vi.waitFor(() => expect(chips(A)[0].status).toBe('ready'))
    expect(chips(A)[0].assetId).toBe('asset-diagram.png')
    expect(chips(A)[0].progress).toBe(1)
    expect(calls()).toEqual([
      'POST /api/v1/assets/upload-url',
      'PUT /collabhub-assets/asset-diagram.png',
      'POST /api/v1/assets/asset-diagram.png/confirm',
    ])
    expect(requests()[0].body).toEqual({
      fileName: 'diagram.png',
      contentType: 'image/png',
      sizeBytes: 100,
      purpose: 'attachment',
    })
    // The XHR double can't report the real byte count (see xhrPut.test.ts): a body was PUT.
    expect((requests()[1].body as { size: number }).size).toBeGreaterThan(0)
  })

  it('shows a chip as uploading, with no asset id, until confirm lands', async () => {
    const gate = deferred()
    asset.acceptUploads({ hold: { confirm: gate.promise } })

    addFiles(A, [png()], token)
    await vi.waitFor(() => expect(confirms()).toHaveLength(1))

    expect(chips(A)[0].status).toBe('uploading')
    expect(chips(A)[0].assetId).toBeNull()

    gate.release()
    await vi.waitFor(() => expect(chips(A)[0].status).toBe('ready'))
  })

  it('shows the reason when confirm answers failed', async () => {
    asset.acceptUploads({
      confirmAs: { status: 'failed', failureReason: 'The upload did not arrive.' },
    })

    addFiles(A, [png()], token)

    await vi.waitFor(() => expect(chips(A)[0].status).toBe('failed'))
    expect(chips(A)[0].error).toBe('The upload did not arrive.')
  })

  it('makes a file that breaks a rule a failed chip with the reason, and never requests it', async () => {
    asset.acceptUploads()
    const svg = new File(['<svg/>'], 'logo.svg', { type: 'image/svg+xml' })

    const refusal = addFiles(A, [svg, png('fine.png')], token)

    // The rule file is a chip (decision 28), and refuses nothing about the batch.
    expect(refusal).toBeNull()
    expect(chips(A).map((c) => [c.fileName, c.status])).toEqual([
      ['logo.svg', 'failed'],
      ['fine.png', 'uploading'],
    ])
    expect(chips(A)[0].error).toBe('Only images (PNG, JPEG, GIF, WebP) and PDFs can be attached.')
    // The positive half: the valid file beside it does go through all three steps.
    await vi.waitFor(() => expect(chips(A)[1].status).toBe('ready'))
    expect(calls().filter((c) => c.includes('logo.svg'))).toEqual([])
    expect(requests().filter((r) => r.method === 'POST' && r.url.pathname.endsWith('upload-url'))).toHaveLength(1)
  })

  it('refuses the whole batch when it would pass ten, and adds none of it', async () => {
    asset.acceptUploads()
    const eleven = Array.from({ length: 11 }, (_, n) => png(`file-${n}.png`))

    const refusal = addFiles(A, eleven, token)

    expect(refusal).toBe('At most 10 files per message — 0 attached, 11 added.')
    expect(chips(A)).toEqual([])
    await sleep(50)
    expect(requests()).toEqual([])
  })

  it('accepts a batch of exactly ten', async () => {
    asset.acceptUploads()
    const ten = Array.from({ length: 10 }, (_, n) => png(`file-${n}.png`))

    expect(addFiles(A, ten, token)).toBeNull()

    expect(chips(A)).toHaveLength(10)
    await vi.waitFor(() => expect(chips(A).every((c) => c.status === 'ready')).toBe(true))
  })

  it('counts a failed chip towards ten, and makes room when it is removed', async () => {
    asset.acceptUploads()
    const svg = new File(['<svg/>'], 'logo.svg', { type: 'image/svg+xml' })
    addFiles(A, [svg], token)
    addFiles(A, Array.from({ length: 9 }, (_, n) => png(`file-${n}.png`)), token)
    expect(chips(A)).toHaveLength(10)

    expect(addFiles(A, [png('one-more.png')], token)).toBe(
      'At most 10 files per message — 10 attached, 1 added.',
    )
    expect(chips(A)).toHaveLength(10)

    useAttachmentStore.getState().remove(A, chips(A)[0].localId)

    expect(addFiles(A, [png('one-more.png')], token)).toBeNull()
    expect(chips(A)).toHaveLength(10)
    expect(chips(A).at(-1)?.fileName).toBe('one-more.png')
  })

  it('counts the chips of the channel it is for, not another’s', () => {
    asset.acceptUploads()
    addFiles(A, Array.from({ length: 10 }, (_, n) => png(`a-${n}.png`)), token)

    expect(addFiles(B, [png('b.png')], token)).toBeNull()
    expect(chips(B)).toHaveLength(1)
  })

  it('finishes an upload into the channel it started in after the user has moved on', async () => {
    const gate = deferred()
    asset.acceptUploads({ hold: { confirm: gate.promise } })
    useChatStore.getState().setActiveChannel(A)
    addFiles(A, [png()], token)
    await vi.waitFor(() => expect(confirms()).toHaveLength(1))

    useChatStore.getState().setActiveChannel(B)
    gate.release()

    await vi.waitFor(() => expect(chips(A)[0].status).toBe('ready'))
    expect(chips(B)).toEqual([])
  })
})

describe('cancel and reset (decision 37)', () => {
  it('requests nothing further once cancelled while upload-url is held', async () => {
    const gate = deferred()
    asset.acceptUploads({ hold: { uploadUrl: gate.promise } })
    addFiles(A, [png()], token)
    await vi.waitFor(() => expect(requests()).toHaveLength(1))
    const { localId } = chips(A)[0]

    // What ✕ on an uploading chip does: cancel, then remove.
    cancel(localId)
    useAttachmentStore.getState().remove(A, localId)
    gate.release()
    await sleep(150)

    expect(chips(A)).toEqual([])
    expect(puts()).toEqual([])
    expect(confirms()).toEqual([])
  })

  it('carries on past the same held step when nobody cancels', async () => {
    const gate = deferred()
    asset.acceptUploads({ hold: { uploadUrl: gate.promise } })
    addFiles(A, [png()], token)
    await vi.waitFor(() => expect(requests()).toHaveLength(1))

    gate.release()

    await vi.waitFor(() => expect(chips(A)[0]?.status).toBe('ready'))
    expect(puts()).toHaveLength(1)
    expect(confirms()).toHaveLength(1)
  })

  it('writes nothing after a reset while confirm is held', async () => {
    const gate = deferred()
    asset.acceptUploads({ hold: { confirm: gate.promise } })
    addFiles(A, [png()], token)
    await vi.waitFor(() => expect(confirms()).toHaveLength(1))

    // The workspace switch: abort what is running, then empty the store.
    cancelAll()
    useAttachmentStore.getState().reset()
    gate.release()
    await sleep(150)

    expect(useAttachmentStore.getState().chips).toEqual({})
  })

  it('writes the same held confirm into the chip when nothing is reset', async () => {
    const gate = deferred()
    asset.acceptUploads({ hold: { confirm: gate.promise } })
    addFiles(A, [png()], token)
    await vi.waitFor(() => expect(confirms()).toHaveLength(1))

    gate.release()

    await vi.waitFor(() => expect(chips(A)[0]?.status).toBe('ready'))
  })

  it('does not start the PUT for an upload cancelled before the PUT began', async () => {
    const gate = deferred()
    asset.acceptUploads({ hold: { uploadUrl: gate.promise } })
    addFiles(A, [png('first.png'), png('second.png')], token)
    await vi.waitFor(() => expect(requests()).toHaveLength(2))
    const [first, second] = chips(A)

    cancel(first.localId)
    useAttachmentStore.getState().remove(A, first.localId)
    gate.release()

    // The other upload, from the same batch and the same held step, is unaffected.
    await vi.waitFor(() => expect(chips(A).find((c) => c.localId === second.localId)?.status).toBe('ready'))
    expect(puts().map((r) => r.url.pathname)).toEqual(['/collabhub-assets/asset-second.png'])
  })
})
