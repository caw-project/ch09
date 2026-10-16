import type { QueryClient } from '@tanstack/react-query'
import { act } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { WorkspaceMember } from '../../lib/auth/api'
import { auth } from '../../test/api'
import { settleDirectory, scriptDirectory } from '../../test/directory'
import { aWorkspaceMember } from '../../test/factories'
import { createTestQueryClient, renderHookWithProviders } from '../../test/render'
import { directoryKeys, shortId, useWorkspaceMembers } from './useWorkspaceMembers'

const WS_A = '0199a000-0000-7000-8000-00000000aaa0'
const WS_B = '0199a000-0000-7000-8000-00000000bbb0'

const ada = aWorkspaceMember({ id: '0199a000-0000-7000-8000-000000000001', displayName: 'Ada Lovelace' })
const grace = aWorkspaceMember({ id: '01a13ec0-0000-7000-8000-000000000002', displayName: 'Grace Hopper' })
const alan = aWorkspaceMember({ id: '01b20000-0000-7000-8000-000000000003', displayName: 'Alan Turing' })
const bob = aWorkspaceMember({ id: '01c30000-0000-7000-8000-000000000004', displayName: 'Bob Barker' })

const idOf = (m: WorkspaceMember) => m.user.id
const short = (m: WorkspaceMember) => shortId(m.user.id)

let anchors = 0
const nextAnchor = () =>
  `0199c0de-0000-7000-8000-${(++anchors).toString(16).padStart(12, '0')}`

/** A macrotask or two, so anything a build would start on its own has started. */
const pause = () => act(() => new Promise<void>((resolve) => setTimeout(resolve, 25)))

/**
 * Two consumers in one render, each asking for its own list of ids. The workspace
 * and the lists are mutable, so a switch or a new question is "change it, rerender".
 */
function harness(initial: { workspace?: string; asking?: string[] } = {}) {
  const queryClient = createTestQueryClient()
  const state = {
    workspace: initial.workspace ?? WS_A,
    first: initial.asking ?? [],
    second: [] as string[],
  }
  const view = renderHookWithProviders(
    () => {
      const first = useWorkspaceMembers('token', state.workspace)
      const second = useWorkspaceMembers('token', state.workspace)
      return { first: state.first.map(first.nameFor), second: state.second.map(second.nameFor) }
    },
    { queryClient },
  )
  return {
    queryClient,
    state,
    names: () => view.result.current.first,
    namesSecond: () => view.result.current.second,
    ask(...ids: string[]) {
      state.first = ids
      view.rerender()
    },
    askSecond(...ids: string[]) {
      state.second = ids
      view.rerender()
    },
    rerender: () => view.rerender(),
    switchTo(workspace: string) {
      state.workspace = workspace
      view.rerender()
    },
  }
}

type Harness = ReturnType<typeof harness>
type Script = ReturnType<typeof scriptDirectory>

async function loaded(queryClient: QueryClient, workspace = WS_A) {
  await vi.waitFor(() =>
    expect(queryClient.getQueryData(directoryKeys.members(workspace))).toBeDefined(),
  )
  await settleDirectory(queryClient, workspace)
}

/**
 * "These ids start no request": settle, take the baseline, do `ask`, settle again
 * (a fetch a wrong build started for them lands here, before any anchor exists),
 * then ask a brand-new id and require exactly one more request — the tracker can
 * still fetch, so "nothing" is not a dead tracker — and that the ids show short.
 */
async function quiet(
  h: Harness,
  script: Script,
  ids: WorkspaceMember[],
  ask: () => void | Promise<void>,
  options: { workspace?: string; anchorAnswer?: WorkspaceMember[] } = {},
) {
  const workspace = options.workspace ?? WS_A
  await settleDirectory(h.queryClient, workspace)
  const before = script.requests(workspace).length
  if (options.anchorAnswer) script.answer(workspace, before + 1, options.anchorAnswer)
  await ask()
  await settleDirectory(h.queryClient, workspace)
  expect(script.requests(workspace)).toHaveLength(before)

  h.ask(...h.state.first, nextAnchor())
  await vi.waitFor(() => expect(script.requests(workspace).length).toBeGreaterThan(before))
  await settleDirectory(h.queryClient, workspace)

  expect(script.requests(workspace)).toHaveLength(before + 1)
  for (const id of ids) expect(h.names()[h.state.first.indexOf(idOf(id))]).toBe(short(id))
}

