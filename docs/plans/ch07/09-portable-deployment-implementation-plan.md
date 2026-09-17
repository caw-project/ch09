# Portable Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy any number of CollabHub instances — k3d or a lab cluster — from one set of images, each identified only by `APP_ORIGIN` and `NAMESPACE`, with every credential suppliable through `--set-string`.

**Architecture:** The SPA calls its APIs relative to the page origin, so the frontend image no longer belongs to an environment. `charts/collabhub` gains an opt-in Ingress whose public-route allow-list lives in the template, with the host coming from `APP_ORIGIN`. `charts/collabhub-local` becomes `charts/collabhub-deps`, with every credential a required scalar value and per-environment values files. `scripts/deploy.sh` selects an environment with `DEPLOY_ENV`, an instance with `NAMESPACE`, and derives every origin-dependent setting from `APP_ORIGIN`.

**Tech Stack:** Helm 3, k3d/k3s (Traefik), ingress-nginx (lab), bash 3.2, Vite + React + Vitest, Python 3.12 + pytest + httpx, Garage v2.3.0, Dex v2.45.1.

**Spec:** `docs/plans/ch07/08-portable-deployment-design.md`

## Global Constraints

- **Never commit.** No `git add`, no `git commit`, no PR. Leave the worktree dirty; committing is the user's.
- **Work only in the worktree** `/Users/elton/scm/manning/caw-portable-deploy` on branch `feature/portable-deployment`. Every path below is relative to it.
- **Stop at red.** New behaviour gets its failing test first; run it, see it fail for the stated reason, then **stop for review** before writing the production change (CLAUDE.md, register D32).
- **Record decisions in the slice that makes them** — register row, ADR, CLAUDE.md — not in a sweep at the end.
- Scripts are **bash 3.2**: no associative arrays; expand a possibly-empty array as `${arr[@]+"${arr[@]}"}`.
- **`--set-string`, never `--set`**, for anything derived from `APP_ORIGIN` or any credential.
- `APP_ORIGIN` is `scheme://host[:port]` with no path and no trailing slash.
- No hostname is written into any values file. The k3d default origin is `http://localhost:8080`.
- The lab's ingress controller is **ingress-nginx** (`className: nginx`); k3d's is **Traefik** (`className: traefik`).
- The lab is plain HTTP, so its Auth runs `AUTH_COOKIE_SECURE: "false"`. k3d instances on `*.localhost` keep the default `true`.
- The Ingress must never route `/api/v1/internal/` or `/health` (Conventions §5.5).
- Run `ruff check` / `ruff format` on Python, and let the lint hook run on `.ts`. A blocking hook finding is fixed, never bypassed.
- The next free register IDs are **D40, D41, D42**. ADRs are dated `260916-`.

## File map

| File | Responsibility | Task |
|---|---|---|
| `src/frontend/src/lib/config.ts` (new) | Resolve each API's base URL from `VITE_*`; one place | 1–2 |
| `src/frontend/src/lib/config.test.ts` (new) | `baseUrlFrom` rules | 1 |
| `src/frontend/src/lib/auth/api.ts`, `lib/api/messaging.ts`, `lib/realtime/socket.ts`, `src/test/api.ts` | Import base URLs instead of reading `import.meta.env` | 2 |
| `scripts/build.sh`, `docker/frontend/Dockerfile` | Build the SPA same-origin by default | 3 |
| `src/services/auth/scripts/sign-in.py` | CLI sign-in that works on one origin | 4 |
| `src/services/auth/tests/unit/test_sign_in_script.py` (new) | `idp_root` / `within_idp` rules | 4 |
| `charts/collabhub/templates/ingress.yaml` (new), `values.yaml`, `values-k3d.yaml` | Opt-in public Ingress | 5 |
| `charts/collabhub-local/templates/ingress.yaml` | Shrinks to `/dex`, host from `origin` | 5 |
| `scripts/lib/common.sh`, `scripts/deploy.sh`, `scripts/test.sh`, `.env.example` | `DEPLOY_ENV`, `NAMESPACE`, `APP_ORIGIN`, Helm passthrough, render checks | 5–6, 8–9 |
| `docs/adr/260916-*.md`, `docs/design/07-open-decisions-register.md`, `docs/adr/260914-local-kubernetes-…md`, `CLAUDE.md`, `README.md` | Decisions D40–D42 and the docs they change | 3, 7, 8, 9 |
| `charts/collabhub-deps/**` (renamed from `collabhub-local`) | Dependencies for any environment; credentials required | 8 |
| `charts/collabhub-deps/values-k3d.yaml`, `values-lab.yaml` (new) | Per-environment dependency settings | 8–9 |
| `charts/collabhub/values-lab.yaml` (new) | The lab's app settings | 9 |

---

## Slice 1 — the frontend image stops belonging to an environment

### Task 1: `baseUrlFrom` — failing test

**Files:**
- Test: `src/frontend/src/lib/config.test.ts` (create)

**Interfaces:**
- Produces (for Task 2): `baseUrlFrom(value: string | undefined, devFallback: string): string` exported from `src/frontend/src/lib/config.ts`.

- [ ] **Step 1: Write the failing test**

Create `src/frontend/src/lib/config.test.ts`:

```ts
import { describe, expect, it } from 'vitest'

import { baseUrlFrom } from './config'

describe('baseUrlFrom', () => {
  it('falls back to the dev address when the variable was never set', () => {
    expect(baseUrlFrom(undefined, 'http://localhost:8001')).toBe('http://localhost:8001')
  })

  it('keeps an empty value, so every call is relative to the page origin', () => {
    expect(baseUrlFrom('', 'http://localhost:8001')).toBe('')
  })

  it('uses a value that was set', () => {
    expect(baseUrlFrom('http://localhost:8011', 'http://localhost:8001')).toBe(
      'http://localhost:8011',
    )
  })

  it('drops a trailing slash, which would otherwise double up before /api', () => {
    expect(baseUrlFrom('http://auth.example/', 'http://localhost:8001')).toBe('http://auth.example')
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd src/frontend && npx vitest run src/lib/config.test.ts`
Expected: FAIL — `Failed to resolve import "./config"`.

- [ ] **Step 3: STOP — review checkpoint.** Report the red run and wait for approval before Task 2.

### Task 2: `baseUrlFrom` and one source of base URLs

**Files:**
- Create: `src/frontend/src/lib/config.ts`
- Modify: `src/frontend/src/lib/auth/api.ts:14`, `src/frontend/src/lib/api/messaging.ts:30`, `src/frontend/src/lib/realtime/socket.ts:23`, `src/frontend/src/test/api.ts:23-24`

**Interfaces:**
- Consumes: the test from Task 1.
- Produces: `AUTH_URL: string` and `MESSAGING_URL: string` exported from `src/frontend/src/lib/config.ts`. `src/test/api.ts` keeps exporting `AUTH_URL` and `MESSAGING_URL` under the same names, so existing tests are untouched.

- [ ] **Step 1: Write `config.ts`**

```ts
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
```

- [ ] **Step 2: Run the new test**

Run: `cd src/frontend && npx vitest run src/lib/config.test.ts`
Expected: PASS, 4 tests.

- [ ] **Step 3: Replace the three duplicated reads**

In `src/frontend/src/lib/auth/api.ts`, delete line 14:
```ts
const AUTH_URL: string = import.meta.env.VITE_AUTH_URL ?? 'http://localhost:8001'
```
and add beside the existing `import { problemFrom } from '../api/client'`:
```ts
import { AUTH_URL } from '../config'
```

In `src/frontend/src/lib/api/messaging.ts`, delete line 30:
```ts
const MESSAGING_URL: string = import.meta.env.VITE_MESSAGING_URL ?? 'http://localhost:8002'
```
and add to its imports:
```ts
import { MESSAGING_URL } from '../config'
```

In `src/frontend/src/lib/realtime/socket.ts`, delete line 23:
```ts
const MESSAGING_URL: string = import.meta.env.VITE_MESSAGING_URL ?? 'http://localhost:8002'
```
and add under `import { io, type Socket } from 'socket.io-client'`:
```ts
import { MESSAGING_URL } from '../config'
```

In `src/frontend/src/test/api.ts`, replace lines 23–24:
```ts
export const MESSAGING_URL: string = import.meta.env.VITE_MESSAGING_URL ?? 'http://localhost:8002'
export const AUTH_URL: string = import.meta.env.VITE_AUTH_URL ?? 'http://localhost:8001'
```
with an import grouped with the other `../lib/…` imports, and a re-export:
```ts
import { AUTH_URL, MESSAGING_URL } from '../lib/config'
```
```ts
// The same values the app calls, so a stub cannot drift from the real URL.
export { AUTH_URL, MESSAGING_URL }
```

- [ ] **Step 4: Run the whole SPA suite, lint and types**

Run: `cd src/frontend && npm test && npm run lint && npm run typecheck`
Expected: every Vitest file passes (same count as before plus 4), eslint and tsc clean.

- [ ] **Step 5: Confirm nothing else reads the variables directly**

Run: `grep -rn "import.meta.env.VITE_" src/frontend/src`
Expected: only the two lines in `src/lib/config.ts`.

### Task 3: build the SPA same-origin, prove the bundle, record it

**Files:**
- Modify: `scripts/build.sh:8-10` (header comment), `scripts/build.sh:45-53`
- Modify: `docker/frontend/Dockerfile:14-19` (comment only)
- Modify: `docs/adr/260914-local-kubernetes-on-k3d-with-a-dev-only-dependency-chart.md` (Consequences)

**Interfaces:**
- Consumes: `baseUrlFrom` from Task 2.
- Produces: `scripts/build.sh frontend` builds an image whose bundle is same-origin unless `VITE_*` is exported.

- [ ] **Step 1: Default the build args to empty**

In `scripts/build.sh`, replace the header lines

```bash
# defaults are in scripts/lib/common.sh. The frontend's VITE_* URLs default to
# the k3d origin — override them to build the SPA for somewhere else.
```
with
```bash
# defaults are in scripts/lib/common.sh. The frontend's VITE_* URLs default to
# empty, so the SPA calls every API on its own origin and one image serves any
# environment behind a single ingress. Export them only to build for a stack
# that is not same-origin.
```

and replace the frontend block

