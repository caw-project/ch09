# Portable deployment — one build, any environment

CollabHub can only be deployed to one place. `scripts/deploy.sh` installs
`charts/collabhub` with `values-k3d.yaml` and nothing else, that file writes
`http://localhost:8080` into four services' configuration, and the frontend image
has the same origin compiled into its JavaScript bundle. A lab cluster with its
own ingress hostname cannot run any of it.

This design makes the origin a deployment-time input rather than a constant, and
gives the app chart the routing it needs to be reachable. The target is a lab
cluster that has an ingress controller and nothing else: CollabHub brings its own
Postgres, Redis, Elasticsearch, Garage, Dex and OTel collector, exactly as it does
on k3d.

## 1. What is actually hardcoded

The build script is the smallest part of it. `scripts/build.sh` already reads
`VITE_AUTH_URL` and friends from the environment — they only *default* to
`K3D_ORIGIN`. The blockers are further down.

| Where | What |
|---|---|
| `docker/frontend/Dockerfile` | Vite inlines `VITE_*` into the bundle, so the image belongs to one origin. Two environments from one commit would need two images on the same `IMAGE_TAG` |
| `scripts/deploy.sh` (`cmd_app`) | Unconditionally passes `--values values-k3d.yaml`. There is no way to name an environment |
| `charts/collabhub/values-k3d.yaml` | `http://localhost:8080` as `AUTH_ISSUER` for four services and `SPA_REDIRECT_URI` for Auth |
| `charts/collabhub` | No Ingress at all. A cluster with an ingress controller has nothing to render against it |
| `charts/collabhub-local` | Holds the only Ingress, plus Dex and the Secrets — and refuses to install outside `k3d-collabhub` |
| `scripts/lib/common.sh` | `K3D_ORIGIN=http://localhost:8080`, used for the build args and the readiness check |

So this is not one string in one script. There is no concept of *an environment*
anywhere except k3d.

## 2. The organising idea

**`APP_ORIGIN` is the single source of the public origin, and no hostname is
written into any values file.** `deploy.sh` passes it to both charts at install
time with `--set-string`. A new environment is then a values file that says
nothing about where it lives, plus one environment variable.

That inverts today's arrangement, where the origin is a constant in
`common.sh` and a literal repeated seven times in `values-k3d.yaml`.

Two inputs identify an instance: `APP_ORIGIN` says where it is reached, and
`NAMESPACE` (today a constant in `common.sh`) says where it lives. Both become
overridable, so **one cluster can hold several instances** — which is also how
the design is proven (§7).

Note that nothing needs it at *build* time. Slice 1 makes the image
origin-agnostic, so `APP_ORIGIN` is purely a deploy-time input — one image, built
once, installed against whatever origin the environment supplies.

## 3. Slice 1 — the frontend image stops belonging to an environment

Every URL the SPA builds degrades correctly to a relative one when its base is
empty:

| Call site | With an empty base |
|---|---|
| `lib/auth/api.ts` — `fetch(\`${AUTH_URL}${path}\`)` | `/api/v1/auth/…` |
| `lib/auth/api.ts` — `loginUrl`, used by `location.assign` | a relative navigation |
| `lib/api/messaging.ts` — `createClient({ baseUrl })` | `/api/v1/channels` (`openapi-fetch` itself defaults `baseUrl` to `""` and builds `` `${baseUrl}${pathname}` ``) |
| `lib/realtime/socket.ts` — `io(\`${MESSAGING_URL}/messaging\`)` | `io('/messaging')` — the canonical same-origin namespace connect |

So one image serves every single-origin deployment: k3d, the lab, and anything
after them. The "frontend image is environment-specific" consequence recorded in
ADR 260914 stops being true, and with it the hazard of two different images
wanting the same commit's tag.

**New `src/frontend/src/lib/config.ts`** holds one pure function:

