/**
 * The one secret the browser tab has to keep. **Register D22 is settled.**
 *
 * D22 — "refresh-token storage: HttpOnly cookie vs. in-app secure storage" — was
 * decided on 2026-07-28 in favour of the cookie. So the refresh token is *not*
 * here, and cannot be: it is set by the Auth service with `HttpOnly`, which
 * means no code in this application can read it, including this file. The
 * browser attaches it to `/api/v1/auth` requests and that is the whole of the
 * SPA's involvement.
 *
 * What is left:
 *
 * - **The access token** lives in a variable in `session.ts` and dies with the
 *   tab. Short-lived and re-obtainable, so persisting it would add exposure and
 *   buy nothing.
 * - **The PKCE verifier** is here, in `sessionStorage`, because it has to
 *   survive a full-page redirect to the identity provider and back — a variable
 *   cannot. It is readable by any script on the origin, which is acceptable in a
 *   way the refresh token was not: it is single-use, lives for the seconds
 *   between leaving and returning, is useless without the matching authorization
 *   code, and is deleted before that code is spent.
 * - **The return path** is a second short-lived `sessionStorage` key, for the
 *   same reason: the route a signed-out visitor asked for must survive the
 *   redirect to the provider. It is only ever a path on this origin.
 */

const VERIFIER_KEY = 'collabhub.pkceVerifier'
const RETURN_KEY = 'collabhub.returnTo'

function read(key: string): string | null {
  try {
    return window.sessionStorage.getItem(key)
  } catch {
    // Storage can throw in private modes and sandboxed frames. A sign-in that
    // cannot be resumed is better than a page that will not render.
    return null
  }
}

function write(key: string, value: string): void {
  try {
    window.sessionStorage.setItem(key, value)
  } catch {
    /* see read() */
  }
}

function clear(key: string): void {
  try {
    window.sessionStorage.removeItem(key)
  } catch {
    /* see read() */
  }
}

/**
 * The PKCE verifier, held only between leaving for the provider and coming back.
 * Cleared as soon as it is spent — it is single-use, and a verifier left behind
 * is one that outlives the code it protects.
 */
export const pkceVerifier = {
  read: () => read(VERIFIER_KEY),
  write: (verifier: string) => write(VERIFIER_KEY, verifier),
  clear: () => clear(VERIFIER_KEY),
}

/**
 * Whether `path` is somewhere to go after signing in: a plain path on this
 * origin, and not a page that would just bounce the visitor back.
 *
 * What is stored is navigated to, so this is an open-redirect surface:
 * `//host` and `/\host` are read by browsers as another origin, and anything
 * without a leading slash could be a full URL.
 */
function isReturnable(path: string): boolean {
  if (!path.startsWith('/') || path.startsWith('//') || path.startsWith('/\\')) return false
  const [pathname] = path.split(/[?#]/)
  return pathname !== '/sign-in' && !pathname.startsWith('/auth/callback')
}

/**
 * The route a signed-out visitor asked for, held across the round trip to the
 * identity provider so sign-in can land them there instead of at `/`. A second
 * short-lived key beside the verifier, for the same reason: it has to survive a
 * full-page redirect. Taken once, and checked again on the way out in case
 * something else wrote the key.
 */
export const returnPath = {
  /** Remember `path`; `null` or `undefined` forgets what was remembered. */
  write: (path: string | null | undefined) => {
    if (path && isReturnable(path)) write(RETURN_KEY, path)
    else clear(RETURN_KEY)
  },
  /** Read and clear. `null` when nothing valid was held. */
  take: (): string | null => {
    const path = read(RETURN_KEY)
    clear(RETURN_KEY)
    return path !== null && isReturnable(path) ? path : null
  },
}
