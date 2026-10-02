/**
 * Where the SPA's API calls go.
 *
 * Deployed, the SPA and every public API share one origin behind an ingress, so
 * the image is built with each `VITE_*_URL` set to an empty string and every
 * call is relative to the page. One image then serves any environment (register
 * D40). The Compose stacks and the Vite dev server are the exception — the SPA
 * and the APIs are on different ports there — so they set the URLs explicitly,
 * and Vitest, which sets nothing, gets the dev fallbacks.
 */

/**
 * `undefined` means the variable was never set, which is the dev server and
 * Vitest. An empty string is a deliberate "same origin", so it is kept — which
 * is why this is not `value || devFallback`.
 */
export function baseUrlFrom(value: string | undefined, devFallback: string): string {
  if (value === undefined) {
    return devFallback
  }
  return value.replace(/\/+$/, '')
}

export const AUTH_URL: string = baseUrlFrom(import.meta.env.VITE_AUTH_URL, 'http://localhost:8001')

export const MESSAGING_URL: string = baseUrlFrom(
  import.meta.env.VITE_MESSAGING_URL,
  'http://localhost:8002',
)

/**
 * Asset's public routes: `upload-url` and `confirm`. The bytes themselves go to
 * object storage on a presigned URL and never through here, and a download URL
 * comes from Messaging, so this is only the handshake.
 */
export const ASSET_URL: string = baseUrlFrom(import.meta.env.VITE_ASSET_URL, 'http://localhost:8004')
