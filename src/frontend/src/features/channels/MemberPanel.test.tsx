import { screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Channel, ChannelMember } from '../../lib/api/messaging'
import { auth, messaging, requests } from '../../test/api'
import { aChannel, aWorkspaceMember, WORKSPACE_ID } from '../../test/factories'
import { createTestQueryClient, renderWithProviders } from '../../test/render'
import { MemberPanel } from './MemberPanel'
import { channelKeys } from './useChannels'

const JOINED_AT = '2026-09-15T09:00:00Z'

const ada = aWorkspaceMember({ displayName: 'Ada Lovelace' })
const grace = aWorkspaceMember({ displayName: 'Grace Hopper' })
const alan = aWorkspaceMember({ displayName: 'Alan Turing' })

function row(member: typeof ada, role = 'member'): ChannelMember {
  return { userId: member.user.id, role, joinedAt: JOINED_AT }
}

/**
 * Plays Messaging's membership routes over a mutable list, so a write shows up
 * in the next read — which is only seen if the panel reads again.
 */
function membership(initial: ChannelMember[]) {
  let rows = initial
  auth.members([ada, grace, alan])
  messaging.get('/api/v1/channels/{channel_id}/members', () => ({ items: rows, nextCursor: null }))
  messaging.post('/api/v1/channels/{channel_id}/members', ({ body }) => {
    const added = { userId: body.userId, role: body.role ?? 'member', joinedAt: JOINED_AT }
    rows = [...rows, added]
    return added
  })
  messaging.noContent('delete', '/api/v1/channels/{channel_id}/members/{user_id}', (params) => {
    rows = rows.filter((r) => r.userId !== params.user_id)
  })
}

function renderPanel(channel: Channel) {
  const queryClient = createTestQueryClient()
  // The channel queries the sidebar and header read, seeded so a test can see
  // whether a membership change marks them stale.
  queryClient.setQueryData(channelKeys.list(WORKSPACE_ID), { items: [channel], nextCursor: null })
  queryClient.setQueryData(channelKeys.detail(WORKSPACE_ID, channel.id), channel)
  const rendered = renderWithProviders(
    <MemberPanel accessToken="token" workspaceId={WORKSPACE_ID} channel={channel} />,
    { queryClient },
  )
  const channelQueriesInvalidated = () => [
    queryClient.getQueryState(channelKeys.list(WORKSPACE_ID))?.isInvalidated,
    queryClient.getQueryState(channelKeys.detail(WORKSPACE_ID, channel.id))?.isInvalidated,
  ]
  return { ...rendered, channelQueriesInvalidated }
}

/** The member list, once its names have resolved. */
async function memberList() {
  const list = within(await screen.findByRole('list'))
  await list.findByText('Grace Hopper')
  return list
}

describe('MemberPanel', () => {
  it('offers a channel admin the controls to add and remove members', async () => {
    membership([row(ada, 'admin'), row(grace)])

    renderPanel(aChannel({ kind: 'private', myRole: 'admin' }))
    await memberList()

    expect(screen.getAllByRole('button', { name: 'Remove' })).toHaveLength(2)
    expect(screen.getByRole('combobox', { name: 'Add someone to this channel' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add' })).toBeInTheDocument()
  })

  it('shows a member who is not an admin the list, and no controls', async () => {
    membership([row(ada, 'admin'), row(grace)])

    renderPanel(aChannel({ kind: 'private', myRole: 'member' }))
    await memberList()

    expect(screen.queryByRole('button', { name: 'Remove' })).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add' })).not.toBeInTheDocument()
  })

  it('offers to add only workspace members who are not already in the channel', async () => {
    membership([row(ada, 'admin'), row(grace)])

    renderPanel(aChannel({ kind: 'private', myRole: 'admin' }))
    await memberList()

    const select = screen.getByRole('combobox', { name: 'Add someone to this channel' })
    expect(within(select).getAllByRole('option').map((option) => option.textContent)).toEqual([
      'Add someone…',
      'Alan Turing',
    ])
  })

  it('adding a member refreshes the member list and the channel', async () => {
    membership([row(ada, 'admin'), row(grace)])
    const channel = aChannel({ kind: 'private', myRole: 'admin' })

    const { user, channelQueriesInvalidated } = renderPanel(channel)
    const list = await memberList()
    await user.selectOptions(
      screen.getByRole('combobox', { name: 'Add someone to this channel' }),
      'Alan Turing',
    )
    await user.click(screen.getByRole('button', { name: 'Add' }))

    expect(await list.findByText('Alan Turing')).toBeInTheDocument()
    expect(requests().find((r) => r.method === 'POST')?.body).toEqual({
      userId: alan.user.id,
      role: 'member',
    })
    expect(channelQueriesInvalidated()).toEqual([true, true])
  })

  it('removing a member refreshes the member list and the channel', async () => {
    membership([row(ada, 'admin'), row(grace)])
    const channel = aChannel({ kind: 'private', myRole: 'admin' })

    const { user, channelQueriesInvalidated } = renderPanel(channel)
    const list = await memberList()
    const graceRow = list
      .getAllByRole('listitem')
      .find((item) => within(item).queryByText('Grace Hopper'))
    await user.click(within(graceRow as HTMLElement).getByRole('button', { name: 'Remove' }))

    await vi.waitFor(() => expect(list.queryByText('Grace Hopper')).not.toBeInTheDocument())
    expect(
      requests().find((r) => r.method === 'DELETE')?.url.pathname.endsWith(`/${grace.user.id}`),
    ).toBe(true)
    expect(channelQueriesInvalidated()).toEqual([true, true])
  })
})
