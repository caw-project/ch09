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
const RETURN_KEY = 'collabhub.returnPath'

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

  it('remembers a return path and forgets an old one', async () => {
    const assign = vi.fn()
    vi.stubGlobal('location', { ...window.location, assign })
    try {
      await session.signIn('dex', '/settings')
      expect(window.sessionStorage.getItem(RETURN_KEY)).toBe('/settings')
      expect(assign).toHaveBeenCalledTimes(1)

      // A later sign-in that names no path must not inherit the earlier one.
      await session.signIn('dex')
      expect(window.sessionStorage.getItem(RETURN_KEY)).toBeNull()
      expect(assign).toHaveBeenCalledTimes(2)
    } finally {
      vi.unstubAllGlobals()
    }
  })
})

describe('takeReturnPath', () => {
  it('hands back a stored path once', () => {
    window.sessionStorage.setItem(RETURN_KEY, '/settings?tab=profile')

    expect(session.takeReturnPath()).toBe('/settings?tab=profile')
    expect(window.sessionStorage.getItem(RETURN_KEY)).toBeNull()
    expect(session.takeReturnPath()).toBe('/')
  })

  it('is home when nothing was stored', () => {
    expect(session.takeReturnPath()).toBe('/')
  })

  it.each([
    ['a protocol-relative URL', '//evil.example'],
    ['an absolute URL', 'https://evil.example'],
    ['a backslash path', '/\\evil'],
    ['a relative path', 'settings'],
  ])('refuses %s, and still forgets it', (_, stored) => {
    window.sessionStorage.setItem(RETURN_KEY, stored)

    expect(session.takeReturnPath()).toBe('/')
    expect(window.sessionStorage.getItem(RETURN_KEY)).toBeNull()
  })
})

describe('updateProfile', () => {
  const RENAMED: Profile = { ...PROFILE, displayName: 'Ada L' }

  it('replaces the profile and notifies', async () => {
    auth.refresh(pair(HOME))
    await session.restore()
    const listener = vi.fn()
    session.subscribe(listener)

    session.updateProfile(RENAMED)

    expect(signedInSession(session).profile).toEqual(RENAMED)
    expect(listener).toHaveBeenCalledTimes(1)
  })

  it('ignores another user’s profile and a signed-out state', async () => {
    const listener = vi.fn()
    session.subscribe(listener)

    // Not signed in yet: the store is still loading.
    session.updateProfile(RENAMED)
    expect(session.snapshot()).toEqual({ status: 'loading' })

    auth.refresh(pair(HOME))
    await session.restore()
    listener.mockClear()
    session.updateProfile({ ...RENAMED, id: 'user-grace', displayName: 'Grace' })
    expect(signedInSession(session).profile).toEqual(PROFILE)
    expect(listener).not.toHaveBeenCalled()

    // The positive: the same id, and it takes effect.
    session.updateProfile(RENAMED)
    expect(signedInSession(session).profile).toEqual(RENAMED)

    auth.logout()
    await session.signOut()
    listener.mockClear()
    session.updateProfile({ ...RENAMED, displayName: 'Too late' })
    expect(session.snapshot()).toEqual({ status: 'signedOut', error: undefined })
    expect(listener).not.toHaveBeenCalled()
  })

  it('a switch in flight over a rename keeps the new name, and one without adopts the fetched', async () => {
    // Call 1 is the restore. Call 2 — the switch's own read — is held, and answers
    // with the name as it was before the rename. Call 3 is a second switch.
    let release!: () => void
    const held = new Promise<void>((resolve) => {
      release = resolve
    })
    auth.meBy(async (call) => {
      if (call === 2) {
        await held
        return PROFILE
      }
      return call === 1 ? PROFILE : { ...PROFILE, displayName: 'Ada Elsewhere' }
    })
    auth.refresh(pair(HOME))
    await session.restore()
    auth.switchWorkspace(pair(AWAY))

    const switching = session.changeWorkspace(AWAY)
    await vi.waitFor(() =>
      expect(requests().filter((r) => r.url.pathname === '/api/v1/users/me')).toHaveLength(2),
    )
    session.updateProfile(RENAMED)
    release()
    await switching

    expect(signedInSession(session).activeWorkspaceId).toBe(AWAY)
    expect(signedInSession(session).profile.displayName).toBe('Ada L')

    // The other side: a switch during which nobody renamed takes what it fetched.
    auth.switchWorkspace(pair(HOME))
    await session.changeWorkspace(HOME)

    expect(signedInSession(session).activeWorkspaceId).toBe(HOME)
    expect(signedInSession(session).profile.displayName).toBe('Ada Elsewhere')
  })
})
