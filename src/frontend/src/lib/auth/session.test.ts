/**
 * The session store is module state, so each test imports a fresh copy.
 * Auth is stubbed at the network edge, exactly as the app calls it.
 */

import { delay, http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { auth, AUTH_URL, requests, server } from '../../test/api'
import type { Profile, TokenPair, Workspace } from './api'

type SessionModule = typeof import('./session')

const HOME = 'workspace-home'
const AWAY = 'workspace-away'
const VERIFIER_KEY = 'collabhub.pkceVerifier'

const PROFILE: Profile = {
  id: 'user-ada',
  email: 'ada@collabhub.dev',
  displayName: 'Ada Lovelace',
  avatarAsset: null,
}
const WORKSPACES: Workspace[] = [
  { id: HOME, name: 'Home', role: 'owner' },
  { id: AWAY, name: 'Away', role: 'member' },
]

/** An unsigned token carrying a `wsp` claim — the SPA only ever reads it. */
function tokenFor(workspaceId: string, marker = 'a'): string {
  const payload = btoa(JSON.stringify({ wsp: workspaceId, marker }))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
  return `header.${payload}.signature`
}

function pair(workspaceId: string, expiresIn = 900, marker = 'a'): TokenPair {
  return { accessToken: tokenFor(workspaceId, marker), tokenType: 'Bearer', expiresIn }
}

function signedInSession(session: SessionModule) {
  const state = session.snapshot()
  if (state.status !== 'signedIn') throw new Error(`expected signedIn, was ${state.status}`)
  return state.session
}

let session: SessionModule

beforeEach(async () => {
  vi.resetModules()
  session = await import('./session')
  auth.me(PROFILE)
  auth.workspaces(WORKSPACES)
})

afterEach(() => {
  vi.useRealTimers()
  window.sessionStorage.clear()
})

describe('restore', () => {
  it('starts out loading', () => {
    expect(session.snapshot()).toEqual({ status: 'loading' })
  })

  it('resumes a session from the refresh cookie', async () => {
    auth.refresh(pair(HOME))

    await session.restore()

    expect(signedInSession(session)).toEqual({
      accessToken: tokenFor(HOME),
      profile: PROFILE,
      workspaces: WORKSPACES,
      activeWorkspaceId: HOME,
    })
  })

  it('treats a refused refresh as a first visit, not an error', async () => {
    auth.problem('post', '/api/v1/auth/refresh', 401, { title: 'Unauthorized' })

    await session.restore()

    expect(session.snapshot()).toEqual({ status: 'signedOut', error: undefined })
  })
})

describe('subscribe', () => {
  it('tells a listener about every change until it unsubscribes', async () => {
    const listener = vi.fn()
    const unsubscribe = session.subscribe(listener)
    auth.problem('post', '/api/v1/auth/refresh', 401, { title: 'Unauthorized' })

    await session.restore()
    expect(listener).toHaveBeenCalledTimes(1)

    unsubscribe()
    await session.signOut()
    expect(listener).toHaveBeenCalledTimes(1)
  })
})

describe('completeSignIn', () => {
  it('says why the identity provider refused, and forgets the verifier', async () => {
    window.sessionStorage.setItem(VERIFIER_KEY, 'verifier')

    const completed = await session.completeSignIn(new URLSearchParams('error=access_denied'))

    expect(completed).toBe(false)
    expect(session.snapshot()).toEqual({
      status: 'signedOut',
      error: 'Sign-in was declined at the identity provider.',
    })
    expect(window.sessionStorage.getItem(VERIFIER_KEY)).toBeNull()
  })

  it('names an error code it does not know rather than hiding it', async () => {
    await session.completeSignIn(new URLSearchParams('error=server_error'))

    expect(session.snapshot()).toEqual({
      status: 'signedOut',
      error: 'Sign-in failed (server_error).',
    })
  })

  it('refuses a code that arrived without this tab’s verifier', async () => {
    const completed = await session.completeSignIn(new URLSearchParams('code=abc'))

    expect(completed).toBe(false)
    expect(session.snapshot()).toEqual({
      status: 'signedOut',
      error: 'This sign-in was started in another tab.',
    })
  })

  it('spends the verifier once, clearing it before the exchange', async () => {
    window.sessionStorage.setItem(VERIFIER_KEY, 'the-verifier')
    let storedDuringExchange: string | null = 'not called'
    server.use(
      http.post(`${AUTH_URL}/api/v1/auth/token`, async ({ request }) => {
        storedDuringExchange = window.sessionStorage.getItem(VERIFIER_KEY)
        const body = (await request.json()) as Record<string, string>
        expect(body).toEqual({
          grantType: 'authorization_code',
          code: 'the-code',
          codeVerifier: 'the-verifier',
        })
        return HttpResponse.json(pair(HOME))
      }),
    )

    const completed = await session.completeSignIn(new URLSearchParams('code=the-code'))

    expect(completed).toBe(true)
    expect(storedDuringExchange).toBeNull()
    expect(signedInSession(session).activeWorkspaceId).toBe(HOME)
  })
})

describe('changeWorkspace', () => {
  it('adopts the token for the other workspace', async () => {
    auth.refresh(pair(HOME))
    await session.restore()
    auth.switchWorkspace(pair(AWAY))

    await session.changeWorkspace(AWAY)

    expect(signedInSession(session).activeWorkspaceId).toBe(AWAY)
    expect(requests().find((r) => r.url.pathname.endsWith('/switch-workspace'))?.body).toEqual({
      workspaceId: AWAY,
    })
  })

  it('signs out when the switch is refused', async () => {
    auth.refresh(pair(HOME))
    await session.restore()
    auth.problem('post', '/api/v1/auth/switch-workspace', 404, {
      title: 'Not found',
      detail: 'No such workspace.',
    })

    await session.changeWorkspace('nowhere')

    expect(session.snapshot()).toEqual({ status: 'signedOut', error: 'No such workspace.' })
  })
})

describe('signOut', () => {
  it('revokes the session on the server', async () => {
    auth.refresh(pair(HOME))
    await session.restore()
    auth.logout()

    await session.signOut()

    expect(session.snapshot()).toEqual({ status: 'signedOut', error: undefined })
    expect(requests().some((r) => r.url.pathname === '/api/v1/auth/logout')).toBe(true)
  })

  it('ends the local session even when revocation fails', async () => {
    auth.refresh(pair(HOME))
    await session.restore()
    auth.problem('post', '/api/v1/auth/logout', 500, { title: 'Internal error' })

    await session.signOut()

    expect(session.snapshot()).toEqual({ status: 'signedOut', error: undefined })
  })
})

describe('renewal', () => {
  it('renews a minute before the token expires', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    auth.refresh(pair(HOME, 120, 'first'))
    await session.restore()
    auth.refresh(pair(HOME, 120, 'renewed'))

    await vi.advanceTimersByTimeAsync(59_000)
    expect(signedInSession(session).accessToken).toBe(tokenFor(HOME, 'first'))

    await vi.advanceTimersByTimeAsync(1_000)
    await vi.waitFor(() =>
      expect(signedInSession(session).accessToken).toBe(tokenFor(HOME, 'renewed')),
    )
  })

  it('signs out when a renewal is refused, rather than retrying a spent token', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    auth.refresh(pair(HOME, 120))
    await session.restore()
    auth.problem('post', '/api/v1/auth/refresh', 401, { title: 'Unauthorized' })

    await vi.advanceTimersByTimeAsync(60_000)

    await vi.waitFor(() => expect(session.snapshot().status).toBe('signedOut'))
  })
})

