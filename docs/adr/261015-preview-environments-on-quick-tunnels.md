# Preview environments are a k3d namespace per branch, public on two cloudflared quick tunnels

- **Status:** Accepted
- **Date:** 2026-10-15

## Context

A branch could only be seen on the developer's own laptop at `*.localhost`. Issue 6 lets
`scripts/deploy.sh preview up` put a branch's whole app on a public URL so someone on another
network can use it. It builds on D40 (an instance is its `APP_ORIGIN` and `NAMESPACE`), D41
(the dependency chart serves any environment) and D22 (the refresh cookie needs the SPA and API
on one site). Three things needed deciding: how the cluster is exposed, how object storage is
reached, and how Socket.IO's origin check behaves behind a TLS-terminating proxy.

## Decision

- **Quick tunnels, started on the host by the script.** Two `cloudflared tunnel --url
  http://localhost:8080` processes, one for the app and one for object storage. No account, no
  stable hostname; a rerun reuses live tunnels and otherwise starts new ones, so URLs (and the
  issuer in every token) change and users sign in again.
- **A second tunnel for object storage**, not a path on the app's host. A presigned URL's host
  is part of its signature and the app's host routes to the SPA. `OBJECT_STORE_ORIGIN` reaches
  the dependency chart as `objectStoreOrigin` (the Garage Ingress host) and Asset as
  `OBJECT_STORE_PUBLIC_ENDPOINT`; unset, both stay `s3.<APP_ORIGIN host>`.
- **Messaging's `CORS_ALLOWED_ORIGINS` is always `[APP_ORIGIN]`, set by the chart** from a
  required `origin` value. k3s's Traefik says `X-Forwarded-Proto: http`/`ws` even when the
  browser arrived over https, so the empty-list same-origin predicate rebuilds the wrong
  scheme and refuses the handshake. An explicit list is compared as given.
- **Names.** `preview-<slug>` in 63 characters, cut and suffixed with a hash of the branch;
  state in `<git common dir>/collabhub-previews/<namespace>/`.

## Consequences

- Anyone with a preview URL can sign in as a demo user (k3d's throwaway credentials). Accepted.
- Tunnels are never watched; a dead one is noticed on the next `up`. "Dead" includes a running
  `cloudflared` whose tunnel Cloudflare has deleted — what a laptop's sleep does to a quick
  tunnel, found on the first real run — so liveness asks each URL as well as each process.
- The empty-list predicate remains the answer for a deployment that sets no list, but the chart
  no longer takes that path.
- Two `up` runs at once, or `up` racing `down`, are unsupported (both upgrade KEDA).
- Branches that differ only in separators share one preview.

## Alternatives Considered

- **`cloudflared` in the cluster, or a named tunnel:** needs an account and a credential in the
  cluster; neither is wanted for a throwaway preview.
- **Object storage on a path of the app's host:** breaks presigned-URL signatures.
- **Fixing the scheme in Traefik's configuration:** outside the chart, and it would not be
  visible to lint or to a render test.
