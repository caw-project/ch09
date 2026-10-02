/**
 * The presigned PUT, over XHR because `fetch` cannot report upload progress.
 *
 * MSW's XHR interceptor fires `upload` progress events for a request with a
 * body, so the progress callback is exercised without a network.
 */

import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'

import { garage, GARAGE_URL, requests, server } from '../../test/api'
import { putFile } from './xhrPut'

const URL = `${GARAGE_URL}/collabhub-assets/asset-1`

function png(bytes = 2048) {
  return new File([new Uint8Array(bytes)], 'diagram.png', { type: 'image/png' })
}

describe('putFile', () => {
  it('sends the signed Content-Type and the bytes, reports progress, then resolves', async () => {
    garage.put()
    const progress: number[] = []

    await putFile({
      url: URL,
      file: png(2048),
      headers: { 'Content-Type': 'image/png' },
      onProgress: (fraction) => progress.push(fraction),
      signal: new AbortController().signal,
    })

    expect(requests()).toHaveLength(1)
    expect(requests()[0].method).toBe('PUT')
    expect(requests()[0].contentType).toBe('image/png')
    // MSW's XHR double reports a streamed `File` as a few bytes of "[object File]",
    // so the byte count cannot be asserted: only that a body was sent.
    expect((requests()[0].body as { size: number }).size).toBeGreaterThan(0)
    expect(progress.length).toBeGreaterThan(0)
    expect(progress.every((fraction) => fraction >= 0 && fraction <= 1)).toBe(true)
    expect(progress.at(-1)).toBe(1)
  })

  it('rejects with “Upload failed” on a non-2xx answer', async () => {
    garage.put(403)

    await expect(
      putFile({
        url: URL,
        file: png(),
        headers: { 'Content-Type': 'image/png' },
        onProgress: () => undefined,
        signal: new AbortController().signal,
      }),
    ).rejects.toThrow('Upload failed')
  })

  it('rejects with “Upload failed” on a network error, which is all a refused PUT looks like', async () => {
    // Garage adds CORS headers to successful answers only, so a refusal reaches
    // the page as an error with no status.
    garage.putFails()

    await expect(
      putFile({
        url: URL,
        file: png(),
        headers: { 'Content-Type': 'image/png' },
        onProgress: () => undefined,
        signal: new AbortController().signal,
      }),
    ).rejects.toThrow('Upload failed')
  })

  it('rejects when aborted, and the request is not left running', async () => {
    let release!: () => void
    const held = new Promise<void>((resolve) => {
      release = resolve
    })
    server.use(
      http.put(`${GARAGE_URL}/*`, async () => {
        await held
        return new HttpResponse(null, { status: 200 })
      }),
    )
    const controller = new AbortController()
    const onProgress = vi.fn()

    const result = putFile({
      url: URL,
      file: png(),
      headers: { 'Content-Type': 'image/png' },
      onProgress,
      signal: controller.signal,
    })
    const rejected = expect(result).rejects.toThrow()
    // Under MSW a held request never fires `xhr.onabort`: `putFile` must reject
    // directly from the signal's abort listener (and call `xhr.abort()`).
    controller.abort()

    await rejected
    release()
  })

  it('rejects at once when the signal is already aborted', async () => {
    garage.put()
    const controller = new AbortController()
    controller.abort()

    await expect(
      putFile({
        url: URL,
        file: png(),
        headers: { 'Content-Type': 'image/png' },
        onProgress: () => undefined,
        signal: controller.signal,
      }),
    ).rejects.toThrow()

    expect(requests()).toEqual([])
  })
})