```ts
baseUrlFrom(value: string | undefined, devFallback: string): string
// undefined  → devFallback  (dev server and Vitest, where no VITE_ var is set)
// ''         → ''           (same origin — every ingress deployment)
// 'http://x/'→ 'http://x'   (trailing slash trimmed: '//api/v1' is a real bug)
```

It replaces the three duplicated `import.meta.env.X ?? 'http://localhost:800N'`
lines in `lib/auth/api.ts`, `lib/api/messaging.ts` and `lib/realtime/socket.ts`.
`src/test/api.ts` imports the same values rather than repeating them, so an MSW
stub cannot drift from the URL the app actually calls.

`build.sh` then defaults the four `VITE_*` build args to **empty** rather than
`$K3D_ORIGIN`, still overridable for a deployment that is not single-origin.

Compose is deliberately untouched. It passes explicit URLs from `.env` and it is
genuinely not same-origin — the SPA is on `:5173` and the APIs on `:8001`–`:8004`
— so relative URLs would be wrong there. The same applies to
`docker-compose.test.yml`, which builds its own frontend for `:8011`/`:8012`.

## 4. Slice 2 — environments in the scripts, routing in the app chart

### Scripts

- `common.sh` gains `DEPLOY_ENV` (default `k3d`) and `APP_ORIGIN` (default the
  k3d origin). `K3D_ORIGIN` stays, as the k3d default rather than the universal
  one.
- `common.sh`'s `NAMESPACE` becomes overridable, default `collabhub`.
- `deploy.sh cmd_app` uses `--values charts/collabhub/values-$DEPLOY_ENV.yaml`,
  and sets everything origin-derived with `--set-string`: `ingress.host` (the
  host part of `APP_ORIGIN`), Auth's `AUTH_ISSUER` and `SPA_REDIRECT_URI`, and
  `AUTH_ISSUER` for Messaging, Canvas and Asset.
- It also sets the Worker's `REDIS_STREAMS_ADDRESS` from `NAMESPACE`. KEDA's
  operator resolves that address from its own namespace, so it has to be fully
  qualified — and `values-k3d.yaml` currently hardcodes `.collabhub.` into it,
  the one place a second namespace would silently scale on the wrong Redis.
- **Arguments after `--` go to Helm**, as `test.sh` already passes them to
  pytest: `scripts/deploy.sh infra -- --set-string postgres.password=…`. That is
  how Secrets are supplied (§5).
- **The Ingress always has a host.** An empty host matches every host, which is
  fine for one instance and a routing collision for two. The k3d default origin
  `http://localhost:8080` gives the host `localhost`.
- **A mismatch guard in both directions.** Refuse `DEPLOY_ENV=k3d` against a
  non-k3d context, and refuse a non-k3d `DEPLOY_ENV` against the k3d context.
  Today's one-way check only stops the dev chart leaving the laptop; the new
  failure mode is a lab deploy landing on k3d, or a k3d values file landing on
  the lab.
- `cluster` and `down` stay k3d-only — they create and destroy a k3d cluster and
  mean nothing elsewhere.
- **The lab needs a registry it can pull from.** `IMAGE_REGISTRY` is already
  overridable, and `cmd_app`'s image precheck uses `docker buildx imagetools
  inspect`, which treats `localhost` as HTTP but uses ordinary `docker login`
  credentials for a real registry — so this needs no new code. It is still a
  prerequisite for a lab deploy, and worth stating because the k3d registry at
  `localhost:5500` is unreachable from anywhere else.
- `check_origin` runs for **every** environment, not only the local one. It
  fetches `/` and `/.well-known/jwks.json` through the ingress, which is the only
  step that proves routing as well as pods, and routing is the thing most likely
  to be wrong in a new environment.

### An opt-in Ingress in `charts/collabhub`

New `charts/collabhub/templates/ingress.yaml`, disabled by default:

```yaml
ingress:
  enabled: false
  className: ""
  host: ""          # required when enabled; deploy.sh sets it from APP_ORIGIN
  annotations: {}
  tls:
    enabled: false
    secretName: ""