describe('the workspace directory', () => {
  // Without it a new member's name never replaces their id until a reload.
  it('shows the short id while the refetch is in flight, then the name it brings', async () => {
    const script = scriptDirectory({ [WS_A]: [ada] })
    const h = harness()
    await loaded(h.queryClient)
    const second = script.hold(WS_A, 2)

    h.ask(idOf(grace))
    await vi.waitFor(() => expect(script.requests(WS_A)).toHaveLength(2))
    expect(h.names()).toEqual([short(grace)])

    await second.release([ada, grace])
    await vi.waitFor(() => expect(h.names()).toEqual(['Grace Hopper']))
  })

  // Without it every unknown id, or every consumer, makes its own request.
  it('asks once for several unknown ids in one render, and once for an id two consumers ask for', async () => {
    const script = scriptDirectory({ [WS_A]: [ada] })
    const h = harness()
    await loaded(h.queryClient)

    script.now[WS_A] = [ada, grace]
    h.state.second = [idOf(grace)]
    h.ask(idOf(grace), idOf(alan))
    await vi.waitFor(() => expect(h.names()[0]).toBe('Grace Hopper'))
    await settleDirectory(h.queryClient, WS_A)

    expect(script.requests(WS_A)).toHaveLength(2)
    expect(h.namesSecond()).toEqual(['Grace Hopper'])
    await quiet(h, script, [alan], () => h.rerender())
  })

  // Without it a failed-to-load directory is refetched at once, or a late id is never retried.
  it('starts nothing during the first load, then one refetch for ids it lacked, and departs them if that lacks them too', async () => {
    const script = scriptDirectory({ [WS_A]: [ada] })
    const first = script.hold(WS_A, 1)
    const h = harness()
    await vi.waitFor(() => expect(script.requests(WS_A)).toHaveLength(1))

    h.ask(idOf(grace))
    await pause()
    expect(script.requests(WS_A)).toHaveLength(1)

    await first.release([ada])
    await vi.waitFor(() => expect(script.requests(WS_A)).toHaveLength(2))
    await quiet(h, script, [grace], () => h.rerender())
  })

  // Without it an id first seen mid-fetch is wrongly departed by a fetch that began before it.
  it('an id first seen during a refetch gets one more; an id seen before it is departed', async () => {
    const script = scriptDirectory({ [WS_A]: [ada] })
    const h = harness()
    await loaded(h.queryClient)
    const second = script.hold(WS_A, 2)
    const third = script.hold(WS_A, 3)

    h.ask(idOf(bob))
    await vi.waitFor(() => expect(script.requests(WS_A)).toHaveLength(2))
    h.ask(idOf(bob), idOf(alan))
    await pause()
    expect(script.requests(WS_A)).toHaveLength(2)

    // The test does not rerender: landing equal data must itself start #3.
    await second.release([ada])
    await vi.waitFor(() => expect(script.requests(WS_A)).toHaveLength(3))

    await third.release([ada])
    await quiet(h, script, [alan, bob], () => h.rerender())
  })

  // Without it a message from someone who left refetches the directory on every render.
  it('a departed id starts no further refetch, however often it is asked', async () => {
    const script = scriptDirectory({ [WS_A]: [ada] })
    const h = harness()
    await loaded(h.queryClient)
    h.ask(idOf(alan))
    await vi.waitFor(() => expect(script.requests(WS_A)).toHaveLength(2))
    await settleDirectory(h.queryClient, WS_A)

    await quiet(h, script, [alan], async () => {
      h.rerender()
      h.rerender()
      h.rerender()
      // A consumer that mounts later asks the same departed id.
      const late = renderHookWithProviders(
        () => useWorkspaceMembers('token', WS_A).nameFor(idOf(alan)),
        { queryClient: h.queryClient },
      )
      await settleDirectory(h.queryClient, WS_A)
      expect(late.result.current).toBe(short(alan))
    })
  })

  // Without it an id seen during a staleness refetch starts a second, concurrent request.
  it('an unknown id seen while a refetch for another reason is in flight joins it', async () => {
    const script = scriptDirectory({ [WS_A]: [ada] })
    const h = harness()
    await loaded(h.queryClient)
    const second = script.hold(WS_A, 2)
    const third = script.hold(WS_A, 3)

    act(() => {
      void h.queryClient.invalidateQueries({ queryKey: directoryKeys.members(WS_A) })
    })
    await vi.waitFor(() => expect(script.requests(WS_A)).toHaveLength(2))
    h.ask(idOf(grace))
    await pause()
    expect(script.requests(WS_A)).toHaveLength(2)

    await second.release([ada])
    await vi.waitFor(() => expect(script.requests(WS_A)).toHaveLength(3))
    await third.release([ada, grace])
    await vi.waitFor(() => expect(h.names()).toEqual(['Grace Hopper']))
    await settleDirectory(h.queryClient, WS_A)
    expect(script.requests(WS_A)).toHaveLength(3)
  })

  // Without it a departed author stays a short id for the rest of the session.
  it('a fetch for another reason clears the departed set, and the id earns one more refetch', async () => {
    const script = scriptDirectory({ [WS_A]: [ada] })
    const h = harness()
    await loaded(h.queryClient)
    h.ask(idOf(alan))
    await vi.waitFor(() => expect(script.requests(WS_A)).toHaveLength(2))
    await settleDirectory(h.queryClient, WS_A)

    act(() => {
      void h.queryClient.invalidateQueries({ queryKey: directoryKeys.members(WS_A) })
    })
    await vi.waitFor(() => expect(script.requests(WS_A)).toHaveLength(4))
    await settleDirectory(h.queryClient, WS_A)
    expect(script.requests(WS_A)).toHaveLength(4)

    await quiet(h, script, [alan], () => h.rerender())
  })

  // Without it a rejoining member is chased on every render, or never named.
  it('a departed member who rejoins is named at the next fetch for another reason, not before', async () => {
    const script = scriptDirectory({ [WS_A]: [ada] })
    const h = harness()
    await loaded(h.queryClient)
    h.ask(idOf(alan))
    await vi.waitFor(() => expect(script.requests(WS_A)).toHaveLength(2))
    await settleDirectory(h.queryClient, WS_A)

    script.now[WS_A] = [ada, alan]
    // The anchor's own call answers without Alan, so only a refetch *for him* could name him.
    await quiet(h, script, [alan], () => h.rerender(), { anchorAnswer: [ada] })

    act(() => {
      void h.queryClient.invalidateQueries({ queryKey: directoryKeys.members(WS_A) })
    })
    await vi.waitFor(() => expect(h.names()[0]).toBe('Alan Turing'))
  })

  // Without it a persistently failing directory is hit on every render.
  it('a refetch that fails leaves the ids it was for quiet', async () => {
    const script = scriptDirectory({ [WS_A]: [ada] })
    const h = harness()
    await loaded(h.queryClient)
    auth.problem('get', '/api/v1/workspaces/:workspaceId/members', 500, { title: 'Boom' })

    h.ask(idOf(grace))
    await vi.waitFor(() => expect(script.requests(WS_A)).toHaveLength(2))
    await settleDirectory(h.queryClient, WS_A)
    expect(h.names()).toEqual([short(grace)])

    await quiet(h, script, [grace], async () => {
      h.rerender()
      h.rerender()
      h.rerender()
    })
  })

  // Without it a response for the workspace left behind lands in, or reads from, the wrong cache.
  it('a refetch for one workspace lands in that workspace’s cache, after a switch', async () => {
    const script = scriptDirectory({ [WS_A]: [ada], [WS_B]: [bob] })
    const h = harness()
    await loaded(h.queryClient)
    const held = script.hold(WS_A, 2)

    h.ask(idOf(grace))
    await vi.waitFor(() => expect(script.requests(WS_A)).toHaveLength(2))
    h.switchTo(WS_B)
    await loaded(h.queryClient, WS_B)

    await held.release([ada, grace])
    await settleDirectory(h.queryClient, WS_A)
    await settleDirectory(h.queryClient, WS_B)

    const inA = h.queryClient.getQueryData<WorkspaceMember[]>(directoryKeys.members(WS_A))
    const inB = h.queryClient.getQueryData<WorkspaceMember[]>(directoryKeys.members(WS_B))
    expect(inA?.map(idOf)).toContain(idOf(grace))
    expect(inB?.map(idOf)).not.toContain(idOf(grace))
    expect(h.names()).toEqual([short(grace)])
  })

  // Without it one workspace's departed member silences every other workspace's lookup.
  it('each workspace keeps its own departed set', async () => {
    const script = scriptDirectory({ [WS_A]: [ada], [WS_B]: [ada] })
    const h = harness()
    // Both directories are loaded and fresh (5 minutes) before anyone departs, so
    // no first-load fetch clears a departed set between the steps below.
    await loaded(h.queryClient)
    h.switchTo(WS_B)
    await loaded(h.queryClient, WS_B)
    h.switchTo(WS_A)
    await settleDirectory(h.queryClient, WS_A)
    expect(script.requests(WS_A)).toHaveLength(1)
    expect(script.requests(WS_B)).toHaveLength(1)

    // Alan departs in A.
    h.ask(idOf(alan))
    await vi.waitFor(() => expect(script.requests(WS_A)).toHaveLength(2))
    await settleDirectory(h.queryClient, WS_A)
    expect(h.names()).toEqual([short(alan)])

    // In B he is not departed: exactly one request for him there, and A is untouched.
    h.switchTo(WS_B)
    await vi.waitFor(() => expect(script.requests(WS_B)).toHaveLength(2))
    await settleDirectory(h.queryClient, WS_B)
    expect(script.requests(WS_B)).toHaveLength(2)
    expect(script.requests(WS_A)).toHaveLength(2)
    expect(h.names()).toEqual([short(alan)])

    // A fetch for another reason in B clears B's set only.
    act(() => {
      void h.queryClient.invalidateQueries({ queryKey: directoryKeys.members(WS_B) })
    })
    await vi.waitFor(() => expect(script.requests(WS_B).length).toBeGreaterThan(2))
    await settleDirectory(h.queryClient, WS_B)

    // Back in A, Alan is still departed: asking again starts nothing, and a new id still can.
    h.switchTo(WS_A)
    await quiet(h, script, [alan], () => h.rerender(), { workspace: WS_A })
  })
})
