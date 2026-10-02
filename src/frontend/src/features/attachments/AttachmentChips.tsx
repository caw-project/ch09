/**
 * The files waiting in a composer, one chip each, with their progress and a ✕.
 *
 * ✕ is `cancel` then `remove`: on a chip that is still uploading it stops the
 * upload (nothing further is requested) as well as taking the chip away. The
 * `data-testid`s belong to the acceptance suite, which waits on `data-status`.
 */

import { useAttachmentStore, type Chip } from '../../stores/attachments'
import { formatBytes } from './format'
import { cancel } from './uploads'

interface Props {
  channelId: string
  chips: Chip[]
}

export function AttachmentChips({ channelId, chips }: Props) {
  const remove = useAttachmentStore((state) => state.remove)
  if (chips.length === 0) return null

  return (
    <ul className="flex flex-wrap gap-2">
      {chips.map((chip) => (
        <li
          key={chip.localId}
          data-testid="attachment-chip"
          data-file-name={chip.fileName}
          data-status={chip.status}
          className={`flex max-w-64 flex-col rounded border px-2 py-1 text-xs ${
            chip.status === 'failed' ? 'border-danger text-danger' : 'border-border text-ink'
          }`}
        >
          <span className="flex items-center gap-2">
            <span className="min-w-0 flex-1 truncate">{chip.fileName}</span>
            <span className="text-ink-muted">{formatBytes(chip.sizeBytes)}</span>
            <button
              type="button"
              aria-label={`Remove ${chip.fileName}`}
              onClick={() => {
                cancel(chip.localId)
                remove(channelId, chip.localId)
              }}
              className="text-ink-muted hover:text-ink"
            >
              ✕
            </button>
          </span>

          {chip.status === 'uploading' && (
            <progress
              value={chip.progress}
              max={1}
              aria-label={`Uploading ${chip.fileName}`}
              className="h-1 w-full"
            />
          )}
          {chip.status === 'failed' && chip.error && <span>{chip.error}</span>}
        </li>
      ))}
    </ul>
  )
}