describe('concurrent renewal', () => {
  const refreshes = () => requests().filter((r) => r.url.pathname === '/api/v1/auth/refresh')

  it('spends the refresh cookie once when two renewals overlap', async () => {
    // StrictMode runs the startup restore twice, and a timer renewal can fire
    // while a restore is still in flight. Rotation makes the second POST a
    // replay of a spent token, which the server treats as theft and answers by
    // revoking the session — so overlapping callers must share one request.
    auth.refresh(pair(HOME))

    await Promise.all([session.restore(), session.restore()])

    expect(refreshes()).toHaveLength(1)
    expect(signedInSession(session).accessToken).toBe(tokenFor(HOME))
  })

  it('asks again for a renewal that starts after the last one settled', async () => {
    auth.refresh(pair(HOME))

    await session.restore()
    await session.restore()

    expect(refreshes()).toHaveLength(2)
  })

  describe('with a workspace switch', () => {
    // Switching rotates the refresh cookie exactly as renewal does, so a switch
    // and a renewal in flight together are the same replay by another route.

    /** Answers both cookie-spending routes slowly, noting if two were ever open at once. */
    function answerSlowly(): { overlapped: boolean } {
      const seen = { overlapped: false }
      let open = 0
      const answer = (reply: TokenPair) => async () => {
        open += 1
        if (open > 1) seen.overlapped = true
        await delay(20)
        open -= 1
        return HttpResponse.json(reply)
      }
      server.use(
        http.post(`${AUTH_URL}/api/v1/auth/refresh`, answer(pair(HOME))),
        http.post(`${AUTH_URL}/api/v1/auth/switch-workspace`, answer(pair(AWAY))),
      )
      return seen
    }

    beforeEach(async () => {
      auth.refresh(pair(HOME))
      await session.restore()
    })

    it('waits for a renewal in flight before switching', async () => {
      const seen = answerSlowly()

      await Promise.all([session.restore(), session.changeWorkspace(AWAY)])

      expect(seen.overlapped).toBe(false)
      expect(signedInSession(session).activeWorkspaceId).toBe(AWAY)
    })

    it('lets a renewal that starts mid-switch share the switch', async () => {
      const seen = answerSlowly()

      await Promise.all([session.changeWorkspace(AWAY), session.restore()])

      expect(seen.overlapped).toBe(false)
      expect(signedInSession(session).activeWorkspaceId).toBe(AWAY)
    })
  })
})