```

**The public-prefix allow-list lives in the template, not in values.** Which
prefixes are public is application knowledge — and it is what keeps
`/api/v1/internal/` and `/health` unroutable (Conventions §5.5). Leaving it to
whoever writes a values file is how that rule gets lost. Host, class, annotations
and TLS are environment knowledge and stay in values.

This amends ADR 260914, which recorded that the chart has no Ingress because
routing is per-environment. The reasoning holds for *where* it routes; it does not
hold for *what may be routed*. Splitting it this way keeps the rule in the chart
and the address in the environment.

**The app chart's Ingress routes only CollabHub.** Dex gets its own Ingress from
the dependency chart, on the same host. Both ingress-nginx and Traefik merge rules
across Ingress objects that share a host, and it keeps the app chart from having
to know that Dex exists.

No NetworkPolicy template changes: `networkPolicy.peers.ingressController` is
already a value, and the default in `values.yaml` — ingress-nginx in namespace
`ingress-nginx` — is what the lab runs.

### Lint

`scripts/test.sh` enumerates values files by hand in `layer_lint`. It gains the
lab file alongside the k3d ones, both as a `helm lint` and as a `helm template`
render with `--api-versions keda.sh/v1alpha1`, so the Ingress and the ScaledObjects
are both checked.

## 5. Slice 3 — the dependency chart becomes any environment's

`charts/collabhub-local` → `charts/collabhub-deps`. The manifests do not change.
What changes is where their settings come from:

- `origin` and every credential become **required values with no defaults**.
- `values-k3d.yaml` carries today's throwaway credentials and
  `http://localhost:8080`.
- `values-lab.yaml` carries the lab's.
- The chart's Ingress shrinks to the `/dex` route; the app chart owns the rest.

Dev-only stops being a property of the chart and becomes a property of a values
file. **This is strictly safer than today.** Right now the chart carries throwaway
credentials as defaults and relies on `deploy.sh` refusing a non-k3d context — so
a hand-run `helm install` anywhere would succeed with a Dex full of demo accounts.
Afterwards it cannot render at all without credentials supplied deliberately.

Dex stays one template parameterised by `origin`, so this adds no fourth copy
beside `docker/dex/config.yaml` and `config.test.yaml`.

The rename carries into two other places: `LOCAL_CHART_FILES` in `common.sh`
becomes `DEPS_CHART_FILES` (the `--set-file` arguments for the Postgres init SQL,
`garage.toml` and the collector config are unchanged), and `test.sh`'s
`helm lint charts/collabhub-local` line follows the new name.

`deploy.sh infra` installs it with `--values charts/collabhub-deps/values-$DEPLOY_ENV.yaml`,
and keeps installing KEDA first — the lab needs it for the same reason k3d does.
KEDA is cluster-wide, so a second instance's `infra` finds it installed and
`helm upgrade --install` leaves it be.

### Secrets are applied with `--set`

Every credential the chart renders is **a scalar at a stable values path** —
`postgres.password`, `garage.accessKeyId`, `garage.secretAccessKey`,
`garage.adminToken`, `garage.rpcSecret`, `dex.clientSecret`, `dex.passwordHash`,
`workerClientSecret`.

Garage's two are the ones that needed a change to get there: its admin token and
RPC secret are literals in `docker/garage/garage.toml`, which the chart reads with
`--set-file`. Garage v2.3.0 takes `GARAGE_ADMIN_TOKEN` and `GARAGE_RPC_SECRET`
from the environment *in place of* the file's values, so the chart supplies both
from a Secret and the shared file stays as Compose needs it. None sits inside a list, and none is a pre-built JSON
string: `OIDC_PROVIDERS` and `AUTH_SERVICE_CLIENTS` are assembled in the template
from those scalars. So any of them can come from a values file, from
`--set-string` on the command line, or from a pipeline's secret store through the
`--` passthrough, without a values file ever holding them.