```bash
    if [ "$component" = frontend ]; then
        # Vite inlines these into the bundle, so the image belongs to one
        # environment. Behind the k3d Ingress every API is same-origin.
        args+=(
            --build-arg "VITE_AUTH_URL=${VITE_AUTH_URL:-$K3D_ORIGIN}"
            --build-arg "VITE_MESSAGING_URL=${VITE_MESSAGING_URL:-$K3D_ORIGIN}"
            --build-arg "VITE_CANVAS_URL=${VITE_CANVAS_URL:-$K3D_ORIGIN}"
            --build-arg "VITE_ASSET_URL=${VITE_ASSET_URL:-$K3D_ORIGIN}"
        )
    fi
```
with
```bash
    if [ "$component" = frontend ]; then
        # Vite inlines these into the bundle. Empty means "same origin": every
        # call is relative to the page, so the image carries no environment and
        # the Ingress decides where it lives (register D40).
        args+=(
            --build-arg "VITE_AUTH_URL=${VITE_AUTH_URL-}"
            --build-arg "VITE_MESSAGING_URL=${VITE_MESSAGING_URL-}"
            --build-arg "VITE_CANVAS_URL=${VITE_CANVAS_URL-}"
            --build-arg "VITE_ASSET_URL=${VITE_ASSET_URL-}"
        )
    fi
```

- [ ] **Step 2: Update the Dockerfile comment**

In `docker/frontend/Dockerfile`, replace

```dockerfile
# Vite inlines VITE_-prefixed vars at build time, so they are build args rather
# than runtime env. Only non-secret values belong here — they ship in the bundle.
```
with
```dockerfile
# Vite inlines VITE_-prefixed vars at build time, so they are build args rather
# than runtime env. Only non-secret values belong here — they ship in the bundle.
# Empty (scripts/build.sh's default) means same-origin: the SPA calls /api/...
# on whatever host served it. Compose passes explicit URLs because its SPA and
# APIs are on different ports.
```

- [ ] **Step 3: Build and inspect the bundle**

Vite leaves `baseUrlFrom`'s call in place, so the `"http://localhost:8001"` fallback literal is **still in the bundle** — its presence proves nothing. What proves the build is the value inlined beside it: `""` when the build arg arrived empty, `void 0` when it was missing.

Run:
```bash
scripts/build.sh frontend
ref="$(IMAGE_REGISTRY=localhost:5500 bash -c 'source scripts/lib/common.sh; image_ref frontend')"
out="$(mktemp -d)"
cid="$(docker create "$ref")" && docker cp "$cid:/usr/share/nginx/html/assets" "$out" && docker rm "$cid" >/dev/null
grep -ho '("","http://localhost:800[12]")' "$out"/assets/*.js | sort -u
grep -c 'void 0,"http://localhost:800[12]"' "$out"/assets/*.js
```
Expected: the first `grep` prints both `("","http://localhost:8001")` and `("","http://localhost:8002")`; the second prints `0` for every file.

If the minifier has reordered the arguments so neither pattern matches, search for `"http://localhost:8001"` with `grep -o '.\{40\}"http://localhost:8001"'` and read what precedes it — the check is "empty string, not `void 0`", however it is spelled.

- [ ] **Step 4: Amend ADR 260914**

In `docs/adr/260914-local-kubernetes-on-k3d-with-a-dev-only-dependency-chart.md`, replace the paragraph

```markdown
The frontend image is environment-specific: the `VITE_*` URLs are inlined at build
time, and `build.sh` defaults them to the k3d origin.
```
with
```markdown
The frontend image was environment-specific: the `VITE_*` URLs are inlined at
build time, and `build.sh` defaulted them to the k3d origin. **Superseded
2026-09-16** — `build.sh` now defaults them to empty, so the SPA calls its APIs
relative to its own origin and one image serves every single-origin deployment.
See [ADR 260916](260916-per-environment-values-and-an-opt-in-ingress.md).
```

(The ADR it links is written in Task 7; the link is correct once that task lands.)

- [ ] **Step 5: Unit layer still green**

Run: `scripts/test.sh unit`
Expected: pytest and Vitest both pass.

---

## Slice 2 — environments in the scripts, routing in the app chart

### Task 4: `sign-in.py` works on one origin

**Files:**
- Test: `src/services/auth/tests/unit/test_sign_in_script.py` (create)
- Modify: `src/services/auth/scripts/sign-in.py:60-68` (`follow_within`), `:70-95` (`sign_in`)

**Interfaces:**
- Produces (used by Task 10): `sign-in.py --auth-url <APP_ORIGIN> --access-token` prints a token for a single-origin instance. Internally `idp_root(authorize: httpx.URL) -> httpx.URL` and `within_idp(target: httpx.URL, idp: httpx.URL) -> bool`.

- [ ] **Step 1: Write the failing test**

Create `src/services/auth/tests/unit/test_sign_in_script.py`:

```python
"""The command-line sign-in's one real decision: when a redirect has left the IdP.

Behind one ingress, Dex and Auth share a host, so the host alone cannot say
where Dex ends. The script is loaded by path because its file name has a hyphen.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import httpx
import pytest

SCRIPT = Path(__file__).parents[2] / "scripts" / "sign-in.py"


@pytest.fixture(scope="module")
def sign_in() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sign_in", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_idp_is_the_authorize_urls_directory(sign_in: ModuleType) -> None:
    authorize = httpx.URL("http://localhost:5556/dex/auth?client_id=collabhub-auth&state=s")

    assert sign_in.idp_root(authorize) == httpx.URL("http://localhost:5556/dex/")


def test_a_dex_page_on_a_shared_origin_is_inside_the_idp(sign_in: ModuleType) -> None:
    idp = sign_in.idp_root(httpx.URL("http://a.localhost:8080/dex/auth?state=s"))

    assert sign_in.within_idp(httpx.URL("http://a.localhost:8080/dex/auth/local?back=&state=s"), idp)


def test_auths_callback_on_a_shared_origin_has_left_the_idp(sign_in: ModuleType) -> None:
    idp = sign_in.idp_root(httpx.URL("http://a.localhost:8080/dex/auth?state=s"))

    assert not sign_in.within_idp(
        httpx.URL("http://a.localhost:8080/api/v1/auth/callback/dex?code=c&state=s"), idp
    )


def test_another_port_has_left_the_idp(sign_in: ModuleType) -> None:
    idp = sign_in.idp_root(httpx.URL("http://localhost:5556/dex/auth?state=s"))

    assert not sign_in.within_idp(httpx.URL("http://localhost:8001/dex/anything"), idp)


def test_another_host_has_left_the_idp(sign_in: ModuleType) -> None:
    idp = sign_in.idp_root(httpx.URL("http://a.localhost:8080/dex/auth?state=s"))

    assert not sign_in.within_idp(httpx.URL("http://b.localhost:8080/dex/auth/local"), idp)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest -m unit src/services/auth/tests/unit/test_sign_in_script.py -v`
Expected: 5 FAILED, each with `AttributeError: module 'sign_in' has no attribute 'idp_root'`.

- [ ] **Step 3: STOP — review checkpoint.** Report the red run and wait for approval before Step 4.

- [ ] **Step 4: Implement**

In `src/services/auth/scripts/sign-in.py`, replace `follow_within`:

```python
def follow_within(client: httpx.Client, response: httpx.Response, host: str) -> httpx.Response:
    """Follow redirects while they stay on `host`; stop at the first that leaves."""
    while response.status_code in REDIRECTS:
        target = response.url.join(response.headers["location"])
        if target.host != host or target.port != response.url.port:
            return response
        response = client.get(target)
    return response
```
with
```python
def idp_root(authorize: httpx.URL) -> httpx.URL:
    """The IdP as an origin plus a path: Dex's `/dex/auth` makes it everything under `/dex/`.

    The host is not enough. Behind one ingress Dex and Auth share it, and the
    redirect from Dex to Auth's callback leaves Dex only by its path.
    """
    directory = authorize.path.rsplit("/", 1)[0] + "/"
    return httpx.URL(scheme=authorize.scheme, host=authorize.host, port=authorize.port, path=directory)


def within_idp(target: httpx.URL, idp: httpx.URL) -> bool:
    return (
        target.scheme == idp.scheme
        and target.host == idp.host
        and target.port == idp.port
        and target.path.startswith(idp.path)
    )


def follow_within(client: httpx.Client, response: httpx.Response, idp: httpx.URL) -> httpx.Response:
    """Follow redirects while they stay inside the IdP; stop at the first that leaves."""
    while response.status_code in REDIRECTS:
        target = response.url.join(response.headers["location"])
        if not within_idp(target, idp):
            return response
        response = client.get(target)
    return response
```

In `sign_in`, replace

```python
        authorize = started.headers["location"]
        idp_host = urlparse(authorize).hostname

        page = follow_within(client, client.get(authorize), idp_host)
```
with
```python
        authorize = httpx.URL(started.headers["location"])
        idp = idp_root(authorize)

        page = follow_within(client, client.get(authorize), idp)
```
and replace
```python
        final = follow_within(client, submitted, idp_host)
```
with
```python
        final = follow_within(client, submitted, idp)
```

Update the module docstring's last paragraph to say it works against a local stack **or a k3d instance on one origin**, with `--auth-url` set to that origin.

- [ ] **Step 5: Run the tests, then lint**

Run: `uv run pytest -m unit src/services/auth/tests/unit/test_sign_in_script.py -v && uv run ruff check src/services/auth && uv run ruff format --check src/services/auth`
Expected: 5 passed; ruff clean.

- [ ] **Step 6: Still works against Compose**

If the Compose development stack is up (`docker compose ps auth` shows it running), run
`src/services/auth/scripts/sign-in.py --access-token | cut -c1-20`
Expected: the start of a JWT (`eyJ…`). If the stack is not up, say so in the task report rather than starting it.

### Task 5: an opt-in Ingress in `charts/collabhub`

**Files:**
- Create: `charts/collabhub/templates/ingress.yaml`
- Modify: `charts/collabhub/values.yaml` (new `ingress:` block; header comment), `charts/collabhub/values-k3d.yaml` (enable it)
- Modify: `charts/collabhub-local/templates/ingress.yaml` (shrink to `/dex`), `charts/collabhub-local/values.yaml` (`ingress.className`)
- Test: `scripts/test.sh` `layer_lint`

**Interfaces:**
- Produces (for Task 6): values `ingress.enabled`, `ingress.className`, `ingress.host`, `ingress.annotations`, `ingress.tls.enabled`, `ingress.tls.secretName`. The Ingress is named `{{ include "collabhub.fullname" . }}` — `collabhub` for the default release. The dependency chart's Dex Ingress is named `dex` and reads `origin` and `ingress.className`.

- [ ] **Step 1: Write the failing render checks**

In `scripts/test.sh` `layer_lint`, every `helm lint`/`helm template` call that passes `values-k3d.yaml` now also needs `--set-string ingress.host=localhost` (the Ingress will require a host). Then append, after the existing `helm template` line and before the `collabhub-local` lint:

