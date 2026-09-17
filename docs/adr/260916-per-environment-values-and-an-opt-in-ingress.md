# Per-environment values and an opt-in Ingress

- **Status:** Accepted
- **Date:** 2026-09-16

## Context

CollabHub could only be deployed to one place. `scripts/deploy.sh` installed
`charts/collabhub` with `values-k3d.yaml` and nothing else, and that file wrote
`http://localhost:8080` into four services' configuration — `AUTH_ISSUER` for
Auth, Messaging, Canvas and Asset, and `SPA_REDIRECT_URI` for Auth — as seven
literals. The frontend image had the same origin compiled into its JavaScript
bundle, because Vite inlines `VITE_*` at build time, so two environments from one
commit would have needed two images on the same `IMAGE_TAG`. `charts/collabhub`
had no Ingress at all: ADR 260914 put the only Ingress in the dev-only
`charts/collabhub-local`, alongside Dex and the Secrets, and that chart refuses to
install anywhere but the `k3d-collabhub` context.

A lab cluster — one with an ingress controller (ingress-nginx) and nothing else —
needed to run CollabHub the same way k3d does: its own Postgres, Redis,
Elasticsearch, Garage, Dex and OTel collector, reached through a public host that
is not `localhost`. Nothing in the app chart, the scripts or the frontend build
had a concept of *an environment* other than k3d, so none of that was possible
without hardcoding a second origin somewhere and duplicating most of what already
existed.

Two settled decisions constrain any answer. Register D22 puts the refresh token in
a `SameSite=Strict` cookie, so the SPA and the API must stay same-site in every
environment. Conventions §5.5 requires that `/api/v1/internal/` is never reachable
from a public ingress, in every environment, which is a stronger requirement than
"an Ingress exists" — it has to be true regardless of who writes the values file
for a given cluster.

## Decision

We will make `APP_ORIGIN` the single source of the public origin and `NAMESPACE`
the single source of an instance's identity. Neither is ever written into a
values file — both arrive at deploy time only.

- **Origin and namespace are deploy-time inputs, not chart content.**
  `scripts/deploy.sh` derives `ingress.host` from `APP_ORIGIN`'s host, `AUTH_ISSUER`
  for Auth, Messaging, Canvas and Asset, `SPA_REDIRECT_URI` for Auth, and the
  Worker's fully qualified `REDIS_STREAMS_ADDRESS` (which has to name `NAMESPACE`
  because KEDA's operator resolves it from its own namespace) — and sets every one
  of them with `--set-string`, never `--set`, since a host or an address can
  contain characters `--set` would otherwise split on.
- **`DEPLOY_ENV` selects `values-<env>.yaml`** for `charts/collabhub`, and a
  context guard runs in both directions: k3d values are refused against a
  non-k3d kubectl context, and a non-k3d `DEPLOY_ENV` is refused against the
  `k3d-collabhub` context. `scripts/deploy.sh up` runs only on k3d, because it
  also creates the cluster; any other environment runs `infra` then `app`
  directly against a cluster that already exists. `cluster` and `down` stay
  k3d-only and ignore `APP_ORIGIN` entirely — they only create or destroy the k3d
  cluster itself. Arguments after `--` on `infra` and `app` pass straight through
  to that chart's `helm` call, which is how an environment's own secrets reach a
  chart without ever sitting in a values file.
- **The SPA is built same-origin.** Every URL it builds degrades to a relative
  one when its base is empty — new `src/frontend/src/lib/config.ts` holds the
  pure function `baseUrlFrom` that each call site now goes through — so
  `scripts/build.sh` defaults the `VITE_*` build args to empty rather than to the
  k3d origin. One frontend image now serves every single-origin environment, k3d
  and a lab alike, with no per-environment rebuild and no risk of two images
  wanting the same commit's tag.
- **`charts/collabhub` gained an opt-in Ingress**, `templates/ingress.yaml`,
  `ingress.enabled` defaulting to `false`. The public-prefix allow-list — which
  prefixes may be routed — is fixed in the template, not in values, because it is
  application knowledge: leaving it to whoever writes a values file for a new
  cluster is how `/api/v1/internal/` or `/health` ends up routable by accident.
  Host, ingress class, annotations and TLS are environment knowledge and stay in
  values. The dependency chart (`charts/collabhub-deps`, below) keeps routing its
  own IdP, Dex, on the same host as a separate Ingress object that the controller
  merges with the app chart's — the app chart's Ingress never has to know Dex
  exists.

### The dependency chart (D41)

ADR 260914's `charts/collabhub-local` was the only thing that could supply what
`charts/collabhub` expects of an environment, and it refused every context but
`k3d-collabhub` because its credentials were throwaway defaults. A lab cluster with
nothing but an ingress controller needs exactly what it provides.

We will rename it **`charts/collabhub-deps`** and let it serve any environment, by
moving the reason it was development only out of the chart:

- **No credential has a default.** `postgres.password`, `garage.adminToken`,
  `garage.rpcSecret`, `garage.accessKeyId`, `garage.secretAccessKey`,
  `dex.clientSecret`, `dex.passwordHash` and `workerClientSecret` are empty in
  `values.yaml`, and every template reads them through one helper,
  `collabhub-deps.credential`, which fails the render naming the missing path and
  how to supply it. Each is a scalar, so it can come from a values file or from
  `scripts/deploy.sh infra -- --set-string <path>=<value>`, so an environment's
  values file never has to hold one.
- **Dev-only is a property of `values-k3d.yaml`**, which carries the throwaway
  credentials and the Traefik class. `scripts/deploy.sh` layers
  `values-$DEPLOY_ENV.yaml` over the chart's defaults, and the context guard keeps
  k3d values off every other cluster.
- **Garage's secrets reach it through a Secret.** `GARAGE_ADMIN_TOKEN` and
  `GARAGE_RPC_SECRET` replace the literals in `docker/garage/garage.toml`, which is
  shared with Compose, so the file can stay a dev copy while each environment
  supplies its own. The bootstrap Job reads the same Secret.
- **A supplied Auth signing key wins.** `auth.signingKey` is optional; set, it
  beats both the key already stored in the cluster and a generated one.

`scripts/test.sh lint` renders the chart once per credential, with that one left
out and the other seven supplied, and requires the render to fail naming it —
Helm stops at the first missing value, so a single render without credentials
would only ever check the first. It then renders with every credential on the
command line, so neither property can quietly regress. The Postgres password is
behind a Secret too, like every other credential the chart renders.

This is safer than before — the chart cannot render with throwaway credentials by
accident — but it is still not production: nothing is backed up, Dex is a password
database of demo accounts, and the Secrets are rendered from values rather than
read from a secret store. `--set-string` splits on commas, so a credential passed
that way may not contain one, and the Postgres password goes into a DSN unescaped
and must be URL-safe.

This amends [ADR 260914](260914-local-kubernetes-on-k3d-with-a-dev-only-dependency-chart.md),
which recorded that the app chart has no Ingress and that the frontend image is
environment-specific. Both statements stop being true; that ADR's Context and
Decision sections carry a dated note pointing here rather than being rewritten.

## Consequences

Several instances of CollabHub can now share one cluster, told apart only by
`APP_ORIGIN` and `NAMESPACE` — proven by running two on one k3d cluster, each with
its own database, its own signing key and its own Dex, neither able to see the
other's data or accept the other's tokens.

`/api/v1/internal/` staying unroutable is now the chart's job, fixed once in the
template, rather than something every environment's values file has to get right
on its own — and `scripts/test.sh` checks it at lint and render time, so a future
change to the allow-list is caught before it reaches a cluster.

A deployment that is not same-origin — the SPA and the API on genuinely different
origins — is no longer the default case, but it is still possible: it needs the
`VITE_*` build args exported explicitly at build time and `CORS_ALLOWED_ORIGINS`
set, since the relative-URL default that same-origin deployments get for free only
works when there is one origin to be relative to.

An existing k3d cluster from before this decision has to be recreated once: the
dependency release was renamed from `collabhub-local` to `collabhub-deps`, and a
new Helm release cannot adopt resources another release owns. `scripts/deploy.sh
down` also deletes the k3d image registry, so the sequence is `scripts/deploy.sh
down`, `scripts/deploy.sh cluster`, `scripts/build.sh --push`, then
`scripts/deploy.sh`.

### D42: the lab's refresh cookie without `Secure`

The lab is plain HTTP on a real hostname, not `http://localhost`, which is the
one origin browsers exempt from `Secure`. Left on, the refresh cookie set at
sign-in is silently dropped and every session dies at its first renewal;
`charts/collabhub/values-lab.yaml` turns it off with `AUTH_COOKIE_SECURE:
"false"`, so the thirty-day refresh token now travels the lab's network in
clear. That is acceptable only because the lab is a trusted network with no
public exposure — any environment reachable from outside one needs TLS instead,
which is what `AUTH_COOKIE_SECURE` staying at its `true` default protects.
Nothing about k3d changes: its `*.localhost` origin keeps `Secure`, which
browsers accept there, so the setting is one line in one environment's values
file rather than a new knob in the chart's defaults.

## Alternatives Considered

### A lab-only chart, separate from `charts/collabhub`

Keeping the app chart k3d-only and writing a second, lab-specific chart would have
avoided touching `charts/collabhub` at all. It would have duplicated most of the
app chart's manifests between the two, and put the public-route allow-list in two
places instead of one — exactly the kind of drift an opt-in Ingress inside the one
chart is meant to prevent.

### Hand-written lab manifests, outside Helm entirely

Writing the lab's Ingress and any other environment-specific objects by hand and
applying them directly would have needed no chart changes either. It is not
reproducible and not scriptable: nothing `scripts/deploy.sh` or a CI pipeline
could drive, and it would drift from the chart the moment either changed.

### Runtime SPA configuration via a fetched `config.json`

Having the SPA fetch its API origin from a small JSON file at load time, rather
than building same-origin, would also let one image serve several origins. It
solves a problem — the origin baked into the build — that building the SPA
same-origin already solves more simply: once the base URL is empty and every call
is relative, there is no origin left to configure at runtime, and no extra request
or failure mode to add.
