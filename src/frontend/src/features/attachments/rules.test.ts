/**
 * The client-side upload rules (issue 4 R2–R4): checked before any upload starts,
 * in the server's own words, so the person reads which rule refused. The server
 * checks the same limits again at `upload-url` (`test_rules.py`); a second copy
 * of a limit is only safe because both are tested against the same literals.
 *
 * Every limit is a literal here, not the module's constant: an import that does
 * not exist yet is `undefined`, and a bound built from it would be `NaN`.
 */

import { describe, expect, it } from 'vitest'

import { batchRefusal, checkFile, filesFromPaste, pastedName } from './rules'

const MAX = 52_428_800

function file(overrides: Partial<{ name: string; size: number; type: string }> = {}) {
  return { name: 'diagram.png', size: 1000, type: 'image/png', ...overrides }
}

describe('checkFile', () => {
  it.each(['image/png', 'image/jpeg', 'image/gif', 'image/webp', 'application/pdf'])(
    'accepts %s',
    (type) => {
      expect(checkFile(file({ type }))).toBeNull()
    },
  )

  it('refuses SVG, which runs script when opened, naming the allowed types', () => {
    expect(checkFile(file({ name: 'logo.svg', type: 'image/svg+xml' }))).toBe(
      'Only images (PNG, JPEG, GIF, WebP) and PDFs can be attached.',
    )
  })

  it('matches the type exactly, so a parameter does not slip through', () => {
    expect(checkFile(file({ type: 'image/png; x=1' }))).toBe(
      'Only images (PNG, JPEG, GIF, WebP) and PDFs can be attached.',
    )
  })

  it('accepts 50 MiB exactly and refuses one byte more', () => {
    expect(checkFile(file({ size: MAX }))).toBeNull()
    expect(checkFile(file({ size: MAX + 1 }))).toBe('Files must be 50 MB or smaller.')
  })

  it('refuses an empty file and accepts a one-byte file', () => {
    expect(checkFile(file({ size: 0 }))).toBe('This file is empty.')
    expect(checkFile(file({ size: 1 }))).toBeNull()
  })

  it('accepts a 255-character name and refuses 256', () => {
    expect(checkFile(file({ name: 'a'.repeat(255) }))).toBeNull()
    expect(checkFile(file({ name: 'a'.repeat(256) }))).toBe('File names must be 1 to 255 characters.')
  })

  it('refuses an empty name', () => {
    expect(checkFile(file({ name: '' }))).toBe('File names must be 1 to 255 characters.')
  })
})

describe('batchRefusal', () => {
  it('takes a batch that brings the message to exactly ten', () => {
    expect(batchRefusal(3, 7)).toBeNull()
    expect(batchRefusal(0, 10)).toBeNull()
  })

  it('refuses a batch that goes over, saying how many were there and how many were added', () => {
    expect(batchRefusal(3, 8)).toBe('At most 10 files per message — 3 attached, 8 added.')
    expect(batchRefusal(0, 11)).toBe('At most 10 files per message — 0 attached, 11 added.')
    expect(batchRefusal(10, 1)).toBe('At most 10 files per message — 10 attached, 1 added.')
  })
})

describe('pastedName', () => {
  it('pads every field, in local time', () => {
    expect(pastedName(new Date(2026, 2, 4, 9, 5, 7))).toBe('Pasted image 2026-03-04 09.05.07.png')
  })

  it('leaves two-digit fields alone', () => {
    expect(pastedName(new Date(2026, 10, 14, 13, 45, 56))).toBe(
      'Pasted image 2026-11-14 13.45.56.png',
    )
  })
})

describe('filesFromPaste', () => {
  /** What a browser hands a paste handler — enough for the code to read, and nothing it would not. */
  function clipboard(files: File[], text = ''): DataTransfer {
    const types = [...(text ? ['text/plain'] : []), ...(files.length ? ['Files'] : [])]
    const list = Object.assign([...files], { item: (n: number) => files[n] ?? null })
    return {
      types,
      files: list,
      getData: (format: string) => (format === 'text' || format === 'text/plain' ? text : ''),
    } as unknown as DataTransfer
  }

  const png = () => new File(['x'], 'image.png', { type: 'image/png' })

  it('lets the browser paste when the clipboard has text beside the file', () => {
    // Excel and Word put both on the clipboard: the text wins and nothing attaches.
    expect(filesFromPaste(clipboard([png()], 'a cell'))).toBeNull()
  })

  it('lets the browser paste when there is nothing to attach', () => {
    expect(filesFromPaste(clipboard([], 'just words'))).toBeNull()
    expect(filesFromPaste(clipboard([]))).toBeNull()
  })

  it('attaches every file when the clipboard has no text', () => {
    const pasted = filesFromPaste(
      clipboard([new File(['a'], 'report.pdf', { type: 'application/pdf' }), png()]),
    )

    expect(pasted).toHaveLength(2)
    expect(pasted?.[0].name).toBe('report.pdf')
    expect(pasted?.[0].type).toBe('application/pdf')
  })

  it('renames the browser’s generic image.png, and only that', () => {
    const pasted = filesFromPaste(
      clipboard([png(), new File(['y'], 'holiday.png', { type: 'image/png' })]),
    )

    expect(pasted?.[0].name).toMatch(/^Pasted image \d{4}-\d{2}-\d{2} \d{2}\.\d{2}\.\d{2}\.png$/)
    expect(pasted?.[0].type).toBe('image/png')
    expect(pasted?.[1].name).toBe('holiday.png')
  })

  it('does not rename a JPEG that happens to be called image.png’s cousin', () => {
    const pasted = filesFromPaste(clipboard([new File(['z'], 'image.jpg', { type: 'image/jpeg' })]))

    expect(pasted?.[0].name).toBe('image.jpg')
  })
})