```bash
    # The Ingress is an allow-list of public prefixes. Nothing internal may ever
    # be routed from it (Conventions §5.5), and it must always name a host — an
    # empty host matches every host, which is a collision once two instances
    # share a cluster.
    local ingress
    ingress="$(helm template collabhub charts/collabhub \
        --values charts/collabhub/values-k3d.yaml \
        --set-string ingress.host=a.localhost \
        --api-versions keda.sh/v1alpha1 \
        --show-only templates/ingress.yaml)"
    if printf '%s\n' "$ingress" | grep -Eq '/api/v1/internal|/health'; then
        die "charts/collabhub's Ingress routes an internal path"
    fi
    printf '%s\n' "$ingress" | grep -q 'host: "a.localhost"' \
        || die "charts/collabhub's Ingress does not route on its host"
    # --api-versions on both: --show-only filters after a full render, and
    # without the KEDA API the ScaledObjects fail first — the no-host check
    # would then pass for the wrong reason.
    if helm template collabhub charts/collabhub \
        --values charts/collabhub/values-k3d.yaml \
        --api-versions keda.sh/v1alpha1 >/dev/null 2>&1; then
        die "charts/collabhub rendered an enabled Ingress with no host"
    fi
```

- [ ] **Step 2: Run it to verify it fails**

Run: `scripts/test.sh lint`
Expected: FAIL at `lint: helm` with `Error: could not find template templates/ingress.yaml in chart`.

- [ ] **Step 3: STOP — review checkpoint.** Report the red run and wait for approval before Step 4.

- [ ] **Step 4: Add the values**

In `charts/collabhub/values.yaml`, replace the header paragraph

```yaml
# Also absent: an Ingress. Which hosts route where is a per-environment
# decision, and anything under /api/v1/internal/ must never be routed from the
# public ingress at all (Conventions §5.5).
```
with
```yaml
# The Ingress is opt-in (register D40). What may be routed is the chart's
# business — the public prefixes are listed in templates/ingress.yaml, and
# nothing under /api/v1/internal/ is among them (Conventions §5.5). Where it is
# routed from is the environment's: host, class, annotations and TLS below.
```

and add after the `image:` block:

```yaml
ingress:
  enabled: false
  # The IngressClass: traefik on k3d, nginx on the lab.
  className: ""
  # Required when enabled. scripts/deploy.sh sets it to the host part of
  # APP_ORIGIN — it is never written into a values file.
  host: ""
  annotations: {}
  tls:
    enabled: false
    # A Secret holding the certificate for `host`, created outside this chart.
    secretName: ""
```

In `charts/collabhub/values-k3d.yaml`, add after `imagePullPolicy: Always`:

```yaml
# k3s's bundled Traefik. The host comes from APP_ORIGIN (scripts/deploy.sh).
ingress:
  enabled: true
  className: traefik
```

- [ ] **Step 5: Write the template**

Create `charts/collabhub/templates/ingress.yaml`:

```yaml
{{- if .Values.ingress.enabled }}
{{- $ctx := dict "root" $ "name" "ingress" }}
{{- $components := .Values.components }}
{{- $host := required "ingress.host is empty: set it to the host part of APP_ORIGIN, as scripts/deploy.sh does" .Values.ingress.host }}
# The public routes, and only those (register D40).
#
# An allow-list, so what is not here is not reachable: /api/v1/internal/
# (Conventions §5.5) and /health fall through to the SPA's index.html and never
# reach a service. Adding a prefix here is how an API becomes public.
#
# One origin for the SPA and every public API. Register D22 needs them
# same-site — the refresh cookie is SameSite=Strict — and one origin needs no
# CORS at all. The identity provider is not routed here: it is a dependency, and
# the chart that deploys it routes it on the same host.
#
# Canvas and Asset have no public API yet. When Canvas gains real-time it will
# want /socket.io too, which Messaging already holds.
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ include "collabhub.fullname" . }}
  labels:
    {{- include "collabhub.labels" $ctx | nindent 4 }}
  {{- with .Values.ingress.annotations }}
  annotations:
    {{- toYaml . | nindent 4 }}
  {{- end }}
spec:
  {{- with .Values.ingress.className }}
  ingressClassName: {{ . }}
  {{- end }}
  {{- if .Values.ingress.tls.enabled }}
  tls:
    - hosts:
        - {{ $host | quote }}
      secretName: {{ required "ingress.tls.secretName is empty and ingress.tls.enabled is true" .Values.ingress.tls.secretName }}
  {{- end }}
  rules:
    - host: {{ $host | quote }}
      http:
        paths:
          {{- if $components.auth.enabled }}
          {{- $auth := include "collabhub.componentFullname" (dict "root" $ "name" "auth") }}
          {{- range list "/api/v1/auth" "/api/v1/users" "/api/v1/workspaces" "/.well-known" }}
          - path: {{ . }}
            pathType: Prefix
            backend:
              service:
                name: {{ $auth }}
                port:
                  name: http
          {{- end }}
          {{- end }}
          {{- if $components.messaging.enabled }}
          {{- $messaging := include "collabhub.componentFullname" (dict "root" $ "name" "messaging") }}
          {{- range list "/api/v1/channels" "/api/v1/messages" "/api/v1/search" "/socket.io" }}
          - path: {{ . }}
            pathType: Prefix
            backend:
              service:
                name: {{ $messaging }}
                port:
                  name: http
          {{- end }}
          {{- end }}
          {{- if $components.frontend.enabled }}
          - path: /
            pathType: Prefix
            backend:
              service:
                name: {{ include "collabhub.componentFullname" (dict "root" $ "name" "frontend") }}
                port:
                  name: http
          {{- end }}
{{- end }}
```

- [ ] **Step 6: Shrink the dependency chart's Ingress to Dex**

Replace the whole of `charts/collabhub-local/templates/ingress.yaml` with:

```yaml
{{- $ctx := dict "root" $ "name" "dex" }}
{{- $origin := required "origin is empty: set it to APP_ORIGIN, as scripts/deploy.sh does" .Values.origin }}
{{- $host := regexReplaceAll "^[a-z]+://([^:/]+).*$" $origin "${1}" }}
# Dex on the instance's own origin, beside the Ingress charts/collabhub renders
# for the SPA and the APIs. Ingress controllers merge rules for one host across
# Ingress objects, so the browser sees a single origin, and the app chart never
# has to know which identity provider an environment runs.
#
# Its issuer is `origin`/dex, so the host routed here and the host in Dex's
# config are the same value by construction.
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: dex
  labels:
    {{- include "collabhub-local.labels" $ctx | nindent 4 }}
spec:
  ingressClassName: {{ required "ingress.className is empty" .Values.ingress.className }}
  rules:
    - host: {{ $host | quote }}
      http:
        paths:
          - path: /dex
            pathType: Prefix
            backend:
              service:
                name: dex
                port:
                  name: http
```

In `charts/collabhub-local/values.yaml`, replace

```yaml
# The one origin the browser uses: k3d's load balancer (scripts/k3d/cluster.yaml).
# Dex's issuer and every redirect URI are built from it.
origin: http://localhost:8080
```
with
```yaml
# The origin the browser uses. Dex's issuer, every redirect URI and the Dex
# Ingress host are built from it. Required: scripts/deploy.sh sets it from
# APP_ORIGIN.
origin: ""

ingress:
  className: traefik
```

- [ ] **Step 7: Run lint**

The dependency chart now requires `origin`, so in `scripts/test.sh` change its lint line to:

```bash
    helm lint --quiet charts/collabhub-local "${LOCAL_CHART_FILES[@]}" --set-string origin=http://localhost:8080
```

Run: `scripts/test.sh lint`
Expected: PASS.

- [ ] **Step 8: Eyeball both renders**

Run:
```bash
helm template collabhub charts/collabhub --values charts/collabhub/values-k3d.yaml \
  --set-string ingress.host=localhost --show-only templates/ingress.yaml
helm template collabhub-local charts/collabhub-local "--set-file" postgres.initSql=docker/postgres/init.sql \
  --set-file garage.config=docker/garage/garage.toml --set-file otelCollector.config=docker/otel-collector/config.yaml \
  --set-string origin=http://a.localhost:8080 --show-only templates/ingress.yaml
```
Expected: the first shows `host: "localhost"`, `ingressClassName: traefik`, 9 paths ending in `/`; the second shows `name: dex`, `host: "a.localhost"`, one path `/dex`.

### Task 6: environments and instances in the scripts

**Files:**
- Modify: `scripts/lib/common.sh:22-35`
- Modify: `scripts/deploy.sh` (header, argument parsing, `require_local_cluster` callers, `cmd_infra`, `cmd_app`, `check_origin`, `cmd_status`)
- Modify: `charts/collabhub/values-k3d.yaml` (drop origin-derived and namespace-derived values)
- Modify: `scripts/k3d/cluster.yaml:14-15` (comment)
- Modify: `.env.example` (build-and-deploy section)

**Interfaces:**
- Consumes: `ingress.*` values and the `dex` Ingress from Task 5.
- Produces (for Tasks 8–10): environment variables `DEPLOY_ENV` (default `k3d`), `NAMESPACE` (default `collabhub`), `APP_ORIGIN` (default `http://localhost:8080` when `DEPLOY_ENV=k3d`, required otherwise); bash functions `origin_host <origin>` and `require_matching_context`; `deploy.sh infra -- <helm args>` and `deploy.sh app -- <helm args>`.

There is no bash test layer in this repo and this plan does not invent one: this task is proven by Step 7's deploy and by Task 10.

- [ ] **Step 1: `common.sh`**

Replace

```bash
K3D_CLUSTER=collabhub
# The only published port. The Ingress puts the SPA, the APIs and Dex behind this
# one origin, which is what register D22's SameSite=Strict cookie needs.
K3D_ORIGIN=http://localhost:8080
NAMESPACE=collabhub
```
with
```bash
K3D_CLUSTER=collabhub
# k3d's only published port. Every instance on the cluster shares it, told apart
# by host: http://localhost:8080, http://a.localhost:8080, ...
K3D_ORIGIN=http://localhost:8080

# Which values files the charts install with: charts/*/values-$DEPLOY_ENV.yaml.
DEPLOY_ENV="${DEPLOY_ENV:-k3d}"
# One instance of CollabHub: its namespace, and the origin the browser reaches it
# on. The SPA, the APIs and Dex all sit behind that one origin, which is what
# register D22's SameSite=Strict cookie needs. deploy.sh resolves an empty
# APP_ORIGIN, because only k3d has a sensible default.
NAMESPACE="${NAMESPACE:-collabhub}"
APP_ORIGIN="${APP_ORIGIN:-}"
```