- `values-k3d.yaml` supplies throwaway credentials, so the local loop still needs
  no arguments.
- `values-lab.yaml` supplies **none**. The lab's arrive with `--set-string`, and a
  missing one fails the render with its path named.
- `--set-string`, not `--set`, so a Garage key made of digits stays a string. A
  bcrypt hash is `$`-heavy but has no commas, which `--set` would split on; it
  needs single quotes in the shell, and the README says so.

Auth's signing key is the exception and stays as it is: generated in the chart
and kept across upgrades with `lookup`. An `auth.signingKey` value, when set,
wins over both.

### `charts/collabhub/values-lab.yaml`

Carries only what is not the origin:

- `APP_ENV`, log level, replica counts.
- `AUTH_COOKIE_SECURE: "false"` — see below.
- `ingress.enabled: true` and `ingress.className: nginx`.
- NetworkPolicy peers for the data stores, matching the `collabhub-deps` pods.
  `ingressController` keeps the `values.yaml` default, which already names
  ingress-nginx.

### The refresh cookie on plain HTTP

The lab is `http://` on a real hostname. The refresh cookie is `Secure` and
`SameSite=Strict` (register D22, `auth/cookies.py`), and browsers only exempt
`http://localhost` from `Secure` — so on a lab hostname the browser accepts the
cookie's response, drops the cookie, and the user is signed out at the first
renewal with nothing in any log to say why.

`AUTH_COOKIE_SECURE: "false"` in `values-lab.yaml` is the answer, and the setting
already exists and is already plumbed through (`auth/settings.py`,
`routers/auth.py`, `routers/federation.py`). It needs no code change — but it puts
a thirty-day session token on the wire in clear, so it is recorded as a decision
rather than left as a line in a values file. It is confined to a lab on a trusted
network; any environment reachable from outside one needs TLS instead.

## 6. Testing

The test pyramid (D32) puts the failing test at the lowest layer that can prove
the behaviour.

- **Unit (pytest).** `within_idp` in `sign-in.py` — when a redirect has left
  the IdP — is a pure function over two URLs, tested before the script changes.
- **Lint-time render checks.** The Ingress must never route
  `/api/v1/internal/` or `/health`; `collabhub-deps` must refuse to render
  without credentials, and must render with every credential given only as
  `--set-string`. Each is a `helm template` check in `test.sh`, written to fail
  before the template change that satisfies it.
- **Unit (Vitest).** `baseUrlFrom` is a pure function over a string. `src/frontend/src/lib/config.test.ts` covers the
  three cases: absent, empty, and a value with a trailing slash. Written first,
  run red, before `config.ts` exists.
- **No new integration or BDD tests.** Nothing here changes a service's
  behaviour at its boundary. The BDD suite runs against Compose, which this
  design deliberately leaves alone.
- **Charts and scripts** are proven the way this repo already proves them:
  `helm lint` and a `helm template` render per values file in `scripts/test.sh`.
  This design does not invent a Helm test layer.

## 7. Acceptance criteria

**One k3d cluster, two instances of CollabHub, told apart only by `APP_ORIGIN`
and `NAMESPACE`, both working.** If any origin were still hardcoded — in the
image, a values file or a script — one of the two would be broken, so this proves
the design better than a single lab deploy could.

```bash
scripts/build.sh --push                       # once: one set of images for both
scripts/deploy.sh cluster
NAMESPACE=collabhub-a APP_ORIGIN=http://a.localhost:8080 scripts/deploy.sh infra
NAMESPACE=collabhub-a APP_ORIGIN=http://a.localhost:8080 scripts/deploy.sh app
NAMESPACE=collabhub-b APP_ORIGIN=http://b.localhost:8080 scripts/deploy.sh infra
NAMESPACE=collabhub-b APP_ORIGIN=http://b.localhost:8080 scripts/deploy.sh app
```

