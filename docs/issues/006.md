Issue: 6

# Issue 6 — Preview environments on k3d, public through Cloudflare quick tunnels

## Summary

A developer runs `scripts/deploy.sh preview up` on any branch and gets the whole app — sign-in,
REST, Socket.IO, attachments, search — on a public `https://…trycloudflare.com` URL, deployed
into its own namespace on the local k3d cluster. Several previews run side by side, each on its
own URLs. `preview down` removes one without touching the others. Separately, the SPA's sign-in
page stops showing the demo credentials.

## Services touched

**Scripts, both charts and the SPA** — no service code changes. Read `scripts/deploy.sh` (its
header, `resolve_origin`, `cmd_infra`, `cmd_app`, `check_origin`), `scripts/lib/common.sh`
(`origin_host`, `origin_s3_endpoint`), `charts/collabhub/templates/ingress.yaml`,
`charts/collabhub-deps/templates/garage.yaml`, `docs/design/04-asset-service.md` §3 (presigned
URLs), `docs/design/00-platform-conventions.md` §5.6 and §6, and
`docs/adr/260916-per-environment-values-and-an-opt-in-ingress.md`.

## What exists already

- **Several instances on one k3d cluster** (D40): `NAMESPACE` and `APP_ORIGIN` identify an
  instance (`deploy.sh:15-19`); both charts are namespace-clean, with no cluster-scoped resource
  except the shared KEDA install that `cmd_infra` upgrades on every run (`deploy.sh:98-101`).
  `resolve_origin` already accepts `https://`.
- **Everything origin-shaped comes from `APP_ORIGIN`**, never from a request: `AUTH_ISSUER`,
  `SPA_REDIRECT_URI`, the Ingress host, Dex's issuer `{origin}/dex` and redirect URI, Garage's
  bucket CORS (`GARAGE_CORS_ORIGINS`), and `OBJECT_STORE_PUBLIC_ENDPOINT`, which
  `origin_s3_endpoint` derives as `scheme://s3.<host>[:port]` (`common.sh:110-115`). The Garage
  Ingress in `collabhub-deps` is on that same `s3.<host>`.
- **Presigned URLs** are SigV4, path-style, signed by Asset's public boto3 client for
  `OBJECT_STORE_PUBLIC_ENDPOINT`; the browser PUTs, shows (`<img src>`) and downloads straight
  from Garage (`asset/object_store.py`, `features/attachments/`).
- **The Socket.IO origin check** (`shared/cors.py:64-106`): an explicit `CORS_ALLOWED_ORIGINS`
  list is used as-is; an empty one (every environment today) becomes a predicate that rebuilds
  `scheme://host` from `X-Forwarded-Proto`/`X-Forwarded-Host` and requires an exact match.
- **The refresh cookie** is `Secure` on k3d (only the lab drops it, D42); behind an https tunnel
  it works unchanged. No CSP is set anywhere; the SPA is built same-origin.
- **The sign-in hint** — "Locally this is Dex — try `ada@collabhub.dev` with the password
  `collabhub`" — is in the SPA, `src/frontend/src/App.tsx:45-48`, with no environment guard. Dex
  serves its stock login page; nothing in the repo themes it.
- **Chart checks at lint time**: `scripts/test.sh` `layer_lint` runs `helm template` and asserts
  on the output (the Ingress host, the refused empty host). There are no tests of bash functions.
- No CI workflow exists (no `.forgejo/`, `.github/`); no file mentions cloudflared.

## Requirements

1. **Named from the branch.** `preview up` deploys to namespace `preview-<slug>`, where `<slug>`
   is the current branch lowercased, every character outside `[a-z0-9]` replaced by `-`, runs of
   `-` collapsed and leading/trailing `-` trimmed. When the whole name would exceed 63 characters
   it is cut, and only then suffixed `-<first 6 hex of sha1(branch)>` within the 63. `BRANCH=`
   overrides the checkout's branch. A detached HEAD with no `BRANCH` is refused. `main` is allowed.
2. **Two tunnels.** `preview up` starts two `cloudflared` quick tunnels as background processes on
   the host, both to the k3d load balancer (`http://localhost:8080`): one gives `APP_ORIGIN`, the
   other `OBJECT_STORE_ORIGIN`. It refuses to run without `cloudflared` on the `PATH`.
