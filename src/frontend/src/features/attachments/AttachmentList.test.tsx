/**
 * What a message shows for its files (issue 4 R9, R11, decisions 29–31): images
 * inline from a fetched URL, PDFs as a chip, a retry when an image will not load,
 * and a fresh URL at the moment of every click.
 *
 * `AttachmentList` takes `{ message, accessToken, workspaceId }` — the plan names
 * the component and leaves its props open. Queries are by role and text: the
 * `data-testid`s on these elements belong to the BDD suite.
 */

import { fireEvent, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { messaging, requests } from '../../test/api'
import { aMessage, anAttachment } from '../../test/factories'
import { renderWithProviders } from '../../test/render'
import { AttachmentList } from './AttachmentList'

const WORKSPACE = 'workspace-1'
const T0 = new Date('2026-10-01T09:00:00Z').getTime()
const DOWNLOAD = '/api/v1/messages/{message_id}/attachments/{asset_id}/download-url'

const image = anAttachment({ fileName: 'diagram.png', contentType: 'image/png', sizeBytes: 2048 })
const pdf = anAttachment({
  fileName: 'notes.pdf',
  contentType: 'application/pdf',
  sizeBytes: 12_345,
})

const downloads = () => requests().filter((r) => r.url.pathname.endsWith('/download-url'))
const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

function serveUrls() {
  let issued = 0
  messaging.get(DOWNLOAD, () => {
    issued += 1
    return { url: `http://garage.test/get/${issued}`, expiresAt: '2026-10-01T09:15:00Z' }
  })
}

function renderList(message = aMessage({ attachments: [image] })) {
  const view = renderWithProviders(
    <AttachmentList message={message} accessToken="token" workspaceId={WORKSPACE} />,
  )
  return { ...view, message }
}

/** A stand-in for the window `window.open` returns, recording where it is sent. */
function stubWindowOpen() {
  const navigated: string[] = []
  const location = {
    assign: (url: string) => navigated.push(url),
    replace: (url: string) => navigated.push(url),
    set href(url: string) {
      navigated.push(url)
    },
  }
  const opened = { opener: 'the page', close: vi.fn() } as Record<string, unknown>
  Object.defineProperty(opened, 'location', {
    get: () => location,
    set: (url: string) => navigated.push(String(url)),
  })
  const open = vi.spyOn(window, 'open').mockReturnValue(opened as unknown as Window)
  return { open, opened, navigated }
}

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('AttachmentList — images', () => {
  it('renders an image with the URL it fetched, capped in size', async () => {
    serveUrls()
    const { message } = renderList()

    const img = await screen.findByRole('img', { name: 'diagram.png' })

    await vi.waitFor(() => expect(img).toHaveAttribute('src', 'http://garage.test/get/1'))
    expect(img).toHaveClass('max-h-60', 'max-w-80')
    expect(downloads().map((r) => r.url.pathname)).toEqual([
      `/api/v1/messages/${message.id}/attachments/${image.assetId}/download-url`,
    ])
  })

  it('shows a tombstone no attachments, and asks for no URL', async () => {
    serveUrls()
    renderList(aMessage({ attachments: [image, pdf], deletedAt: '2026-09-15T10:00:00Z' }))

    await sleep(100)

    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(screen.queryByText('notes.pdf')).not.toBeInTheDocument()
    expect(downloads()).toEqual([])
  })

  it('asks for no URL while the message is still pending, then does once it is confirmed', async () => {
    // A `temp:` id would 404 at the server; the row carries the chips' metadata only.
    serveUrls()
    const pending = aMessage({ id: 'temp:1234', attachments: [image] })
    const { rerender, message } = renderList(pending)

    await sleep(100)
    expect(downloads()).toEqual([])

    rerender(
      <AttachmentList
        message={{ ...message, id: '0199a000-0000-7000-8000-0000000000aa' }}
        accessToken="token"
        workspaceId={WORKSPACE}
      />,
    )

    expect(await screen.findByRole('img', { name: 'diagram.png' })).toHaveAttribute(
      'src',
      'http://garage.test/get/1',
    )
    expect(downloads()).toHaveLength(1)
  })

  it('refetches once when the image fails to load, then offers a retry', async () => {
    serveUrls()
    renderList()
    const img = await screen.findByRole('img', { name: 'diagram.png' })
    await vi.waitFor(() => expect(img).toHaveAttribute('src', 'http://garage.test/get/1'))

    // The URL is fresh, so only a deliberate refetch can have asked for another.
    fireEvent.error(img)
    await vi.waitFor(() => expect(downloads()).toHaveLength(2))
    const second = await screen.findByRole('img', { name: 'diagram.png' })
    await vi.waitFor(() => expect(second).toHaveAttribute('src', 'http://garage.test/get/2'))

    fireEvent.error(second)

    expect(await screen.findByText(/couldn.t load/i)).toBeInTheDocument()
    expect(screen.queryByRole('img', { name: 'diagram.png' })).not.toBeInTheDocument()
    await sleep(100)
    expect(downloads()).toHaveLength(2)
  })

  it('refetches when retry is pressed, and shows the image again', async () => {
    serveUrls()
    const { user } = renderList()
    let img = await screen.findByRole('img', { name: 'diagram.png' })
    fireEvent.error(img)
    img = await screen.findByRole('img', { name: 'diagram.png' })
    await vi.waitFor(() => expect(img).toHaveAttribute('src', 'http://garage.test/get/2'))
    fireEvent.error(img)
    await screen.findByText(/couldn.t load/i)

    await user.click(screen.getByRole('button', { name: /retry/i }))

    await vi.waitFor(() => expect(downloads()).toHaveLength(3))
    expect(await screen.findByRole('img', { name: 'diagram.png' })).toHaveAttribute(
      'src',
      'http://garage.test/get/3',
    )
  })

  it('shows the retry placeholder, and still the PDF, when Asset is down', async () => {
    messaging.problem('get', DOWNLOAD, 503, { title: 'Service Unavailable' })
    renderList(aMessage({ attachments: [image, pdf] }))

    expect(await screen.findByText(/couldn.t load/i)).toBeInTheDocument()
    expect(screen.queryByRole('img', { name: 'diagram.png' })).not.toBeInTheDocument()
    // Metadata is stored with the message, so the chip needs no URL to render.
    expect(screen.getByText('notes.pdf')).toBeInTheDocument()
  })
})

describe('AttachmentList — PDFs', () => {
  it('renders a chip with the name, the size and a way to download', async () => {
    serveUrls()
    renderList(aMessage({ attachments: [pdf] }))

    expect(screen.getByText('notes.pdf')).toBeInTheDocument()
    expect(screen.getByText(/KB/)).toBeInTheDocument()
    const control =
      screen.queryByRole('button', { name: /download/i }) ??
      screen.getByRole('link', { name: /download/i })
    expect(control).toBeInTheDocument()
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })
})

describe('AttachmentList — fresh on click (R11, decision 29)', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(T0)
  })

  it('opens the window at once, then sends it to a URL fetched because the first had gone stale', async () => {
    const issued: string[] = []
    let hold!: () => void
    let gate: Promise<void> | null = null
    messaging.get(DOWNLOAD, async () => {
      await gate
      issued.push(`http://garage.test/get/${issued.length + 1}`)
      return { url: issued.at(-1) as string, expiresAt: '2026-10-01T09:15:00Z' }
    })
    const { user } = renderList()
    const img = await screen.findByRole('img', { name: 'diagram.png' })
    await vi.waitFor(() => expect(img).toHaveAttribute('src', 'http://garage.test/get/1'))
    const { open, opened, navigated } = stubWindowOpen()

    // 1 000 s on: the URL on screen is stale and the click must not use it.
    vi.setSystemTime(T0 + 1_000_000)
    gate = new Promise<void>((resolve) => {
      hold = resolve
    })
    await user.click(img)

    // Synchronously, before the fetch can have answered: a window opened after an
    // await loses its user activation in Safari and is blocked.
    expect(open).toHaveBeenCalledTimes(1)
    expect(open).toHaveBeenCalledWith('', '_blank')
    expect(navigated).toEqual([])
    expect(opened.opener).toBeNull()

    hold()

    await vi.waitFor(() => expect(navigated).toEqual(['http://garage.test/get/2']))
    expect(downloads()).toHaveLength(2)
  })

  it('opens the cached URL, with no new request, while it is still fresh', async () => {
    serveUrls()
    const { user } = renderList()
    const img = await screen.findByRole('img', { name: 'diagram.png' })
    await vi.waitFor(() => expect(img).toHaveAttribute('src', 'http://garage.test/get/1'))
    const { open, navigated } = stubWindowOpen()

    vi.setSystemTime(T0 + 1_000)
    await user.click(img)

    expect(open).toHaveBeenCalledTimes(1)
    await vi.waitFor(() => expect(navigated).toEqual(['http://garage.test/get/1']))
    expect(downloads()).toHaveLength(1)
  })

  it('downloads a PDF through a URL that is fresh at the click', async () => {
    serveUrls()
    const { user } = renderList(aMessage({ attachments: [pdf] }))
    stubWindowOpen()
    const download = () =>
      screen.queryByRole('button', { name: /download/i }) ??
      screen.getByRole('link', { name: /download/i })

    await user.click(download())
    await vi.waitFor(() => expect(downloads().length).toBeGreaterThanOrEqual(1))
    const afterFirst = downloads().length

    // Still fresh: another click is no further request.
    vi.setSystemTime(T0 + 1_000)
    await user.click(download())
    await sleep(100)
    expect(downloads()).toHaveLength(afterFirst)

    // Past 780 s: the click fetches again before anything is opened.
    vi.setSystemTime(T0 + 781_000)
    await user.click(download())
    await vi.waitFor(() => expect(downloads()).toHaveLength(afterFirst + 1))
  })
})
