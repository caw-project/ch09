/**
 * The sidebar's *Direct messages* section and its picker (issue 5, R1, R6, R7).
 *
 * The section reads the channel list and the workspace directory itself, shows the
 * `kind: 'dm'` rows named after the other person, and opens one DM from a **+**.
 * Messaging and Auth are stubbed at the network edge, so TanStack and
 * `openapi-fetch` run for real. Real time throughout, as `ChannelList.test.tsx`.
 *
 * Red: `Failed to resolve import "./DirectMessageList"`.
 */

import { act, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Channel } from '../../lib/api/messaging'
import { auth, messaging, requests } from '../../test/api'
import { aChannel, aWorkspaceMember, WORKSPACE_ID } from '../../test/factories'
import { renderWithProviders } from '../../test/render'
import { useChatStore } from '../../stores/chat'
import { DirectMessageList } from './DirectMessageList'
import { channelKeys } from './useChannels'

const ADA = 'user-ada'
const GRACE = 'user-grace'
const ALAN = 'user-alan'
const BARBARA = 'user-barbara'
const OTHER_WORKSPACE = 'workspace-2'

const directory = () =>
  auth.members([
    aWorkspaceMember({ id: ADA, displayName: 'Ada Lovelace' }),
    aWorkspaceMember({ id: GRACE, displayName: 'Grace Hopper' }),
    aWorkspaceMember({ id: ALAN, displayName: 'Alan Turing' }),
    aWorkspaceMember({ id: BARBARA, displayName: 'Barbara Liskov' }),
  ])

const dmWith = (partner: string, overrides: Partial<Channel> = {}) =>
  aChannel({ kind: 'dm', name: `dm:${ADA}:${partner}`, dmPartnerId: partner, ...overrides })

function renderSection(workspaceId: string | null = WORKSPACE_ID) {
  return renderWithProviders(
    <DirectMessageList accessToken="token" workspaceId={workspaceId} userId={ADA} />,
  )
}

const region = () => screen.findByRole('region', { name: 'Direct messages' })

describe('DirectMessageList — the rows', () => {
  it('lists only the direct messages of a mixed response, named after the partner, in name order', async () => {
    directory()
    messaging.get('/api/v1/channels', {
      items: [
        aChannel({ name: 'general' }),
        dmWith(GRACE),
        aChannel({ name: 'random' }),
        dmWith(ALAN),
      ],
      nextCursor: null,
    })

    renderSection()
    const section = await region()

    // Names arrive from the directory: wait for both, so the stub is not what is read.
    await within(section).findByRole('link', { name: 'Alan Turing' })
    const links = within(section).getAllByRole('link')
    expect(links.map((link) => link.textContent)).toEqual(['Alan Turing', 'Grace Hopper'])
    expect(within(section).queryByText(/dm:/)).not.toBeInTheDocument()
    expect(screen.queryByText('general')).not.toBeInTheDocument()
  })

  it('links each row to its channel', async () => {
    directory()
    const dm = dmWith(GRACE)
    messaging.get('/api/v1/channels', { items: [dm], nextCursor: null })

    renderSection()

    expect(await screen.findByRole('link', { name: 'Grace Hopper' })).toHaveAttribute(
      'href',
      `/c/${dm.id}`,
    )
  })

  it('shows a count pill and a bold name for unread messages, and none for the one being read', async () => {
    directory()
    const reading = dmWith(GRACE, { unreadCount: 3 })
    const unread = dmWith(ALAN, { unreadCount: 2 })
    const quiet = dmWith(BARBARA)
    useChatStore.setState({ readingChannelId: reading.id })
    messaging.get('/api/v1/channels', { items: [reading, unread, quiet], nextCursor: null })

    renderSection()

    // The other DM's badge is the positive half: the list has rendered.
    const pill = await screen.findByLabelText('2 unread messages')
    expect(pill).toHaveTextContent('2')
    expect(screen.queryByLabelText('3 unread messages')).not.toBeInTheDocument()
    expect(screen.getAllByLabelText(/unread message/)).toHaveLength(1)
    const link = screen.getByRole('link', { name: /^Alan Turing/ })
    expect(within(link).getByText('Alan Turing')).toHaveClass('font-semibold')
    expect(
      within(screen.getByRole('link', { name: 'Barbara Liskov' })).getByText('Barbara Liskov'),
    ).not.toHaveClass('font-semibold')
  })
})

