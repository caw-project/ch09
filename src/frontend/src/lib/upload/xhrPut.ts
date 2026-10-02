/**
 * The presigned PUT to object storage, over XHR because `fetch` cannot report
 * upload progress.
 *
 * Every failure is the same `Error('Upload failed')`: a non-2xx answer and a
 * network error alike. A refused PUT (wrong `Content-Type`, an expired URL, a
 * CORS rule that does not allow this origin) reaches the page as an XHR error
 * with no status — Garage adds its CORS headers to successful answers only — so
 * there is nothing finer to say, and the chip says "Upload failed".
 *
 * **Abort rejects from the signal's own listener.** `xhr.abort()` is called too,
 * to stop the request, but the rejection does not wait for `onabort`: a caller
 * that cancelled must be unblocked even where the XHR implementation never
 * fires it (MSW's does not for a held request).
 */

interface PutOptions {
  url: string
  file: File
  /** The headers the presigned URL was signed with — the `Content-Type` above all. */
  headers: Record<string, string>
  /** A fraction from 0 to 1. */
  onProgress: (fraction: number) => void
  signal: AbortSignal
}

const FAILED = 'Upload failed'

export function putFile({ url, file, headers, onProgress, signal }: PutOptions): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    if (signal.aborted) {
      reject(new Error(FAILED))
      return
    }

    const xhr = new XMLHttpRequest()
    let settled = false
    const settle = (finish: () => void) => {
      if (settled) return
      settled = true
      signal.removeEventListener('abort', onAbort)
      finish()
    }
    const fail = () => settle(() => reject(new Error(FAILED)))
    const onAbort = () => {
      xhr.abort()
      fail()
    }

    xhr.open('PUT', url)
    for (const [name, value] of Object.entries(headers)) xhr.setRequestHeader(name, value)

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) onProgress(event.loaded / event.total)
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        settle(() => {
          onProgress(1)
          resolve()
        })
      } else {
        fail()
      }
    }
    xhr.onerror = fail
    xhr.onabort = fail
    xhr.ontimeout = fail

    signal.addEventListener('abort', onAbort)
    xhr.send(file)
  })
}