and update the header comment's variable list to add, after `KUBE_CONTEXT`:

```bash
#   DEPLOY_ENV      default: k3d. Selects charts/*/values-$DEPLOY_ENV.yaml.
#   NAMESPACE       default: collabhub. One instance per namespace.
#   APP_ORIGIN      the origin the browser uses, e.g. http://a.localhost:8080.
#                   Default: http://localhost:8080 on k3d; required elsewhere.
```

Append to the helper functions:

```bash
# The host part of an origin: http://a.localhost:8080 → a.localhost.
origin_host() {
    local host="${1#*://}"
    host="${host%%/*}"
    printf '%s' "${host%%:*}"
}
```

- [ ] **Step 2: `deploy.sh` — arguments, origin and guards**

Replace the header usage block with:

```bash
# Deploy CollabHub to Kubernetes with Helm. Developers and CI run this same
# script.
#
#   scripts/deploy.sh [up]     cluster, then infra, then app. Re-run to upgrade
#   scripts/deploy.sh cluster  create the k3d cluster and its image registry
#   scripts/deploy.sh infra    KEDA, then data stores, Dex, Secrets and Dex's Ingress
#   scripts/deploy.sh app      CollabHub itself (charts/collabhub) at IMAGE_TAG
#   scripts/deploy.sh status   releases, pods, jobs and ingresses
#   scripts/deploy.sh down     delete the k3d cluster, its registry and all its data
#
#   scripts/deploy.sh infra -- --set-string postgres.password=...
#                              anything after -- goes to that command's helm call
#
# One instance per NAMESPACE, reached on APP_ORIGIN; DEPLOY_ENV picks the values
# files. Two instances on one k3d cluster:
#
#   NAMESPACE=collabhub-a APP_ORIGIN=http://a.localhost:8080 scripts/deploy.sh up
#   NAMESPACE=collabhub-b APP_ORIGIN=http://b.localhost:8080 scripts/deploy.sh up
#
# The images must already be in the registry — run scripts/build.sh --push
# first. With no overrides CollabHub is served at http://localhost:8080.
```

Replace the final `case` block with:

```bash
command="${1:-up}"
[ $# -gt 0 ] && shift
helm_args=()
if [ "${1:-}" = -- ]; then
    shift
    helm_args=("$@")
elif [ $# -gt 0 ]; then
    die "unexpected argument '$1' (Helm arguments go after --)"
fi

case "$command" in
    up | cluster | infra | app | status | down) ;;
    -h | --help)
        usage
        exit 0
        ;;
    *) die "unknown command '$command' (expected up, cluster, infra, app, status or down)" ;;
esac

# Helm arguments belong to one chart. `up` installs two, and a credential for
# one would be silently ignored by the other.
if [ ${#helm_args[@]} -gt 0 ]; then
    case "$command" in
        infra | app) ;;
        *) die "Helm arguments go to 'infra' or 'app', not '$command'" ;;
    esac
fi

resolve_origin
"cmd_$command"
```

Add after `require_local_cluster`:

```bash
# Only k3d has a default origin. Anywhere else the origin is the environment's
# identity, and guessing localhost would install something nobody can reach.
resolve_origin() {
    if [ -z "$APP_ORIGIN" ]; then
        [ "$DEPLOY_ENV" = k3d ] || die "APP_ORIGIN is required when DEPLOY_ENV is '$DEPLOY_ENV'"
        APP_ORIGIN="$K3D_ORIGIN"
    fi
    APP_ORIGIN="${APP_ORIGIN%/}"
    case "$APP_ORIGIN" in
        http://* | https://*) ;;
        *) die "APP_ORIGIN must start with http:// or https:// (got '$APP_ORIGIN')" ;;
    esac
    case "${APP_ORIGIN#*://}" in
        */*) die "APP_ORIGIN is an origin, with no path (got '$APP_ORIGIN')" ;;
    esac
}

# The environment and the cluster have to agree, in both directions: k3d values
# carry throwaway credentials that must not reach a shared cluster, and another
# environment's values would misconfigure the laptop's.
require_matching_context() {
    if [ "$DEPLOY_ENV" = k3d ]; then
        is_local_cluster || die "DEPLOY_ENV is k3d but KUBE_CONTEXT is '$KUBE_CONTEXT'"
    elif is_local_cluster; then
        die "DEPLOY_ENV is '$DEPLOY_ENV' but KUBE_CONTEXT is the local k3d cluster"
    fi
    [ -f "$REPO_ROOT/charts/collabhub/values-$DEPLOY_ENV.yaml" ] \
        || die "no charts/collabhub/values-$DEPLOY_ENV.yaml for DEPLOY_ENV '$DEPLOY_ENV'"
}
```

- [ ] **Step 3: `deploy.sh` — `cmd_infra`**

Replace `require_local_cluster infra` with `require_matching_context`, and the release install with:

```bash
    log "installing $LOCAL_RELEASE into $NAMESPACE for $APP_ORIGIN — data stores, Dex, Secrets"
    helm_ns upgrade --install "$LOCAL_RELEASE" "$REPO_ROOT/charts/collabhub-local" \
        --create-namespace \
        "${LOCAL_CHART_FILES[@]}" \
        --set-string "origin=$APP_ORIGIN" \
        ${helm_args[@]+"${helm_args[@]}"} \
        --wait --timeout 10m
```

(Task 8 renames the chart and adds its values file.) Update the `require_local_cluster` comment above it to say it now guards only `cluster` and `down`.

- [ ] **Step 4: `deploy.sh` — `cmd_app`**

Add `require_matching_context` as the first line of `cmd_app`, and replace the `helm_ns upgrade --install "$APP_RELEASE"` call with:

```bash
    log "installing $APP_RELEASE at $IMAGE_TAG into $NAMESPACE for $APP_ORIGIN"
    # Everything that depends on where this instance is reached, or which
    # namespace it is in, is set here — never in a values file — so one values
    # file serves any number of instances.
    #
    # REDIS_STREAMS_ADDRESS is read by KEDA's operator, which resolves it from its
    # own namespace, so it must be fully qualified.
    helm_ns upgrade --install "$APP_RELEASE" "$REPO_ROOT/charts/collabhub" \
        --create-namespace \
        --values "$REPO_ROOT/charts/collabhub/values-$DEPLOY_ENV.yaml" \
        --set-string "image.registry=$IMAGE_REGISTRY" \
        --set-string "image.tag=$IMAGE_TAG" \
        --set-string "ingress.host=$(origin_host "$APP_ORIGIN")" \
        --set-string "components.auth.env.AUTH_ISSUER=$APP_ORIGIN" \
        --set-string "components.auth.env.SPA_REDIRECT_URI=$APP_ORIGIN/auth/callback" \
        --set-string "components.messaging.env.AUTH_ISSUER=$APP_ORIGIN" \
        --set-string "components.canvas.env.AUTH_ISSUER=$APP_ORIGIN" \
        --set-string "components.asset.env.AUTH_ISSUER=$APP_ORIGIN" \
        --set-string "components.worker.env.REDIS_STREAMS_ADDRESS=redis-streams.$NAMESPACE.svc.cluster.local:6379" \
        ${helm_args[@]+"${helm_args[@]}"} \
        --wait --timeout 10m
```

Replace

```bash
    if is_local_cluster; then
        check_origin
    fi
```
with
```bash
    check_origin
```

- [ ] **Step 5: `deploy.sh` — `check_origin` and `status`**

Replace `check_origin` with:

```bash
# Through the Ingress, so this proves routing as well as the pods: the SPA, and
# Auth's JWKS, which every other service needs to verify a token. Routing is
# what is most likely to be wrong in a new environment, so it runs everywhere.
check_origin() {
    local path
    for path in / /.well-known/jwks.json; do
        curl --fail --silent --show-error --output /dev/null \
            --retry 30 --retry-delay 2 --retry-all-errors \
            "$APP_ORIGIN$path" || die "$APP_ORIGIN$path is not answering"
    done
    if [ "$DEPLOY_ENV" = k3d ]; then
        log "CollabHub is up at $APP_ORIGIN — sign in as ada@collabhub.dev with password collabhub"
    else
        log "CollabHub is up at $APP_ORIGIN"
    fi
}
```

In `cmd_status`, `kube get pods,jobs,ingress` stays; add `log "namespace $NAMESPACE, origin $APP_ORIGIN"` as its first line.

- [ ] **Step 6: Take the origin and namespace out of `values-k3d.yaml`**

In `charts/collabhub/values-k3d.yaml`:
- Delete every `AUTH_ISSUER: http://localhost:8080` line (auth, messaging, canvas, asset) and `SPA_REDIRECT_URI: http://localhost:8080/auth/callback`.
- Delete from the worker block:
  ```yaml
      # Fully qualified: KEDA's operator resolves this from its own namespace,
      # `keda`, where a bare `redis-streams` does not exist.
      REDIS_STREAMS_ADDRESS: redis-streams.collabhub.svc.cluster.local:6379
  ```
- Replace the header's last three lines

  ```yaml
  # charts/collabhub-local, and KEDA from `deploy.sh infra`. The browser reaches
  # everything on one origin, http://localhost:8080, so CORS_ALLOWED_ORIGINS stays
  # unset.
  ```
  with
  ```yaml
  # charts/collabhub-local, and KEDA from `deploy.sh infra`. The browser reaches
  # everything on one origin, so CORS_ALLOWED_ORIGINS stays unset. That origin is
  # APP_ORIGIN, and deploy.sh sets everything derived from it — AUTH_ISSUER,
  # SPA_REDIRECT_URI, the Ingress host — along with the namespace-qualified
  # REDIS_STREAMS_ADDRESS. None of it belongs here, so one file serves any number
  # of instances on the cluster.
  ```

In `scripts/test.sh`, the `values-k3d.yaml` lint and template calls now render with no `AUTH_ISSUER` — that is valid Helm, so no change is needed beyond Task 5's `ingress.host`.

In `scripts/k3d/cluster.yaml`, replace the port comment with:

```yaml
  # The only published port. Traefik (bundled with k3s) serves every instance's
  # Ingress here, routed on host: localhost, a.localhost, b.localhost ...
```

- [ ] **Step 7: `.env.example`**

In the "Build and deploy scripts" section, after the `KUBE_CONTEXT` entry, add:

```bash
#
# Which charts/*/values-$DEPLOY_ENV.yaml files to install with: k3d or lab.
# DEPLOY_ENV=k3d
#
# One instance per namespace. Several can share a cluster.
# NAMESPACE=collabhub
#
# The origin the browser reaches this instance on. Everything origin-dependent —
# Auth's issuer, the SPA redirect, Dex's issuer, the Ingress host — is derived
# from it. Default http://localhost:8080 on k3d; required for any other
# DEPLOY_ENV.
# APP_ORIGIN=http://a.localhost:8080
```

- [ ] **Step 8: Lint, then a single-instance deploy on a fresh cluster**

The dependency chart's Ingress was named `collabhub` and the app chart's is now `collabhub`, in different releases — so an existing cluster must be recreated, not upgraded.

Run:
```bash
scripts/test.sh lint
scripts/deploy.sh down
scripts/build.sh --push
scripts/deploy.sh
```
Expected: lint passes; `deploy.sh` ends with `CollabHub is up at http://localhost:8080 — sign in as ada@collabhub.dev with password collabhub`.

Then:
```bash
src/services/auth/scripts/sign-in.py --auth-url http://localhost:8080 --access-token | cut -c1-20
kubectl --context k3d-collabhub -n collabhub get configmap collabhub-auth -o jsonpath='{.data.AUTH_ISSUER}{"\n"}{.data.SPA_REDIRECT_URI}{"\n"}'
```
Expected: `eyJ…`; then `http://localhost:8080` and `http://localhost:8080/auth/callback`.

If `sign-in.py` reports a refused connection, `localhost` resolved to `::1` first while k3d binds `127.0.0.1` — check with `curl -v http://localhost:8080/ 2>&1 | grep Trying`.

- [ ] **Step 9: The guards refuse what they should**

Run each and confirm the message:
```bash
DEPLOY_ENV=lab scripts/deploy.sh app            # APP_ORIGIN is required when DEPLOY_ENV is 'lab'
DEPLOY_ENV=lab APP_ORIGIN=http://lab.example scripts/deploy.sh app
                                                # DEPLOY_ENV is 'lab' but KUBE_CONTEXT is the local k3d cluster
APP_ORIGIN=http://x.localhost:8080/app scripts/deploy.sh app
                                                # APP_ORIGIN is an origin, with no path
scripts/deploy.sh up -- --set-string a=b        # Helm arguments go to 'infra' or 'app', not 'up'
```

### Task 7: record D40 — per-environment values and an opt-in Ingress

**Files:**
- Create: `docs/adr/260916-per-environment-values-and-an-opt-in-ingress.md` (via the `adr-writer` skill)
- Modify: `docs/design/07-open-decisions-register.md`, `docs/adr/260914-local-kubernetes-on-k3d-with-a-dev-only-dependency-chart.md`, `CLAUDE.md`, `README.md`

- [ ] **Step 1: Write the ADR with `adr-writer`**

Invoke the `adr-writer` skill with the title "Per-environment values and an opt-in Ingress", status Accepted, date 2026-09-16. It must record:
- **Context:** only k3d could be deployed — `values-k3d.yaml` hardwired, the origin a constant and seven literals, the frontend image origin-specific, no Ingress in the app chart; a lab with ingress-nginx and nothing else needed CollabHub.
- **Decision:** (1) `APP_ORIGIN` is the single source of the public origin and `NAMESPACE` the instance; neither is written into a values file; `deploy.sh` derives `ingress.host`, `AUTH_ISSUER`, `SPA_REDIRECT_URI` and `REDIS_STREAMS_ADDRESS` from them. (2) `DEPLOY_ENV` selects `values-<env>.yaml`, with a context guard in both directions. (3) The SPA is built same-origin, so one image serves every environment. (4) `charts/collabhub` has an opt-in Ingress; the public-prefix allow-list is in the template, host/class/annotations/TLS are values; the dependency chart routes its own IdP on the same host.
- **Consequences:** several instances per cluster; `/api/v1/internal/` protection now lives in the chart and is checked by `test.sh`; a non-same-origin deployment must export `VITE_*` and set `CORS_ALLOWED_ORIGINS`; existing k3d clusters are recreated once (Ingress name moved release).
- **Alternatives:** a lab-only chart (duplicated manifests, route list in two places); hand-written lab manifests (not reproducible, not scriptable); runtime SPA config via a fetched `config.json` (unnecessary once same-origin is the norm).

- [ ] **Step 2: Register row D40**

In `docs/design/07-open-decisions-register.md`, add to the cross-cutting table, after the D30 row:

```markdown
| D40 | How CollabHub is deployed to more than one environment (raised 2026-09-16: only k3d could be deployed — the origin was a constant, `values-k3d.yaml` was hardwired, and the frontend image was built for one origin) | 🟢 **Decided (2026-09-16):** `APP_ORIGIN` and `NAMESPACE` identify an instance and are never written into values; `DEPLOY_ENV` selects `values-<env>.yaml`; the SPA is built same-origin, so one image serves every environment; `charts/collabhub` has an opt-in Ingress whose public-prefix allow-list is in the template | Several instances can share a cluster. `/api/v1/internal/` staying unrouted is now the chart's job, checked at lint time. See [ADR 260916](../adr/260916-per-environment-values-and-an-opt-in-ingress.md) | Cross-cutting (chart, scripts, Frontend) |
```

and add to the "Resolve First" settled list:

```markdown
**Settled 2026-09-16:** D40 — CollabHub deploys to any environment from one set
of images, identified by `APP_ORIGIN` and `NAMESPACE`.
[ADR](../adr/260916-per-environment-values-and-an-opt-in-ingress.md).
```

- [ ] **Step 3: Amend ADR 260914's Ingress statements**

In `docs/adr/260914-local-kubernetes-on-k3d-with-a-dev-only-dependency-chart.md`:
- In **Context**, after "and no Ingress, because routing is per-environment and `/api/v1/internal/` must never be public (Conventions §5.5).", add: "*(Amended 2026-09-16: the chart now has an opt-in Ingress — see ADR 260916.)*"
- In **Decision**, replace the "**One origin.**" bullet with:
  ```markdown
  - **One origin.** A Traefik Ingress serves the SPA, the public API prefixes and
    Dex from `http://localhost:8080`. That satisfies D22 with no CORS at all, and
    nothing routes `/api/v1/internal/`. *(Amended 2026-09-16: the SPA and API
    routes are now `charts/collabhub`'s opt-in Ingress, and this chart routes
    only `/dex`, on a host taken from `APP_ORIGIN` — ADR 260916.)*
  ```

- [ ] **Step 4: CLAUDE.md**

- Replace "There is no Ingress in the chart — routing is per-environment, and `/api/v1/internal/` must never be reachable from the public one." with: "The chart's Ingress is opt-in (D40): its public-prefix allow-list lives in `templates/ingress.yaml`, so `/api/v1/internal/` is never routable; the host comes from `APP_ORIGIN` and never from a values file."
- In the **Settled so far** list, add `· D40 deploy any environment from one set of images, identified by APP_ORIGIN and NAMESPACE`.

- [ ] **Step 5: README**

In "Deploying to Kubernetes":
- Replace the paragraph starting "Then open <http://localhost:8080>" so it says everything is on one origin, `APP_ORIGIN`, default `http://localhost:8080`, with the SPA and APIs routed by `charts/collabhub`'s Ingress and Dex by the dependency chart's.
- Add a table row: `` `NAMESPACE=… APP_ORIGIN=… scripts/deploy.sh` `` | "Another instance on the same cluster, e.g. `NAMESPACE=collabhub-a APP_ORIGIN=http://a.localhost:8080`. `*.localhost` needs no DNS" |.
- Add the line: "`scripts/deploy.sh infra -- <helm args>` and `app -- <helm args>` pass arguments to that chart's Helm call."
- Add: "An existing k3d cluster from before this change must be recreated once (`scripts/deploy.sh down`): the `collabhub` Ingress moved from the dependency release to the app release."

In "What the chart expects of an environment", replace the closing two paragraphs ("There is no Ingress either…" and "Because routing is per-environment, **two constraints land on whoever writes it**:" with its bullets) with:

```markdown
The Ingress is opt-in: set `ingress.enabled`, `ingress.className` and — through
`scripts/deploy.sh`, from `APP_ORIGIN` — `ingress.host`. The public prefixes are
fixed in the template, so `/api/v1/internal/` (Conventions §5.5) cannot be routed
by a values file. Two constraints remain the environment's:

- The identity provider must be routed on the same host, or be a real IdP with its
  own. `charts/collabhub-deps` does this for Dex.
- The SPA and the API must be **same-site** — one registrable domain, or one
  origin. The refresh cookie is `SameSite=Strict` (register D22), so splitting them
  across genuinely different domains silently signs everyone out. See
  [`auth/cookies.py`](src/services/auth/auth/cookies.py).
```

