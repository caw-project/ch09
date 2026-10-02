/**
 * The upload runner (issue 4 R2, R4, R5, R15): `upload-url` → PUT → `confirm` for
 * each file, **outside React**.
 *
 * Nothing in a component owns an upload. A hook would die with its component, and
 * a channel switch unmounts the composer; a file the user chose in #general has to
 * finish into #general's chips whatever they are looking at. So the runner writes
 * to the chip store directly, by chip id.
 *
 * Three awaited steps mean a ✕ or a workspace switch can land between any two,
 * so each upload has an `AbortController`. `uploads.ts` checks its signal before
 * each step and hands it to each request: after a cancel nothing further is
 * requested, and nothing is written (the store ignores a chip that has gone, as a
 * second line). The asset stays `pending` in Asset — nothing sweeps it
 * (register D16).
 *
 * The token is asked for before *each* step rather than once: a long upload can
 * outlive a 15-minute access token, and the refresh rotates it.
 */

import { confirmUpload, requestUploadUrl } from '../../lib/api/asset'
import { describeError } from '../../lib/api/client'
import { putFile } from '../../lib/upload/xhrPut'
import { useAttachmentStore, type Chip } from '../../stores/attachments'
import { batchRefusal, checkFile } from './rules'

/** One per upload in flight, so ✕ and a workspace switch can stop exactly what they mean to. */
const running = new Map<string, AbortController>()

/**
 * Attach files to a channel's composer.
 *
 * Returns why the batch was refused, or `null`. The count is **all or none**: a
 * batch that would pass ten adds nothing. A file that breaks a per-file rule is
 * not refused with the batch — it becomes a `failed` chip saying why, counts
 * towards ten until removed, and is never uploaded (decision 28).
 */
export function addFiles(
  channelId: string,
  files: File[],
  getToken: () => string,
): string | null {
  const attached = useAttachmentStore.getState().chips[channelId]?.length ?? 0
  const refusal = batchRefusal(attached, files.length)
  if (refusal !== null) return refusal

  for (const file of files) {
    const rule = checkFile(file)
    const chip: Chip = {
      localId: crypto.randomUUID(),
      fileName: file.name,
      contentType: file.type,
      sizeBytes: file.size,
      status: rule === null ? 'uploading' : 'failed',
      progress: 0,
      assetId: null,
      error: rule,
    }
    useAttachmentStore.getState().add(channelId, chip)
    if (rule === null) start(chip.localId, file, getToken)
  }
  return null
}

/** Stop one upload: nothing further is requested, and nothing is written for it. */
export function cancel(localId: string): void {
  running.get(localId)?.abort()
  running.delete(localId)
}

/** Stop every upload — a workspace switch, or the shell going away. */
export function cancelAll(): void {
  for (const controller of running.values()) controller.abort()
  running.clear()
}

function start(localId: string, file: File, getToken: () => string): void {
  const controller = new AbortController()
  running.set(localId, controller)
  void run(localId, file, getToken, controller).finally(() => {
    // Only if it is still this run's: a cancel has already removed it.
    if (running.get(localId) === controller) running.delete(localId)
  })
}

async function run(
  localId: string,
  file: File,
  getToken: () => string,
  { signal }: AbortController,
): Promise<void> {
  const chips = useAttachmentStore.getState()
  try {
    const upload = await requestUploadUrl(
      getToken(),
      { fileName: file.name, contentType: file.type, sizeBytes: file.size },
      signal,
    )
    if (signal.aborted) return

    await putFile({
      url: upload.uploadUrl,
      file,
      headers: upload.headers,
      onProgress: (progress) => {
        if (!signal.aborted) chips.update(localId, { progress })
      },
      signal,
    })
    if (signal.aborted) return

    const confirmed = await confirmUpload(getToken(), upload.assetId, signal)
    if (signal.aborted) return

    if (confirmed.status === 'ready') {
      chips.update(localId, { status: 'ready', progress: 1, assetId: confirmed.id, error: null })
    } else {
      chips.update(localId, {
        status: 'failed',
        error: confirmed.failureReason ?? 'The upload could not be confirmed.',
      })
    }
  } catch (error) {
    if (signal.aborted) return
    chips.update(localId, { status: 'failed', error: describeError(error) })
  }
}