describe('updateProfile', () => {
  const RENAMED: Profile = { ...PROFILE, displayName: 'Ada L' }

  it('replaces the signed-in profile and tells listeners', async () => {
    auth.refresh(pair(HOME))
    await session.restore()
    const listener = vi.fn()
    session.subscribe(listener)

    session.updateProfile(RENAMED)

    expect(signedInSession(session).profile).toEqual(RENAMED)
    expect(listener).toHaveBeenCalled()
    // Only the profile moved: the token and workspaces are the session's own.
    expect(signedInSession(session).accessToken).toBe(tokenFor(HOME))
    expect(signedInSession(session).workspaces).toEqual(WORKSPACES)
  })

  it('ignores a profile that is not the signed-in user’s', async () => {
    auth.refresh(pair(HOME))
    await session.restore()

    session.updateProfile({ ...RENAMED, id: 'user-grace' })

    expect(signedInSession(session).profile).toEqual(PROFILE)
  })

  it('does nothing while signed out', async () => {
    auth.problem('post', '/api/v1/auth/refresh', 401, { title: 'Unauthorized' })
    await session.restore()
    const before = session.snapshot()

    session.updateProfile(RENAMED)

    expect(session.snapshot()).toBe(before)
  })
})

describe('a rename racing a renewal or a switch', () => {
  const RENAMED: Profile = { ...PROFILE, displayName: 'Ada L' }
  const meCalls = () => requests().filter((r) => r.url.pathname === '/api/v1/users/me')

  function held() {
    let release!: (profile: Profile) => void
    const promise = new Promise<Profile>((resolve) => {
      release = resolve
    })
    return { promise, release }
  }

  it('keeps the new name when a renewal’s answer predates the rename', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    auth.refresh(pair(HOME, 120, 'first'))
    await session.restore()
    const gate = held()
    auth.meBy(() => gate.promise)
    auth.refresh(pair(HOME, 120, 'renewed'))
    await vi.advanceTimersByTimeAsync(60_000)
    // The renewal is now waiting on `me`, which answered before the PATCH committed.
    await vi.waitFor(() => expect(meCalls()).toHaveLength(2))

    session.updateProfile(RENAMED)
    gate.release(PROFILE)

    await vi.waitFor(() =>
      expect(signedInSession(session).accessToken).toBe(tokenFor(HOME, 'renewed')),
    )
    expect(signedInSession(session).profile.displayName).toBe('Ada L')
  })

  it('keeps the new name when a workspace switch’s answer predates the rename', async () => {
    auth.refresh(pair(HOME))
    await session.restore()
    const gate = held()
    auth.meBy(() => gate.promise)
    auth.switchWorkspace(pair(AWAY))
    const switching = session.changeWorkspace(AWAY)
    await vi.waitFor(() => expect(meCalls()).toHaveLength(2))

    session.updateProfile(RENAMED)
    gate.release(PROFILE)
    await switching

    expect(signedInSession(session).activeWorkspaceId).toBe(AWAY)
    expect(signedInSession(session).profile.displayName).toBe('Ada L')
  })

  it('adopts what a renewal fetches when it started after the rename', async () => {
    // The guard’s positive: an edit made before a renewal begins must not freeze
    // the profile, or a rename made in another tab would never arrive.
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    auth.refresh(pair(HOME, 120, 'first'))
    await session.restore()
    session.updateProfile(RENAMED)
    auth.meBy(() => ({ ...PROFILE, displayName: 'Ada M' }))
    auth.refresh(pair(HOME, 120, 'renewed'))

    await vi.advanceTimersByTimeAsync(60_000)

    await vi.waitFor(() =>
      expect(signedInSession(session).accessToken).toBe(tokenFor(HOME, 'renewed')),
    )
    expect(signedInSession(session).profile.displayName).toBe('Ada M')
  })
})