(`charts/collabhub-deps` is named ahead of Task 8's rename; the README is consistent once slice 3 lands.)

---

## Slice 3 — the dependency chart becomes any environment's

### Task 8: `collabhub-local` → `collabhub-deps`, credentials required and settable with `--set-string`

**Files:**
- Rename: `charts/collabhub-local/` → `charts/collabhub-deps/`
- Modify: every template under it (helper names), `Chart.yaml`, `values.yaml`, `templates/_helpers.tpl`, `templates/app-secrets.yaml`, `templates/dex.yaml`, `templates/garage.yaml`, `templates/postgres.yaml`
- Create: `charts/collabhub-deps/values-k3d.yaml`
- Modify: `scripts/lib/common.sh` (`LOCAL_CHART_FILES`), `scripts/deploy.sh` (`LOCAL_RELEASE`, `cmd_infra`), `scripts/test.sh` (lint), `charts/collabhub/values-k3d.yaml` (comments), `scripts/k3d/cluster.yaml` (no change needed after Task 6)
- Modify: `docs/design/07-open-decisions-register.md` (D41), ADR 260914, `CLAUDE.md`, `README.md`

**Interfaces:**
- Consumes: `origin` and `ingress.className` values and `DEPLOY_ENV` from Tasks 5–6.
- Produces (for Tasks 9–10): chart `charts/collabhub-deps`, release `collabhub-deps`, bash array `DEPS_CHART_FILES`, bash array `DEPS_TEST_CREDENTIALS` in `test.sh`. Required scalar values: `postgres.password`, `garage.adminToken`, `garage.rpcSecret`, `garage.accessKeyId`, `garage.secretAccessKey`, `dex.clientSecret`, `dex.passwordHash`, `workerClientSecret`. Optional: `auth.signingKey`.

- [ ] **Step 1: Rename mechanically, stay green**

Run:
```bash
git mv charts/collabhub-local charts/collabhub-deps
grep -rl 'collabhub-local\.' charts/collabhub-deps/templates | xargs sed -i '' 's/collabhub-local\./collabhub-deps./g'
sed -i '' 's/part-of: collabhub-local/part-of: collabhub-deps/' charts/collabhub-deps/templates/_helpers.tpl
```

Then by hand:
- `charts/collabhub-deps/Chart.yaml`: `name: collabhub-deps`, description `What CollabHub needs around it in an environment with nothing but an ingress controller — data stores, Dex, Secrets and Dex's Ingress. Credentials have no defaults; the environment supplies them.`
- `scripts/lib/common.sh`: rename `LOCAL_CHART_FILES` → `DEPS_CHART_FILES`, comment `# Files charts/collabhub-deps reads from the repo rather than keeping a copy of.`
- `scripts/deploy.sh`: `LOCAL_RELEASE=collabhub-local` → `DEPS_RELEASE=collabhub-deps`; every `$LOCAL_RELEASE` → `$DEPS_RELEASE`; `charts/collabhub-local` → `charts/collabhub-deps`; `LOCAL_CHART_FILES` → `DEPS_CHART_FILES`.
- `scripts/test.sh`: the lint line becomes `helm lint --quiet charts/collabhub-deps "${DEPS_CHART_FILES[@]}" --set-string origin=http://localhost:8080`.
- `charts/collabhub/values-k3d.yaml`: `charts/collabhub-local` → `charts/collabhub-deps` in both comments.
- `garage-bootstrap.py:111` names a Garage key `collabhub-local` — a key name inside Garage, not the chart. Leave it.

Run: `scripts/test.sh lint`
Expected: PASS.

- [ ] **Step 2: Write the failing render checks**

In `scripts/test.sh`, above `layer_lint`, add:

```bash
# Every credential charts/collabhub-deps renders, as a --set-string argument.
# The values are only shaped right; the render never contacts anything.
DEPS_TEST_CREDENTIALS=(
    --set-string postgres.password=lint-password
    --set-string garage.adminToken=lint-admin-token
    --set-string garage.rpcSecret=0000000000000000000000000000000000000000000000000000000000000002
    --set-string garage.accessKeyId=GK000000000000000000000002
    --set-string garage.secretAccessKey=0000000000000000000000000000000000000000000000000000000000000002
    --set-string dex.clientSecret=lint-client-secret
    --set-string 'dex.passwordHash=$2b$10$lintlintlintlintlintlO0000000000000000000000000000000'
    --set-string workerClientSecret=lint-worker-secret
)
```

and replace the `collabhub-deps` lint line in `layer_lint` with:

```bash
    local deps=(charts/collabhub-deps "${DEPS_CHART_FILES[@]}" --set-string origin=http://lab.example)
    helm lint --quiet "${deps[@]}" --values charts/collabhub-deps/values-k3d.yaml
    # No credential has a default, so the chart refuses to render without them —
    # it cannot be installed anywhere by accident with throwaway values (D41)...
    if helm template collabhub-deps "${deps[@]}" --set-string ingress.className=nginx >/dev/null 2>&1; then
        die "charts/collabhub-deps rendered with no credentials"
    fi
    # ...and every one of them can arrive on the command line, with no values file.
    helm template collabhub-deps "${deps[@]}" --set-string ingress.className=nginx \
        "${DEPS_TEST_CREDENTIALS[@]}" >/dev/null
```

- [ ] **Step 3: Run it to verify it fails**

Run: `scripts/test.sh lint`
Expected: FAIL at `lint: helm` with `Error: open charts/collabhub-deps/values-k3d.yaml: no such file or directory`. Delete `--values charts/collabhub-deps/values-k3d.yaml` from the `helm lint` line temporarily and rerun: FAIL with `error: charts/collabhub-deps rendered with no credentials`. Restore the `--values` argument.

- [ ] **Step 4: STOP — review checkpoint.** Report both red runs and wait for approval before Step 5.

- [ ] **Step 5: `values.yaml` loses its credentials; `values-k3d.yaml` gains them**

Create `charts/collabhub-deps/values-k3d.yaml` holding exactly the credentials removed below, plus the class:

```yaml
# charts/collabhub-deps on the local k3d cluster — DEV ONLY. Layered over
# values.yaml by scripts/deploy.sh when DEPLOY_ENV=k3d, which refuses any
# context but k3d-collabhub.
#
# Every credential here is a throwaway, and Dex is full of demo accounts. They
# repeat .env.example, which cannot be read directly: it carries Compose
# hostnames and `$$` escaping. Any of them can still be overridden per instance
# with `scripts/deploy.sh infra -- --set-string <path>=<value>`.

ingress:
  className: traefik

postgres:
  password: collabhub

garage:
  # The same values docker/garage/garage.toml carries for Compose. Here they reach
  # Garage as GARAGE_ADMIN_TOKEN and GARAGE_RPC_SECRET, which replace the file's.
  adminToken: collabhub-local-admin-token
  rpcSecret: "0000000000000000000000000000000000000000000000000000000000000001" # gitleaks:allow — local dev secret
  # Garage only accepts keys in its own format — `GK` plus 24 hex digits, and a
  # 64-hex-digit secret — so .env.example's `collabhub-local` cannot be imported.
  accessKeyId: GK00000000000000000c011ab0 # gitleaks:allow — local dev key
  secretAccessKey: "00000000000000000000000000000000000000000000000000000000c011ab00" # gitleaks:allow

dex:
  clientSecret: collabhub-local-secret
  # bcrypt of the shared password "collabhub". Single `$`s: the doubling in
  # .env.example is Compose escaping and does not apply here.
  passwordHash: "$2b$10$AjNda/ZYuDZgz2nQA9lAPOb3Y.uGW4xYCWXG8wTfnyb9KjviceU/S"

workerClientSecret: worker-local-secret
```

Rewrite `charts/collabhub-deps/values.yaml` so the header reads:

```yaml
# charts/collabhub-deps — what CollabHub needs around it in an environment that
# provides nothing but an ingress controller. Installed by `scripts/deploy.sh
# infra`, before the app chart, once per instance namespace.
#
# charts/collabhub deliberately leaves the data stores, Secrets and the identity
# provider to each environment. This chart is one answer to all three, suitable
# for k3d and for a lab — not for production: nothing is backed up, Dex is a
# password database of demo accounts, and the Secrets are rendered from values
# rather than a secret store (register D41).
#
# **No credential has a default.** Each is a required scalar, so it can come from
# a values file (values-k3d.yaml has throwaway ones) or from
# `--set-string <path>=<value>` — `scripts/deploy.sh infra -- --set-string ...`.
# The chart refuses to render until every one is supplied, naming the path.
#
# Images match docker-compose.yml; both follow docs/platform/versions.md.
```

and make these value changes (everything else unchanged):

```yaml
postgres:
  image: postgres:18
  user: collabhub
  # Required. Goes into a DSN unescaped, so keep it URL-safe: letters, digits, - _ . ~
  password: ""
  storage: 5Gi
  initSql: ""

garage:
  image: dxflrs/garage:v2.3.0
  config: ""
  # Required. Reach Garage as GARAGE_ADMIN_TOKEN and GARAGE_RPC_SECRET, which
  # replace the literals in the --set-file garage.toml.
  adminToken: ""
  # Required. 64 hex digits.
  rpcSecret: ""
  storage: 2Gi
  bucket: collabhub-assets
  # Required. Garage's own formats: `GK` + 24 hex digits, and 64 hex digits.
  accessKeyId: ""
  secretAccessKey: ""
  bootstrapImage: python:3.12-slim

dex:
  image: ghcr.io/dexidp/dex:v2.45.1
  # Required.
  clientSecret: ""
  # Required. A bcrypt hash — single-quote it on a command line, it is full of `$`.
  passwordHash: ""

# Required. The Worker's client-credentials secret (Conventions §5.5).
workerClientSecret: ""

auth:
  # Optional: Auth's RS256 signing key as PEM, e.g.
  # `--set-file auth.signingKey=signing.pem`. Empty means generate one on first
  # install and keep it across upgrades.
  signingKey: ""
```

Delete the `ingress.className: traefik` added in Task 5 from `values.yaml` and replace with:

```yaml
ingress:
  # Required: the IngressClass that routes this environment's origin.
  className: ""
```

- [ ] **Step 6: One `required` helper, used wherever a credential is read**

Append to `charts/collabhub-deps/templates/_helpers.tpl`:

```yaml
{{/*
A credential that has no default. Fails the render naming the path, and how to
supply it. Usage: include "collabhub-deps.credential" (dict "path" "postgres.password" "value" .Values.postgres.password)
*/}}
{{- define "collabhub-deps.credential" -}}
{{- required (printf "%s is empty: supply it in a values file or with `scripts/deploy.sh infra -- --set-string %s=...`" .path .path) .value -}}
{{- end -}}
```

and change `collabhub-deps.dsn` to:

```yaml
{{- define "collabhub-deps.dsn" -}}
{{- $pg := .root.Values.postgres -}}
{{- $password := include "collabhub-deps.credential" (dict "path" "postgres.password" "value" $pg.password) -}}
{{- printf "postgresql+asyncpg://%s:%s@postgres:5432/collabhub_%s" $pg.user $password .db -}}
{{- end -}}
```

In `templates/postgres.yaml`, the `POSTGRES_PASSWORD` value becomes:

```yaml
              value: {{ include "collabhub-deps.credential" (dict "path" "postgres.password" "value" .Values.postgres.password) | quote }}
```

In `templates/dex.yaml`, `DEX_PASSWORD_HASH:` becomes
`{{ include "collabhub-deps.credential" (dict "path" "dex.passwordHash" "value" .Values.dex.passwordHash) | quote }}`
and `secret: {{ .Values.dex.clientSecret }}` becomes
`secret: {{ include "collabhub-deps.credential" (dict "path" "dex.clientSecret" "value" .Values.dex.clientSecret) | quote }}`.

In `templates/app-secrets.yaml`:
- Before the `$oidcProviders` block, add:
  ```yaml
  {{- $clientSecret := include "collabhub-deps.credential" (dict "path" "dex.clientSecret" "value" .Values.dex.clientSecret) }}
  {{- $workerSecret := include "collabhub-deps.credential" (dict "path" "workerClientSecret" "value" .Values.workerClientSecret) }}
  {{- $accessKeyId := include "collabhub-deps.credential" (dict "path" "garage.accessKeyId" "value" $garage.accessKeyId) }}
  {{- $secretAccessKey := include "collabhub-deps.credential" (dict "path" "garage.secretAccessKey" "value" $garage.secretAccessKey) }}
  ```
- Use `$clientSecret` in `$oidcProviders`, `$workerSecret` in `$serviceClients` and `WORKER_SERVICE_CLIENT_SECRET`, `$accessKeyId`/`$secretAccessKey` for both `OBJECT_STORE_ACCESS_KEY`/`_SECRET_KEY` pairs.
- Signing key: replace
  ```yaml
  {{- $signingKey := "" }}
  {{- $existing := lookup "v1" "Secret" .Release.Namespace $authName }}
  ```
  with
  ```yaml
  {{- $signingKey := .Values.auth.signingKey }}
  {{- $existing := lookup "v1" "Secret" .Release.Namespace $authName }}
  {{- if not $signingKey }}
  ```
  and close it with `{{- end }}` after the existing `{{- end }}` that closes `if $existing`, so a supplied key wins over both the stored and a generated one. Update the comment above to say so.

In `templates/garage.yaml`:
- Add a Secret before the `ConfigMap`:
  ```yaml
  {{- $adminToken := include "collabhub-deps.credential" (dict "path" "garage.adminToken" "value" $garage.adminToken) }}
  {{- $rpcSecret := include "collabhub-deps.credential" (dict "path" "garage.rpcSecret" "value" $garage.rpcSecret) }}
  {{- $accessKeyId := include "collabhub-deps.credential" (dict "path" "garage.accessKeyId" "value" $garage.accessKeyId) }}
  {{- $secretAccessKey := include "collabhub-deps.credential" (dict "path" "garage.secretAccessKey" "value" $garage.secretAccessKey) }}
  # Garage's secrets. GARAGE_ADMIN_TOKEN and GARAGE_RPC_SECRET replace the
  # literals in garage.toml, which is shared with Compose and carries dev values.
  apiVersion: v1
  kind: Secret
  metadata:
    name: garage
    labels:
      {{- include "collabhub-deps.labels" $ctx | nindent 4 }}
  type: Opaque
  stringData:
    GARAGE_ADMIN_TOKEN: {{ $adminToken | quote }}
    GARAGE_RPC_SECRET: {{ $rpcSecret | quote }}
    GARAGE_ACCESS_KEY_ID: {{ $accessKeyId | quote }}
    GARAGE_SECRET_ACCESS_KEY: {{ $secretAccessKey | quote }}
  ---
  ```
- In the StatefulSet's `garage` container add:
  ```yaml
            env:
              - name: GARAGE_ADMIN_TOKEN
                valueFrom:
                  secretKeyRef: {name: garage, key: GARAGE_ADMIN_TOKEN}
              - name: GARAGE_RPC_SECRET
                valueFrom:
                  secretKeyRef: {name: garage, key: GARAGE_RPC_SECRET}
  ```
  and extend its pod annotation to `checksum/config: {{ list $garage.config $adminToken $rpcSecret | toJson | sha256sum }}`.
- In the bootstrap Job, replace the three literal env entries `GARAGE_ADMIN_TOKEN`, `GARAGE_ACCESS_KEY_ID`, `GARAGE_SECRET_ACCESS_KEY` with `valueFrom.secretKeyRef` entries on Secret `garage`, same keys.

- [ ] **Step 7: Install with the environment's values**

In `scripts/deploy.sh` `cmd_infra`, the install becomes:

```bash
    log "installing $DEPS_RELEASE into $NAMESPACE for $APP_ORIGIN — data stores, Dex, Secrets"
    helm_ns upgrade --install "$DEPS_RELEASE" "$REPO_ROOT/charts/collabhub-deps" \
        --create-namespace \
        --values "$REPO_ROOT/charts/collabhub-deps/values-$DEPLOY_ENV.yaml" \
        "${DEPS_CHART_FILES[@]}" \
        --set-string "origin=$APP_ORIGIN" \
        ${helm_args[@]+"${helm_args[@]}"} \
        --wait --timeout 10m
```

and `require_matching_context` also checks `charts/collabhub-deps/values-$DEPLOY_ENV.yaml` exists.

- [ ] **Step 8: Lint green, then a fresh single-instance deploy**

Run:
```bash
scripts/test.sh lint
scripts/deploy.sh down && scripts/deploy.sh
src/services/auth/scripts/sign-in.py --auth-url http://localhost:8080 --access-token | cut -c1-20
kubectl --context k3d-collabhub -n collabhub get jobs
```
Expected: lint passes; deploy ends `CollabHub is up at http://localhost:8080 …`; `eyJ…`; no failed Jobs (the migration Jobs and `garage-bootstrap` are hook Jobs deleted on success, so an empty list is a pass).

Then prove Garage accepted the token from the environment — a wrong token would fail the bootstrap Job, so run:
```bash
kubectl --context k3d-collabhub -n collabhub logs statefulset/garage | grep -i -m3 "admin\|token\|error" || true
```
Expected: no authentication errors.

- [ ] **Step 9: Record D41**

Register row, cross-cutting table:

```markdown
| D41 | Where an environment's data stores, IdP and Secrets come from when the cluster provides none (raised 2026-09-16: the lab has only an ingress controller, and `charts/collabhub-local` refused anything but k3d) | 🟢 **Decided (2026-09-16):** `charts/collabhub-local` becomes `charts/collabhub-deps`, for any environment. No credential has a default; each is a required scalar supplied by a values file or `--set-string`. Dev-only is a property of `values-k3d.yaml`, not the chart | Safer than before: the chart cannot render with throwaway credentials by accident. Still not production — no backups, Dex's password DB, Secrets rendered from values rather than a secret store. See [ADR 260916](../adr/260916-per-environment-values-and-an-opt-in-ingress.md) | Cross-cutting (charts, scripts) |
```

Add a **D41** section to ADR `260916-per-environment-values-and-an-opt-in-ingress.md` (under Decision, "The dependency chart"), and to ADR 260914 add at the top of **Decision**: "*(Amended 2026-09-16: `charts/collabhub-local` is now `charts/collabhub-deps`, usable in any environment, with credentials required rather than defaulted — register D41.)*"

CLAUDE.md:
- Repo layout line: `charts/collabhub-deps/  # data stores, Dex, Secrets, Dex's Ingress — any environment; credentials required (D41)`.
- Replace the paragraph starting "`charts/collabhub-local` is the local k3d environment's answer to all of that" with:
  "`charts/collabhub-deps` is an environment's answer to all of that — the data stores, Dex, the Secrets the app chart's `envFromSecrets` names, and Dex's Ingress on the instance's host. **No credential has a default** (D41): `values-k3d.yaml` carries throwaway ones and is development only; any other environment supplies them with `scripts/deploy.sh infra -- --set-string <path>=<value>`. `scripts/deploy.sh` refuses k3d values on any context but `k3d-collabhub`, and any other environment's values on it. Its Dex config is a third copy beside `docker/dex/config.yaml` and `config.test.yaml` — change all three together. Gaps a deploy finds in `charts/collabhub` get fixed in that chart, never worked around in the scripts or the dependency chart."
- Settled list: `· D41 the dependency chart serves any environment, credentials required`.

README: every `charts/collabhub-local` → `charts/collabhub-deps` (lines 106, 272, 285, 315); rewrite the "**development only**" paragraph to say the *k3d values* are development only and the chart takes credentials from values or `--set-string`, with a worked example:

```bash
scripts/deploy.sh infra -- \
  --set-string postgres.password=... \
  --set-string 'dex.passwordHash=$2b$10$...'
```

and a note that `--set-string` splits on commas, so a credential may not contain one, and that the Postgres password must be URL-safe.

### Task 9: the lab's values and D42

**Files:**
- Create: `charts/collabhub/values-lab.yaml`, `charts/collabhub-deps/values-lab.yaml`
- Modify: `scripts/test.sh` (lint the lab values)
- Modify: `docs/design/07-open-decisions-register.md` (D42), ADR 260916, `CLAUDE.md`, `README.md`

**Interfaces:**
- Consumes: everything from Tasks 5–8.
- Produces: `DEPLOY_ENV=lab` renders and lints.

- [ ] **Step 1: Write the failing lint**

In `scripts/test.sh`, append to the **end** of `layer_lint` — after the `collabhub-deps` checks, because it reuses their `deps` array:

```bash
    # The lab: ingress-nginx, plain HTTP, CollabHub bringing its own dependencies.
    helm lint --quiet charts/collabhub --values charts/collabhub/values-lab.yaml \
        --set-string ingress.host=lab.example \
        --set components.worker.autoscaling.enabled=false
    helm template collabhub charts/collabhub --values charts/collabhub/values-lab.yaml \
        --set-string ingress.host=lab.example \
        --api-versions keda.sh/v1alpha1 >/dev/null
    helm template collabhub-deps "${deps[@]}" --values charts/collabhub-deps/values-lab.yaml \
        "${DEPS_TEST_CREDENTIALS[@]}" >/dev/null
```

Run: `scripts/test.sh lint`
Expected: FAIL with `Error: open charts/collabhub/values-lab.yaml: no such file or directory`.

(Values files, not behaviour — no review stop needed; proceed.)

- [ ] **Step 2: `charts/collabhub/values-lab.yaml`**

```yaml
# charts/collabhub on the lab cluster: ingress-nginx and nothing else, so
# charts/collabhub-deps provides the data stores, Dex and the Secrets. Layered
# over values.yaml by scripts/deploy.sh when DEPLOY_ENV=lab.
#
# No hostname appears here. The origin is APP_ORIGIN, and deploy.sh sets
# everything derived from it (register D40).

ingress:
  enabled: true
  className: nginx

components:
  auth:
    env:
      # `local` is the only APP_ENV the code distinguishes, and only Auth reads it:
      # it creates the shared demo workspace every new account joins. The lab
      # runs Dex's demo accounts, so it wants that. Anything else would only
      # isolate users — it switches on no stricter behaviour (the signing-key
      # check it also gates is satisfied by charts/collabhub-deps).
      APP_ENV: local
      # The lab is plain HTTP on a real hostname. Browsers exempt only
      # http://localhost from `Secure`, so with it on the refresh cookie is
      # dropped and every user is signed out at the first renewal. Off puts the
      # refresh token on the wire in clear — acceptable only because the lab is
      # a trusted network. Register D42; never copy this to an environment
      # reachable from outside one.
      AUTH_COOKIE_SECURE: "false"
  messaging:
    env:
      APP_ENV: local
  canvas:
    env:
      APP_ENV: local
  asset:
    env:
      APP_ENV: local
  worker:
    env:
      APP_ENV: local

# ingressController keeps the values.yaml default — ingress-nginx in namespace
# ingress-nginx — which is what the lab runs. Everything else is a pod from
# charts/collabhub-deps in this namespace.
networkPolicy:
  peers:
    postgres:
      to:
        - podSelector:
            matchLabels:
              app.kubernetes.io/name: postgres
    redisCache:
      to:
        - podSelector:
            matchLabels:
              app.kubernetes.io/name: redis-cache
    redisRealtime:
      to:
        - podSelector:
            matchLabels:
              app.kubernetes.io/name: redis-rt
    redisStreams:
      to:
        - podSelector:
            matchLabels:
              app.kubernetes.io/name: redis-streams
    elasticsearch:
      to:
        - podSelector:
            matchLabels:
              app.kubernetes.io/name: elasticsearch
    objectStore:
      to:
        - podSelector:
            matchLabels:
              app.kubernetes.io/name: garage
    otelCollector:
      to:
        - podSelector:
            matchLabels:
              app.kubernetes.io/name: otel-collector
    oidcProvider:
      to:
        - podSelector:
            matchLabels:
              app.kubernetes.io/name: dex
      ports:
        - port: 5556
          protocol: TCP
```


- [ ] **Step 3: `charts/collabhub-deps/values-lab.yaml`**

```yaml
# charts/collabhub-deps on the lab cluster. Layered over values.yaml by
# scripts/deploy.sh when DEPLOY_ENV=lab.
#
# **No credentials here** (register D41). Supply every one on the command line:
#
#   DEPLOY_ENV=lab APP_ORIGIN=http://<host> KUBE_CONTEXT=<lab> scripts/deploy.sh infra -- \
#     --set-string postgres.password=... \
#     --set-string garage.adminToken=... \
#     --set-string garage.rpcSecret=<64 hex> \
#     --set-string garage.accessKeyId=GK<24 hex> \
#     --set-string garage.secretAccessKey=<64 hex> \
#     --set-string dex.clientSecret=... \
#     --set-string 'dex.passwordHash=<bcrypt>' \
#     --set-string workerClientSecret=...
#
# The render fails naming whichever is missing.

ingress:
  className: nginx
```

- [ ] **Step 4: Lint green**

Run: `scripts/test.sh lint`
Expected: PASS.

- [ ] **Step 5: Record D42**

Register row, cross-cutting table:

```markdown
| D42 | Whether the refresh cookie may drop `Secure` in an environment served over plain HTTP (raised 2026-09-16: the lab is `http://` on a real hostname, where browsers discard a `Secure` cookie) | 🟢 **Decided (2026-09-16):** yes, in the lab only — `AUTH_COOKIE_SECURE: "false"` in `charts/collabhub/values-lab.yaml` | The refresh token — thirty days — then travels in clear. Acceptable on a trusted lab network and nowhere else; any environment reachable from outside one needs TLS. k3d instances on `*.localhost` keep `Secure`, which browsers accept there. Related: D22 | Auth (+ chart) |
```

In ADR 260916 add a **Consequences** paragraph for D42. CLAUDE.md settled list: `· D42 the lab (plain HTTP) runs the refresh cookie without Secure; nowhere else`. README "Deploying to Kubernetes": a short "Deploying to the lab" subsection with the `DEPLOY_ENV=lab APP_ORIGIN=… KUBE_CONTEXT=…` commands, the registry prerequisite ("`IMAGE_REGISTRY` must be a registry the lab can pull from, with `docker login` done — the k3d registry at `localhost:5500` is unreachable from it"), and the D42 caveat.

- [ ] **Step 6: Full local run**

Run: `scripts/test.sh`
Expected: lint, unit and integration all pass.

---

## Acceptance

### Task 10: one k3d cluster, two instances

**Files:** none changed — verification only. Record results in the task report.

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: A clean cluster and one set of images**

```bash
scripts/deploy.sh down
scripts/build.sh --push
scripts/deploy.sh cluster
```
Expected: images pushed at one `IMAGE_TAG`; cluster created.

- [ ] **Step 2: Instance A from `values-k3d.yaml`**

```bash
export IMAGE_TAG="$(bash -c 'source scripts/lib/common.sh; echo $IMAGE_TAG')"
NAMESPACE=collabhub-a APP_ORIGIN=http://a.localhost:8080 scripts/deploy.sh infra
NAMESPACE=collabhub-a APP_ORIGIN=http://a.localhost:8080 scripts/deploy.sh app
```
Expected: ends `CollabHub is up at http://a.localhost:8080 …`. (Exporting `IMAGE_TAG` keeps both instances on the build from Step 1 even though the worktree is dirty and unchanged.)

- [ ] **Step 3: Instance B with credentials supplied only through `--set-string`**

Each of B's credentials differs from `values-k3d.yaml`, so a pass proves the `--set-string` path rather than the file:

```bash
NAMESPACE=collabhub-b APP_ORIGIN=http://b.localhost:8080 scripts/deploy.sh infra -- \
  --set-string postgres.password=instance-b-postgres \
  --set-string garage.adminToken=instance-b-admin-token \
  --set-string garage.rpcSecret=00000000000000000000000000000000000000000000000000000000000000bb \
  --set-string garage.accessKeyId=GK0000000000000000000000bb \
  --set-string garage.secretAccessKey=00000000000000000000000000000000000000000000000000000000000000bb \
  --set-string dex.clientSecret=instance-b-client-secret \
  --set-string workerClientSecret=instance-b-worker-secret
NAMESPACE=collabhub-b APP_ORIGIN=http://b.localhost:8080 scripts/deploy.sh app
kubectl --context k3d-collabhub -n collabhub-b get secret collabhub-auth -o jsonpath='{.data.OIDC_PROVIDERS}' | base64 -d
```
Expected: deploy ends `CollabHub is up at http://b.localhost:8080 …`; `OIDC_PROVIDERS` shows `"authority":"http://b.localhost:8080/dex"` and `"clientSecret":"instance-b-client-secret"`.

(`dex.passwordHash` keeps the k3d value so `ada`/`collabhub` still signs in.)

- [ ] **Step 4: Criterion 1 — both origins route**

```bash
for o in http://a.localhost:8080 http://b.localhost:8080; do
  for p in / /.well-known/jwks.json /dex/.well-known/openid-configuration; do
    printf '%s%s %s\n' "$o" "$p" "$(curl -s -o /dev/null -w '%{http_code}' "$o$p")"
  done
done
curl -s http://a.localhost:8080/dex/.well-known/openid-configuration | grep -o '"issuer":"[^"]*"'
curl -s http://b.localhost:8080/dex/.well-known/openid-configuration | grep -o '"issuer":"[^"]*"'
curl -s -o /dev/null -w '%{http_code} %{content_type}\n' http://a.localhost:8080/api/v1/internal/anything
```
Expected: six `200`s; issuers `http://a.localhost:8080/dex` and `http://b.localhost:8080/dex`; the internal path answers `200 text/html` — the SPA's `index.html`, never a service.

- [ ] **Step 5: Criterion 2 — sign-in works on both**

```bash
TOKEN_A="$(src/services/auth/scripts/sign-in.py --auth-url http://a.localhost:8080 --access-token)"
TOKEN_B="$(src/services/auth/scripts/sign-in.py --auth-url http://b.localhost:8080 --access-token)"
for t in "$TOKEN_A" "$TOKEN_B"; do printf '%s' "$t" | cut -d. -f2 | tr '_-' '/+' | base64 -d 2>/dev/null | grep -o '"iss":"[^"]*"'; done
```
Expected: `"iss":"http://a.localhost:8080"` then `"iss":"http://b.localhost:8080"`.

Then in a browser (use the `claude-in-chrome` skill): open `http://a.localhost:8080`, sign in as `ada@collabhub.dev` / `collabhub`, reload the page, and confirm the user is still signed in (the reload spends the refresh cookie). Repeat at `http://b.localhost:8080`. Open the network panel on A and confirm API calls go to `http://a.localhost:8080/api/v1/...` and the WebSocket to `ws://a.localhost:8080/socket.io/…` — relative URLs resolved on A's origin.

- [ ] **Step 6: Criteria 3 and 5 — separate data, separate trust**

```bash
curl -s -X POST http://a.localhost:8080/api/v1/channels \
  -H "Authorization: Bearer $TOKEN_A" -H 'Content-Type: application/json' \
  -d '{"name":"only-in-a","kind":"public"}' | grep -o '"name":"only-in-a"'
curl -s http://b.localhost:8080/api/v1/channels -H "Authorization: Bearer $TOKEN_B" | grep -c only-in-a
curl -s -o /dev/null -w '%{http_code}\n' http://b.localhost:8080/api/v1/channels -H "Authorization: Bearer $TOKEN_A"
```
Expected: `"name":"only-in-a"`; `0`; `401`.

- [ ] **Step 7: Criterion 4 — one image**

```bash
for ns in collabhub-a collabhub-b; do
  kubectl --context k3d-collabhub -n "$ns" get pods -l app.kubernetes.io/component=frontend \
    -o jsonpath='{.items[0].status.containerStatuses[0].imageID}{"\n"}'
done
```
Expected: the same `sha256:` digest twice.

- [ ] **Step 8: Criterion 7 — idempotent, keys kept**

```bash
for ns in collabhub-a collabhub-b; do
  kubectl --context k3d-collabhub -n "$ns" get secret collabhub-auth -o jsonpath='{.data.AUTH_SIGNING_KEY}' | shasum
done > /tmp/keys-before
NAMESPACE=collabhub-a APP_ORIGIN=http://a.localhost:8080 scripts/deploy.sh infra
NAMESPACE=collabhub-a APP_ORIGIN=http://a.localhost:8080 scripts/deploy.sh app
# B again, with the same --set-string arguments as Step 3
for ns in collabhub-a collabhub-b; do
  kubectl --context k3d-collabhub -n "$ns" get secret collabhub-auth -o jsonpath='{.data.AUTH_SIGNING_KEY}' | shasum
done | diff /tmp/keys-before -
curl -s -o /dev/null -w '%{http_code}\n' http://a.localhost:8080/api/v1/channels -H "Authorization: Bearer $TOKEN_A"
```
Expected: both redeploys succeed; `diff` prints nothing, and the two keys differ from each other; `TOKEN_A` still gets `200`.

(Use the scratchpad directory rather than `/tmp` if the executor has one.)

- [ ] **Step 9: No regression for the default instance**

```bash
scripts/deploy.sh down && scripts/deploy.sh
```
Expected: `CollabHub is up at http://localhost:8080 — sign in as ada@collabhub.dev with password collabhub`.

- [ ] **Step 10: Report**

Report each criterion with its actual output, the `scripts/test.sh` result. Leave the worktree uncommitted and list the changed files (`git status --short`).