3. **The whole app, per namespace, in one command.** `preview up` first builds and pushes the
   checkout's images (`scripts/build.sh --push`, at the usual `IMAGE_TAG` — the short SHA, plus
   `-dirty` for uncommitted changes), then deploys `collabhub-deps` (with
   `values-k3d.yaml`) and `collabhub` into the preview's namespace with those two origins —
   Elasticsearch and the Worker included. It runs only on the `k3d-collabhub` context, and creates
   or starts the cluster if needed, as `up` does.
4. **A separate object-store origin.** When `OBJECT_STORE_ORIGIN` is set, it is
   `OBJECT_STORE_PUBLIC_ENDPOINT` and the Garage Ingress host. When it is not set, both are
   `s3.<APP_ORIGIN host>` exactly as today, so plain k3d and the lab do not change.
5. **Socket.IO behind TLS.** The `collabhub` chart sets Messaging's `CORS_ALLOWED_ORIGINS` to
   `[APP_ORIGIN]` in every environment, so the handshake is checked against the configured origin
   and not a rebuilt one.
6. **A rerun of `up`.** If both of the preview's tunnels are still running, `up` reuses them: same
   URLs, same data, the checkout's newly built images rolled out. If either is dead, it stops the other, starts two new
   tunnels and redeploys both charts with the new origins; the data is kept.
7. **`preview url`** prints the preview's two URLs, or says its tunnels are not running.
8. **`preview down`** stops the preview's two tunnels, uninstalls both releases and deletes its
   namespace — and nothing else: not KEDA, not the cluster, not another instance. On a preview
   that does not exist, or whose tunnels are already dead, it does what is left and succeeds.
9. **No credentials on the sign-in page.** The SPA's sign-in page shows no email address and no
   password, in any environment. `deploy.sh`'s console message after a k3d deploy keeps printing
   them.

## Where the rules meet

- **A new URL and signed-in users (R6, R2):** new tunnels mean a new `APP_ORIGIN`, so a new token
  issuer and a new cookie site. Everyone signed in to that preview signs in again; messages and
  attachments are still there (Postgres and Garage keep their volumes).
- **Previews and other instances (R3, R8):** previews coexist with the developer's own
  `collabhub` namespace on `localhost:8080` and with each other, told apart by Host. Two `up` runs
  at the same time are **not supported** — both `helm upgrade` the shared KEDA release. The
  README says so; the script does not lock.
- **Two branches, one slug (R1):** `feature/a_b` and `feature/a-b` share a preview. Accepted,
  and documented.
- **The CORS list everywhere (R5):** a non-empty list also installs Messaging's REST
  `CORSMiddleware` for that one origin — harmless for a same-origin SPA. Garage's bucket CORS
  stays `APP_ORIGIN`: the browser's origin is the app's, whichever host it uploads to.

## Paths each rule holds on

| Path | What must be true |
|---|---|
| First `up` on a branch | namespace created, two new URLs, both charts installed, `check_origin` passes through the public URL |
| `up` again after a push, tunnels alive | same URLs, data kept, new images running, migrations run |
| `up` after a reboot or sleep, tunnels dead | new URLs, both charts redeployed with them, data kept |
| `up` that failed after the URLs appeared | tunnels left running; the next `up` reuses them |
| A second preview while the first runs | each on its own URLs; neither sees the other's data or accepts its tokens |
| Plain `deploy.sh up` (no preview) | unchanged: `http://localhost:8080`, S3 on `s3.localhost:8080` |
| The lab | unchanged, except Messaging's CORS list (R5) |
| Upload, inline image, download in a preview | all go to `OBJECT_STORE_ORIGIN` and succeed |
| Socket.IO in a preview | the handshake over `wss://` is accepted; live messages arrive |

## What this assumes — check before building on it

- **cloudflared forwards the browser's `Host` header unchanged** to `http://localhost:8080` when
  no `--http-host-header` is given. Everything rests on it: the Ingress rules match on Host, and
  a SigV4 signature covers the Host Garage receives. If it is false, the plan stops here.
- **A quick tunnel's URL appears in cloudflared's output** as `https://<words>.trycloudflare.com`
  within seconds, so the script can read it. Check the installed version's output format.
- **k3s's Traefik overwrites `X-Forwarded-Proto` with `http`/`ws`** for traffic from the
  load balancer, which is why R5 is needed. R5 is right whether or not this holds.
- **A new trycloudflare hostname may take seconds to resolve.** `check_origin`'s 30 retries at 2s
  are assumed to cover it.

## Timing

The order of a first `up`, and what a failure leaves behind:

```
t-1     scripts/build.sh --push for the checkout → a build failure stops here; no tunnel started
t0      start tunnel A (app) and tunnel B (object store) in the background;
        record their PIDs and log paths in the preview's state directory
t0..30s read each tunnel's URL from its output
        → either missing at 30s: stop both, fail; nothing deployed
t1      cmd_infra  with APP_ORIGIN=A, OBJECT_STORE_ORIGIN=B (Garage Ingress on B's host)
t2      cmd_app    with the same two origins
t3      check_origin through A (retries cover DNS for a new hostname)
t4      print A and B
        → a failure at t1..t3 leaves both tunnels running and recorded; a rerun reuses them
```

## Decided already

1. Scope is R1–R9. Everything in *Not in this issue* stays out.
2. Quick tunnels, no Cloudflare account; cloudflared runs on the host, started by the script.
3. Tunnel restarts are not watched for; R6 handles a dead tunnel on the next `up`.
4. A preview uses `values-k3d.yaml` and its throwaway credentials — no new `DEPLOY_ENV`.
5. **Accepted risk:** anyone who has a preview's URL can sign in as the demo users, whose password
   is in the repo. Previews are short-lived and hold throwaway data.
6. The Socket.IO fix is in the chart (R5), not Traefik configuration.
7. This depends on no 🔴 register entry. It builds on D40, D41 and D22 (all 🟢); D42 is
   untouched, because a preview is https and keeps `Secure`.

Left to the plan, on purpose: where the state directory lives (gitignored), how the slug code is
shaped for testing, the name of the chart value behind `OBJECT_STORE_ORIGIN`, and how `up`
detects a live tunnel.

## Tests

- **Lint layer** (`helm template` checks in `scripts/test.sh`): Messaging's
  `CORS_ALLOWED_ORIGINS` is `[origin]`; with an object-store origin, the Garage Ingress host and
  `OBJECT_STORE_PUBLIC_ENDPOINT` come from it; without one, both are still `s3.<host>`.
- **Bash**: the slug rule — the substitutions, the cut and the hash suffix only when cut, the
  63-character limit, a detached HEAD refused without `BRANCH` — in a small test `scripts/test.sh
  lint` runs.
- **Unit (pytest)**: the Socket.IO origin check accepts `https://X` from an explicit list when
  `X-Forwarded-Proto` is `ws`.
- **Vitest**: the sign-in page shows no email address and no password.
- **No BDD journey.** A real tunnel cannot run headless; the first real run below is the proof.

## Record in this slice

- Register: **D45 🟢** — preview environments: a k3d instance per branch on two quick tunnels.
- An ADR: host-side quick tunnels, and a second tunnel for object storage rather than a path.
- `docs/platform/versions.md`: a cloudflared entry.
- Doc 04: the object store's public endpoint can be set apart from `APP_ORIGIN`.
- Conventions §5.6: Messaging's CORS list is always set, and why.
- README: a preview section (the commands, the cost — roughly 1.5–2 GB per preview, most of it
  Elasticsearch — no concurrent `up`, and the accepted sign-in risk). The `deploy.sh` header.

## Not in this issue

- A CI or PR workflow that calls `preview up`/`down`.
- Named tunnels, stable hostnames, Cloudflare Access, per-preview passwords.
- Watching or restarting tunnels; cleaning up previews of deleted branches.
- A lock against concurrent `up` runs.
- Previews on any cluster but local k3d.

## Acceptance — first real run on k3d

With two branches checked out in two worktrees, and Ada and Grace in two browsers on another
network (a phone off Wi-Fi will do):
- `preview up` on branch A prints two URLs; Ada signs in through Dex on the app URL, and the
  sign-in page shows no credentials.
- Ada and Grace chat: messages arrive live both ways (Socket.IO over `wss://`).
- Ada uploads an image and a PDF; Grace sees the image inline and downloads the PDF.
- `preview up` on branch B: a second pair of URLs; A's data is not visible there.
- Push to A and `up` again: same URLs, data kept. Kill A's tunnels and `up` again: new URLs,
  sign in again, data kept.
- `preview down` on A: B and the developer's own `collabhub` instance still work.

## References

- `docs/adr/260916-per-environment-values-and-an-opt-in-ingress.md` (D40, D41, D42)
- `docs/design/04-asset-service.md` §3; `docs/design/00-platform-conventions.md` §5.6, §6
- `scripts/deploy.sh`, `scripts/lib/common.sh`, `scripts/test.sh` (`layer_lint`)
- `src/services/shared/shared/cors.py`; `src/frontend/src/App.tsx`