describe('the return path', () => {
  const RETURN_KEY = 'collabhub.returnPath'
  const assign = vi.fn()

  beforeEach(() => {
    assign.mockReset()
    vi.stubGlobal('location', { ...window.location, assign })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('is kept by signIn and handed back once', async () => {
    await session.signIn('dex', '/settings')

    expect(window.sessionStorage.getItem(RETURN_KEY)).toBe('/settings')
    expect(session.takeReturnPath()).toBe('/settings')
    expect(session.takeReturnPath()).toBeNull()
    expect(window.sessionStorage.getItem(RETURN_KEY)).toBeNull()
  })

  it('keeps a path with a query', async () => {
    await session.signIn('dex', '/search?q=zeppelin')

    expect(session.takeReturnPath()).toBe('/search?q=zeppelin')
  })

  it.each(['//evil.example/phish', 'https://evil.example/', 'settings'])(
    'refuses %j as a place to return to',
    async (target) => {
      await session.signIn('dex', target)

      expect(session.takeReturnPath()).toBeNull()
    },
  )

  it('is overwritten by the next signIn, and cleared when that one names none', async () => {
    await session.signIn('dex', '/settings')
    await session.signIn('dex', '/search?q=a')
    expect(session.takeReturnPath()).toBe('/search?q=a')

    await session.signIn('dex', '/settings')
    await session.signIn('dex')
    expect(session.takeReturnPath()).toBeNull()
  })

  it('survives a sign-in that completes, for the callback to take', async () => {
    auth.exchange(pair(HOME))
    await session.signIn('dex', '/settings')

    const completed = await session.completeSignIn(new URLSearchParams('code=the-code'))

    expect(completed).toBe(true)
    expect(session.takeReturnPath()).toBe('/settings')
  })

  describe('after a sign-in that fails', () => {
    // Each `return false` of completeSignIn: a failed attempt from /settings must
    // not send a later plain sign-in there.
    it('forgets it when the identity provider refused', async () => {
      await session.signIn('dex', '/settings')

      await session.completeSignIn(new URLSearchParams('error=access_denied'))

      expect(session.takeReturnPath()).toBeNull()
    })

    it('forgets it when the code arrived without this tab’s verifier', async () => {
      await session.signIn('dex', '/settings')
      window.sessionStorage.removeItem(VERIFIER_KEY)

      const completed = await session.completeSignIn(new URLSearchParams('code=abc'))

      expect(completed).toBe(false)
      expect(session.takeReturnPath()).toBeNull()
    })

    it('forgets it when the exchange fails', async () => {
      await session.signIn('dex', '/settings')
      auth.problem('post', '/api/v1/auth/token', 400, { title: 'Bad request', detail: 'No.' })

      const completed = await session.completeSignIn(new URLSearchParams('code=abc'))

      expect(completed).toBe(false)
      expect(session.takeReturnPath()).toBeNull()
    })
  })
})

describe('signIn', () => {
  it('keeps the verifier and sends the browser to Auth with its challenge', async () => {
    const assign = vi.fn()
    vi.stubGlobal('location', { ...window.location, assign })

    await session.signIn('dex')

    const verifier = window.sessionStorage.getItem(VERIFIER_KEY)
    expect(verifier).toMatch(/^[A-Za-z0-9_-]{43}$/)
    const target = new URL(assign.mock.calls[0][0] as string)
    expect(target.pathname).toBe('/api/v1/auth/login/dex')
    expect(target.searchParams.get('codeChallengeMethod')).toBe('S256')
    expect(target.searchParams.get('codeChallenge')).toMatch(/^[A-Za-z0-9_-]{43}$/)
    vi.unstubAllGlobals()
  })
})