Both share k3d's one published port and Traefik routes on host. `*.localhost`
resolves to loopback in browsers and in curl, and browsers treat it as a
trustworthy origin, so the `Secure` cookie works without `AUTH_COOKIE_SECURE`.

It passes when:

1. `check_origin` succeeds for both origins — `/` and `/.well-known/jwks.json`,
   through the Ingress.
2. Signing in as `ada@collabhub.dev` works at `http://a.localhost:8080` **and** at
   `http://b.localhost:8080`, each through its own Dex, and the session survives a
   reload (which spends the refresh cookie).
3. A channel created in A does not appear in B — separate databases, not two
   routes to one.
4. Both frontend Deployments run the same image digest.
5. A token issued by A is rejected by B's Messaging: different issuer, different
   signing key.
6. The instance B credentials are supplied with `--set-string` through `--`, not
   from `values-k3d.yaml`, proving the Secret path works without a values file.
7. Re-running both deploys changes nothing, and each Auth's signing key survives.

Along the way:

- `scripts/test.sh` passes — lint (including the new values files), unit,
  integration.
- The bundle is built with each `VITE_*_URL` inlined as `""`, not `void 0`. The
  minifier folds `baseUrlFrom("")` to its result, so the call and the
  `http://localhost:8001` fallback literal are both gone from the bundle — the
  literal's *absence* is what shows Vite inlined the empty string, which is the
  same property. Vite's handling of an empty build arg is the one thing in slice
  1 not to take on faith.
- `src/services/auth/scripts/sign-in.py` signs in on a single origin. It stops
  following redirects when they leave the IdP's *host*, which cannot tell Dex
  from Auth when both are behind one ingress (recorded under *Found during
  verification* in `01-build-deploy-test-scripts-design.md`). Every k3d instance is
  single-origin, and criteria 2, 3 and 5 are checked with it, so it is fixed
  here: the IdP becomes host, port *and* path prefix.
- A plain `scripts/deploy.sh` with no overrides still gives the single instance
  at `http://localhost:8080` it gives today.

Two of everything — Elasticsearch included — is heavy. Give Docker the memory, and
expect `deploy.sh down` to remove both instances with the cluster.

`values-lab.yaml` is linted and rendered by `test.sh`, but the lab deploy itself
is not part of acceptance; the two-instance run proves the same properties on a
cluster anyone can create.

## 8. Decisions to record

Recorded in the slice that makes them, not swept up at the end.

- **Amend ADR 260914.** Two recorded consequences stop being true: the chart has
  no Ingress, and the frontend image is environment-specific.
- **New ADR** — per-environment values with an opt-in Ingress, and `APP_ORIGIN`
  as the single source of the public origin.
- **Register rows** for both of those, and a separate one for
  `AUTH_COOKIE_SECURE=false` on a non-TLS lab.
- **CLAUDE.md** — the repo layout (chart rename), the "no Ingress in the chart"
  line, and the dev-only wording that now describes `values-k3d.yaml` rather than
  the chart.
- **README** — the deploy table, and "What the chart expects of an environment",
  which currently tells the reader to write their own Ingress.
- **`.env.example`** — `DEPLOY_ENV` and `APP_ORIGIN` beside `IMAGE_REGISTRY`,
  `IMAGE_TAG` and `KUBE_CONTEXT`.

## 9. Out of scope

- TLS on the lab, and cert-manager. The lab is plain HTTP by decision; a TLS
  environment is a values file plus `ingress.tls`, which this design leaves
  ready but unused.
- A CI workflow that deploys to the lab.
- Removing a single instance. `deploy.sh down` deletes the cluster; a per-instance
  `uninstall` can come when something needs it.
- Real Secret management. `collabhub-deps` renders Secrets from values, which is
  right for a lab and wrong for production — Sealed Secrets, Vault or Key Vault
  is a separate decision.
- Canvas and Asset public routes. Neither has a public API yet, and the Ingress
  allow-list grows when they do.
- The `/socket.io` clash when Canvas gains real-time, which Messaging holds today.
