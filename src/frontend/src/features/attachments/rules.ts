/**
 * The client-side upload rules (issue 4 R2–R4), checked before any upload starts
 * and worded as the server words them, so the person reads which rule refused.
 *
 * The server checks the same limits again at `upload-url` (`asset/rules.py`): a
 * second copy of a limit is only safe because it is a copy, and both are tested
 * against the same literals. The client's copy is for a fast, friendly answer,
 * never for authority.
 */

export const MAX_FILES = 10
/** 50 MiB, the server's `ASSET_MAX_UPLOAD_BYTES`; the message says "50 MB". */
export const MAX_FILE_BYTES = 52_428_800
export const MAX_NAME_CHARS = 255

/** Exactly these, compared whole. No SVG: it runs script when opened (register D15). */
export const ALLOWED_TYPES = [
  'image/png',
  'image/jpeg',
  'image/gif',
  'image/webp',
  'application/pdf',
] as const

/** The browser's generic name for a pasted screenshot. */
const GENERIC_PASTE_NAME = 'image.png'

export function checkFile(file: { name: string; size: number; type: string }): string | null {
  if (!(ALLOWED_TYPES as readonly string[]).includes(file.type)) {
    return 'Only images (PNG, JPEG, GIF, WebP) and PDFs can be attached.'
  }
  if (file.size < 1) return 'This file is empty.'
  if (file.size > MAX_FILE_BYTES) return 'Files must be 50 MB or smaller.'
  if (file.name.length < 1 || file.name.length > MAX_NAME_CHARS) {
    return 'File names must be 1 to 255 characters.'
  }
  return null
}

/**
 * Why a batch cannot be added, or `null`. All or none: a batch that would take the
 * message past ten is refused whole, so nobody has to guess which files got in.
 */
export function batchRefusal(attached: number, added: number): string | null {
  if (attached + added <= MAX_FILES) return null
  return `At most ${MAX_FILES} files per message — ${attached} attached, ${added} added.`
}

const pad = (n: number) => String(n).padStart(2, '0')

/** `Pasted image 2026-03-04 09.05.07.png`, in local time — a name that sorts and has no colons. */
export function pastedName(date: Date): string {
  const day = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
  const time = `${pad(date.getHours())}.${pad(date.getMinutes())}.${pad(date.getSeconds())}`
  return `Pasted image ${day} ${time}.png`
}

/**
 * The files to attach from a paste, or `null` to let the browser paste as usual.
 *
 * Text on the clipboard wins: Excel and Word put an image of the selection beside
 * the text, and attaching that would surprise everyone. Only a clipboard with
 * files and no text attaches. Only the browser's generic `image.png` is renamed —
 * a Finder file keeps its own name, and a JPEG is never relabelled `.png`.
 */
export function filesFromPaste(data: DataTransfer): File[] | null {
  const files = Array.from(data.files)
  if (files.length === 0) return null
  if (data.getData('text') !== '') return null

  const now = new Date()
  return files.map((file) =>
    file.name === GENERIC_PASTE_NAME && file.type === 'image/png'
      ? new File([file], pastedName(now), { type: file.type })
      : file,
  )
}