describe('DirectMessageList — the picker', () => {
  it('lists the other members by display name, without the caller, sorted', async () => {
    directory()
    messaging.get('/api/v1/channels', { items: [], nextCursor: null })
    const { user } = renderSection()
    await region()

    await user.click(screen.getByRole('button', { name: 'New direct message' }))

    const [alan, barbara, grace] = await Promise.all(
      ['Alan Turing', 'Barbara Liskov', 'Grace Hopper'].map((name) => screen.findByText(name)),
    )
    expect(screen.queryByText('Ada Lovelace')).not.toBeInTheDocument()
    const before = (a: HTMLElement, b: HTMLElement) =>
      Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING)
    expect(before(alan, barbara)).toBe(true)
    expect(before(barbara, grace)).toBe(true)
  })

  it('opens the DM with the person picked and goes to it', async () => {
    directory()
    const dm = dmWith(GRACE)
    messaging.get('/api/v1/channels', { items: [], nextCursor: null })
    messaging.post('/api/v1/channels/dm', dm)
    const { user, location } = renderSection()
    await region()

    await user.click(screen.getByRole('button', { name: 'New direct message' }))
    await user.click(await screen.findByText('Grace Hopper'))

    await vi.waitFor(() => expect(location().pathname).toBe(`/c/${dm.id}`))
    const posts = requests().filter((r) => r.method === 'POST')
    expect(posts.map((r) => [r.url.pathname, r.body])).toEqual([
      ['/api/v1/channels/dm', { userId: GRACE }],
    ])
  })
})

describe('DirectMessageList — a workspace switch while the DM is being opened', () => {
  function holdTheOpen() {
    directory()
    const dm = dmWith(GRACE)
    let release!: () => void
    const held = new Promise<void>((resolve) => {
      release = resolve
    })
    messaging.get('/api/v1/channels', { items: [], nextCursor: null })
    messaging.post('/api/v1/channels/dm', async () => {
      await held
      return dm
    })
    return { dm, release: () => act(async () => release()) }
  }

  async function pickGrace(view: ReturnType<typeof renderSection>) {
    await region()
    await view.user.click(screen.getByRole('button', { name: 'New direct message' }))
    await view.user.click(await screen.findByText('Grace Hopper'))
    await vi.waitFor(() => expect(requests().some((r) => r.method === 'POST')).toBe(true))
  }

  it('navigates when the workspace is still the one it started in', async () => {
    const { dm, release } = holdTheOpen()
    const view = renderSection()
    await pickGrace(view)

    await release()

    await vi.waitFor(() => expect(view.location().pathname).toBe(`/c/${dm.id}`))
  })

  it('does not navigate into another workspace, and invalidates only the list it started in', async () => {
    const { release } = holdTheOpen()
    const view = renderSection()
    await pickGrace(view)
    const startedIn = view.location().pathname

    view.rerender(
      <DirectMessageList accessToken="token" workspaceId={OTHER_WORKSPACE} userId={ADA} />,
    )
    await release()

    // Settled: both the hook's and the call's callbacks have run by now.
    await vi.waitFor(() => expect(view.queryClient.isMutating()).toBe(0))
    expect(
      view.queryClient.getQueryState(channelKeys.list(WORKSPACE_ID))?.isInvalidated,
    ).toBe(true)
    expect(view.location().pathname).toBe(startedIn)
  })
})
