# CollabHub — sample project for *Claude at Work*

This repo is the running sample project for **Claude at Work** (Manning), by Elton Stoneman.

It's a deliberately realistic codebase: a greenfield product with real design documents,
real architectural decisions, and real recurring maintenance work — the kind of project you'd
get Claude Code to build.

> [Claude at Work - repo](https://github.com/sixeyed/claude-at-work)

**CollabHub** is the product being built: a team collaboration platform that pairs a
Slack-like chat experience with a Figma-like collaborative canvas in a single app.

## Current state

Early-stage. **Auth is complete**, including federated sign-in through Dex.
**Messaging has its core**: channels with administration and membership,
messages with history, editing and deleting, and the Socket.IO `/messaging`
namespace carrying live delivery, the write path and typing indicators. Threads,
reactions, read receipts and search are not built — [doc 02
§3.1.5](docs/design/02-messaging-service.md) lists every endpoint the design
names and the service does not implement, with the reason for each. Canvas,
Asset and Worker are still scaffold — a process that reads its configuration and
answers `/health/live` and `/health/ready`, with no models, migrations, routes
or job handlers. **The SPA** has sign-in, a workspace switcher and the whole chat
shell. Chapters of the book add code, configuration and automation to this repo
as they go.

**[The open-decisions register](docs/design/07-open-decisions-register.md) is the
list of what is settled and what is not.** It is maintained as decisions are
made, and this README points at it rather than keeping a second copy that can
disagree with it — which is exactly what happened before. Every significant one
also has an ADR in [`docs/adr/`](docs/adr/).

Three are worth knowing before reading any code, because they constrain
deployment or the shape of everything above them. **D22** — the browser keeps its
refresh token in an `HttpOnly; Secure; SameSite=Strict` cookie, so the SPA stores
nothing at all and **the SPA and API must be deployed same-site**
([ADR](docs/adr/260728-refresh-token-in-an-httponly-cookie.md)). **D5** — Auth
federates to an upstream IdP and is never an OpenID Provider itself
([ADR](docs/adr/260728-federate-to-an-upstream-oidc-provider.md)). **D2** — an
access token is scoped to exactly one workspace, so switching is a token
exchange ([ADR](docs/adr/260727-single-active-workspace-per-token.md)).

Still open and worth knowing about: **D16** — retention values are unset, so nothing hard-deletes anything.

`collabhub-shared` carries the cross-cutting layer so the next service inherits it: RFC 7807
Problem Details, UUID v7, JWKS-backed verification, the token denylist, cursor pagination and
CORS. The job envelope and the `ObjectStore` protocol are still to come, and
`collabhub-contracts` is still empty.

## Where to read next

| | |
|---|---|
| [`docs/design/00-platform-conventions.md`](docs/design/00-platform-conventions.md) | **Start here.** The cross-service contract every service doc builds on. |
| [`docs/design/07-open-decisions-register.md`](docs/design/07-open-decisions-register.md) | What is still undecided, and what has been settled. |
| [`docs/adr/`](docs/adr/) | One file per significant decision, with the rejected options. |
| [`docs/platform/versions.md`](docs/platform/versions.md) | Tracked upstream versions for every platform component. |

Each component documents itself — how to run it, what it owns, and the rules that are easy
to get wrong:

| Component | Design doc | Service README |
|-----------|-----------|----------------|
| Auth | [01](docs/design/01-auth-service.md) | [src/services/auth](src/services/auth/README.md) |
| Messaging | [02](docs/design/02-messaging-service.md) | [src/services/messaging](src/services/messaging/README.md) |
| Canvas | [03](docs/design/03-canvas-service.md) | *scaffold* |
| Asset | [04](docs/design/04-asset-service.md) | *scaffold* |
| Worker | [05](docs/design/05-worker-service.md) | *scaffold* |
| Frontend SPA | [06](docs/design/06-frontend-spa.md) | [src/frontend](src/frontend/README.md) |

## Architecture

Five backend services, each independently deployable with its own database and its own
container image, plus a single-page frontend:

| Component | Role |
|-----------|------|
| Auth service | Identity, JWT issuance, workspace membership — the authorization source of truth |
| Messaging service | Channels, threads, messages, reactions; real-time delivery |
| Canvas service | Collaborative design documents — CRDT relay, presence, snapshot persistence |
| Asset service | File uploads and downloads via presigned object-storage URLs |
| Worker service | Headless background jobs: indexing, thumbnails, notifications, exports, retention |
| Frontend SPA | React + TypeScript client for both chat and canvas |

**Stack:** Python 3.12 · FastAPI / Uvicorn · SQLAlchemy + Alembic · Socket.IO · PostgreSQL ·
Redis (cache, real-time backplane, and job streams) · Elasticsearch · S3-compatible object
storage (Garage) · Dex · Kubernetes · OpenTelemetry into the Grafana LGTM stack.

Python was chosen over .NET — see
[ADR 260708](docs/adr/260708-python-instead-of-dotnet.md) for the reasoning.

```
docs/design/      Architecture and per-service design docs
docs/adr/         Architecture Decision Records
docs/platform/    versions.md — tracked upstream versions
docs/plans/       Strategy, delivery and per-slice implementation plans
src/services/     shared, contracts, and the five backend services (one uv workspace)
src/frontend/     React + TypeScript SPA (Vite)
tests/bdd/        The Gherkin acceptance suite — it spans every service, so it lives here
docker/           One folder per component: its Dockerfile and any files it needs
charts/collabhub/ Helm chart covering every component
charts/collabhub-deps/   Data stores, Dex, Secrets and Dex's Ingress for any environment; credentials required
scripts/          build.sh, test.sh, deploy.sh — the same entry points CI uses
.claude/skills/   Project skills: adr-writer, stack-update-checker
```

## Running it locally

Prerequisites: [uv](https://docs.astral.sh/uv/), Node 24, Docker. Deploying to Kubernetes
also needs [k3d](https://k3d.io), Helm and kubectl.

```bash
cp .env.example .env   # nothing in it is a real secret
scripts/test.sh        # lint, unit, then integration (integration needs Docker)
```

`scripts/test.sh` is the one entry point for checks, and CI runs it too. Name layers to run
fewer — `lint` is ruff, the CollabHub convention checks, eslint, tsc and `helm lint`; `unit`
needs no Docker; `integration` starts real Postgres, Redis and Dex containers (Conventions
§11). Anything after `--` goes to pytest:

```bash
scripts/test.sh unit                 # fast, no Docker
scripts/test.sh lint unit -- -x      # stop at the first failure
scripts/test.sh e2e                  # the browser journeys, on a stack it starts and stops
scripts/test.sh all                  # every layer, e2e included — what CI runs
```

The no-argument run is `lint unit integration`. The `e2e` layer is slower — it builds and
starts a whole Compose stack — so it runs when named, or as part of `all` (see
[Acceptance tests](#acceptance-tests)).

Every run rewrites [`docs/test-report.md`](docs/test-report.md) after each layer, pass or
fail: layer results, failures with their messages, the journeys feature by feature, and
tests and unit coverage per service. Commit it with the change it describes. A layer you
did not run keeps its last result, marked ⚠️ if that was at another revision, and a run
narrowed with `--` says so.

Bring up the full stack — Postgres, the three Redis instances, Dex, Garage, Elasticsearch,
the OTel collector, all five services and the SPA:

```bash
docker compose up --build
```

Then open <http://localhost:5173> and **sign in as `ada@collabhub.dev` with the password
`collabhub`** (or `grace@`, or `alan@`). Health checks are on `:8001` Auth, `:8002`
Messaging, `:8003` Canvas, `:8004` Asset, `:8005` Worker.

Every account owns a personal workspace *and* belongs to the shared **CollabHub
Demo** workspace. Two people only see each other's channels in the shared one, so
switch to it in the sidebar before trying anything with a second user.

Auth and Messaging have APIs — see their READMEs
([auth](src/services/auth/README.md), [messaging](src/services/messaging/README.md))
and their interactive docs at <http://localhost:8001/docs> and
<http://localhost:8002/docs>.

### Acceptance tests

The Gherkin suite in `tests/bdd/` drives a real browser through the whole stack.
**It truncates the messaging tables before every scenario** — scenarios like
"Ada's channel list is empty" cannot pass with real channels in the workspace —
so it runs against a throwaway stack, never the one you demo on.

`docker-compose.test.yml` is an override that gives that stack its own Compose
project name — and with it its own volumes — and moves the seven ports anyone
reaches from the host. **It runs alongside your development stack**, so you can
leave that up and keep working.

`scripts/test.sh e2e` does the whole round trip: it brings the test stack up and
waits until it is healthy, installs Chromium for Playwright if it is missing, runs
the suite, and takes the stack down again whether the scenarios passed or not. It
exits with pytest's status. It needs Docker and a `.env` (`cp .env.example .env`).

```bash
scripts/test.sh e2e                           # up, run, down
scripts/test.sh e2e -- --headed -k channels   # watch it drive the browser
KEEP_STACK=1 scripts/test.sh e2e              # leave the stack up afterwards
```

`KEEP_STACK=1` is for iterating on steps: with the stack left up, rerun just the
suite with `uv run pytest tests/bdd -m bdd`, which skips the build. What the script
does, by hand:

```bash
docker compose -f docker-compose.yml -f docker-compose.test.yml up -d --build --wait
uv run playwright install chromium
uv run pytest tests/bdd -m bdd
docker compose -f docker-compose.yml -f docker-compose.test.yml down
```

| | development | test |
|---|---|---|
| SPA | 5173 | **5183** |
| Auth | 8001 | **8011** |
| Messaging | 8002 | **8012** |
| Dex | 5556 | **5566** |
| Postgres | 5432 | **5442** |
| Asset | 8004 | **8014** |
| Garage (S3) | 3900 | **3910** |

Nothing else is published on the test stack — Canvas, Worker,
Elasticsearch and the OTel collector still run, they are just reached
over the Compose network by name. Asset and Garage are published because the
browser calls them directly (the upload handshake and the presigned PUT/GET).
Both stacks running means two of everything, Elasticsearch included. The test
stack runs Elasticsearch and the Worker anyway, because the search journey needs
both: the Worker indexes a posted message and Messaging searches the index.

`--wait` only means something for containers with a healthcheck, which is why the
frontend has one: it probes `/`, the same path the Helm chart's probes use.

Addressing only test-stack ports is also the safety interlock. The suite
truncates over 5442, so run against a machine with just the development stack up
it fails to connect rather than deleting your channels — it cannot tell the two
apart by looking, because they are the same images.

`down` without `-v` keeps the development stack's volumes. The test stack's are
dropped by the script itself before each run.

The suite runs against the test stack's frontend container, **not** `npm run
dev` — in dev, React's StrictMode fires the session restore twice, which spends
the rotating refresh token twice and signs the user out.

For frontend work where you are not running the acceptance tests, the Vite dev
server is faster than rebuilding the Nginx image:

```bash
cd src/frontend && npm install && npm run dev
```

The SPA's Messaging types are generated from that service's OpenAPI document
(register D23). After changing a Messaging route or schema:

```bash
uv run python -m messaging.openapi > src/frontend/openapi/messaging.json
cd src/frontend && npm run generate:api
```

### Object storage sets itself up

Garage will not serve S3 traffic until a cluster layout is assigned, and has no bucket, key or
CORS rules. `docker compose up` runs a one-shot `garage-bootstrap` service that does all of it
(layout, the `collabhub-assets` bucket, the app's key, and CORS for `GARAGE_CORS_ORIGINS`) and
exits; `asset` waits for it. It is the same script the test stack, k3d and the integration tests
run, and it is safe to run again.

**If your `.env` predates attachments, update it.** Garage only imports keys in its own format
(`GK` and 24 hex characters, then 64 hex), so the old `collabhub-local` key cannot be used:
take the new `OBJECT_STORE_*` values, `OBJECT_STORE_PUBLIC_ENDPOINT`, `GARAGE_ADMIN_TOKEN`,
`GARAGE_CORS_ORIGINS`, `MESSAGING_SERVICE_CLIENT_*` and `AUTH_SERVICE_CLIENTS` from
`.env.example` (or `cp .env.example .env`). `ASSET_INTERNAL_URL` is now Asset's origin, with no
`/api/v1/internal` path. A Garage volume made with the old key keeps it: `docker compose down
-v` starts it fresh.

The k3d deployment below does the same for you, and routes Garage's S3 API on `s3.<host>` so
the browser can PUT to a presigned URL. On the **lab**, `scripts/deploy.sh infra` now also needs
`--set-string messagingClientSecret=...`.

### Deploying to Kubernetes

`scripts/build.sh` and `scripts/deploy.sh` build the images and install the Helm chart into a
local [k3d](https://k3d.io) cluster — the same scripts CI will run:

```bash
scripts/test.sh && scripts/build.sh --push && scripts/deploy.sh
```

Then open `APP_ORIGIN` — `http://localhost:8080` by default — and sign in as
`ada@collabhub.dev` / `collabhub`, as above. Everything is on that one origin: the SPA and
every public API routed by `charts/collabhub`'s Ingress, and Dex by the dependency chart's,
both behind the Traefik Ingress k3s ships with.

| | |
|---|---|
| `scripts/build.sh [component...] [--push]` | Builds `localhost:5500/collabhub/<component>:<tag>`. The tag is the short commit SHA, plus `-dirty` for uncommitted changes |
| `scripts/deploy.sh cluster` | Creates the `collabhub` k3d cluster (k3s pinned to `versions.md`) and its registry on `localhost:5500` |
| `scripts/deploy.sh infra` | Installs KEDA (pinned to `versions.md`), then `charts/collabhub-deps` with `values-k3d.yaml`: Postgres, three Redis, Elasticsearch, Garage (bootstrapped), Dex, the OTel collector, the Secrets and Dex's Ingress |
| `scripts/deploy.sh app` | Installs `charts/collabhub` at the current tag. Migrations run as Helm hook Jobs before any pod rolls |
| `scripts/deploy.sh` | All three, in order. Idempotent — re-run it to upgrade |
| `scripts/deploy.sh status` / `down` | What is running / delete the cluster, its registry and **all its data** |
| `scripts/deploy.sh preview up` / `url` / `down` | This branch's app in `preview-<slug>`, public on two quick tunnels — see *Preview environments* |
| `NAMESPACE=… APP_ORIGIN=… scripts/deploy.sh` | Another instance on the same cluster, e.g. `NAMESPACE=collabhub-a APP_ORIGIN=http://a.localhost:8080`. `*.localhost` needs no DNS |

`scripts/deploy.sh infra -- <helm args>` and `app -- <helm args>` pass arguments to that
chart's Helm call.

The scripts never use your current kubectl context. Every call names `KUBE_CONTEXT` —
`k3d-collabhub` by default — and creating the cluster does not switch to it. `cluster` and
`down` refuse any context but `k3d-collabhub`; `infra` and `app` refuse k3d values on any other
context, and any other environment's values on it. `IMAGE_REGISTRY`, `IMAGE_TAG` and `KUBE_CONTEXT` override the defaults — see
`.env.example`.

An existing k3d cluster from before this change must be recreated once: the dependency release
was renamed from `collabhub-local` to `collabhub-deps`, and a new release cannot adopt the
resources the old one owns. `down` deletes the image registry too, so push again before
deploying:

```bash
scripts/deploy.sh down
scripts/deploy.sh cluster
scripts/build.sh --push
scripts/deploy.sh
```

k3d and the Compose development stack can run at the same time, but that is two of
everything, Elasticsearch included — give Docker the memory for it.

`charts/collabhub-deps` has **no default for any credential** (register D41) — it refuses to
render until each one is supplied, and names the one that is missing. On k3d they come from
`charts/collabhub-deps/values-k3d.yaml`, and it is those *values* that are **development
only**: the credentials are throwaway, Dex is full of demo accounts, and nothing is backed up.
`scripts/deploy.sh` keeps them off every cluster but `k3d-collabhub`.

Any other environment has its own `charts/collabhub-deps/values-<env>.yaml` — `deploy.sh`
requires one, if only for `ingress.className` — and can keep every credential out of it, on
the command line instead:

```bash
DEPLOY_ENV=<env> APP_ORIGIN=http://<host> scripts/deploy.sh infra -- \
  --set-string postgres.password=... \
  --set-string garage.adminToken=... \
  --set-string garage.rpcSecret=... \
  --set-string garage.accessKeyId=GK... \
  --set-string garage.secretAccessKey=... \
  --set-string dex.clientSecret=... \
  --set-string 'dex.passwordHash=$2b$10$...' \
  --set-string workerClientSecret=...
```

Single-quote the bcrypt hash: it is full of `$`. `--set-string` splits on commas, so a
credential passed this way may not contain one, and the Postgres password goes into a DSN
unescaped, so it must be URL-safe — letters, digits and `-_.~`. Garage only accepts keys in its
own format: `GK` plus 24 hex digits for the key ID, and 64 hex digits for the secret and the
RPC secret. Auth's signing key is optional — `--set-file auth.signingKey=signing.pem` — and is
otherwise generated on first install and kept.

Even with real credentials the chart is not production: nothing is backed up, Dex is a
password database, and the Secrets are rendered from values rather than a secret store.
Four things to know before running it anywhere but your laptop:

- **KEDA is cluster-wide.** `infra` installs it as release `keda` in namespace `keda`, at the
  pinned version. On a shared cluster that already runs KEDA, that upgrades or downgrades
  everyone's, so coordinate first.
- **Rotating Garage's key means a new key.** The bootstrap Job imports the key only when
  `garage.accessKeyId` is not already there, so a changed `garage.secretAccessKey` under the
  same ID is ignored. Change both together.
- **The Postgres password is fixed at first start.** It is set when the volume is first
  initialised, so changing `postgres.password` later breaks every service's connection
  unless you change the password in the database too.
- **`helm uninstall collabhub-deps` is not harmless.** It deletes the Auth signing-key
  Secret, which ends every session, and the `redis-streams` PVC, which loses any job not yet
  acknowledged.

### Preview environments

`scripts/deploy.sh preview up` deploys the current branch's whole app into its own namespace,
`preview-<slug>`, on the local k3d cluster, and makes it public on two
[cloudflared](https://github.com/cloudflare/cloudflared) quick tunnels — no account needed —
so someone on another network can use it. One tunnel serves the app, the other object storage
(a presigned URL's host is signed, and the app's host routes to the SPA).

```bash
scripts/deploy.sh preview up     # cluster, build, push, tunnels, deploy; prints both origins
scripts/deploy.sh preview url    # prints APP_ORIGIN=… and OBJECT_STORE_ORIGIN=… again
scripts/deploy.sh preview down   # stops the tunnels, uninstalls, deletes the namespace
```

- `cloudflared` must be on `PATH`. `BRANCH=<name>` names the preview instead of the checked-out
  branch (needed on a detached HEAD).
- A rerun reuses live tunnels. If either has died, `up` starts two new ones: the URLs change,
  so everyone signs in again, but the data is kept.
- **A quick tunnel does not survive the machine sleeping.** When its connection drops for long
  enough, Cloudflare deletes the tunnel; `cloudflared` keeps running and logs `Tunnel not found`
  for ever. `up` and `url` ask each URL as well as each process, so they see this as dead. Keep
  the machine awake while a preview is in use (`caffeinate -d` on macOS).
- Roughly 1.5–2 GB of memory per preview, most of it Elasticsearch.
- Do not run two `up` at once (both upgrade KEDA), nor `up` while `down` runs.
- `feature/a_b` and `feature/a-b` share one preview, because they share a slug.
- **Accepted risk:** anyone with a preview URL can sign in as the demo users
  (`ada@collabhub.dev`). The sign-in page no longer shows the credentials; the URL is the secret.
- A `~/.cloudflared/config.yml` written for a named tunnel is not meant for these quick tunnels.

### Deploying to the lab

`values-lab.yaml` exists for both charts: `charts/collabhub`'s carries ingress-nginx and
`AUTH_COOKIE_SECURE: "false"`; `charts/collabhub-deps`'s carries nothing but
`ingress.className` — every credential still arrives on the command line, as above.

```bash
export IMAGE_REGISTRY=<registry the lab pulls from>   # after `docker login` to it
export DEPLOY_ENV=lab APP_ORIGIN=http://<lab host> KUBE_CONTEXT=<lab context>
scripts/build.sh --push
scripts/deploy.sh infra -- \
  --set-string postgres.password=... \
  --set-string garage.adminToken=... \
  --set-string garage.rpcSecret=... \
  --set-string garage.accessKeyId=GK... \
  --set-string garage.secretAccessKey=... \
  --set-string dex.clientSecret=... \
  --set-string 'dex.passwordHash=$2b$10$...' \
  --set-string workerClientSecret=...
scripts/deploy.sh app
```

`IMAGE_REGISTRY` must be a registry the lab can pull from, with `docker login` done — the k3d
registry at `localhost:5500` is unreachable from it, which is why the block above sets it
explicitly rather than taking the default.

The lab is plain HTTP on a real hostname, not `http://localhost`, the one origin browsers
exempt from `Secure` — so its refresh cookie runs with `Secure` off (register D42). The
refresh token then travels the lab's network in clear; acceptable only because the lab is a
trusted network, and never copied to an environment reachable from outside one.

### What the chart expects of an environment

Three things the chart now needs, all per environment:

- **KEDA**, installed in the cluster — the chart fails to render without the `keda.sh/v1alpha1`
  API, since the Worker's `ScaledObject`s depend on it. No KEDA and don't want it? Set
  `components.worker.autoscaling.enabled=false` and the Worker renders as plain Deployments
  instead.
- **`networkPolicy.peers` set in a values file for that environment** — `postgres`,
  `redisCache`, `redisRealtime`, `redisStreams`, `elasticsearch`, `objectStore`,
  `otelCollector`, `oidcProvider`. Where Postgres, Redis and the rest actually live varies per
  cluster, so the chart ships no defaults for them, and the render fails, naming whichever
  peer is missing, until every one an enabled component needs is set. Don't want NetworkPolicy
  objects at all? Set `networkPolicy.enabled=false`.
- **A `REDIS_STREAMS_PASSWORD` key in the `collabhub-worker` secret**, and
  `components.worker.env.REDIS_STREAMS_ADDRESS` pointed at R3's `host:port` — KEDA's
  `TriggerAuthentication` and its `redis-streams` trigger read these directly; they are not
  parsed out of `REDIS_STREAMS_URL`.

`ingressController` and `dns` are the exceptions: they ship non-empty defaults (ingress-nginx
in namespace `ingress-nginx`; CoreDNS via `k8s-app: kube-dns` in `kube-system`), so they pass
the empty-peer check even on a cluster where they're wrong. That's silent — nothing fails — so
check them by hand for your cluster. Under a CNI that enforces NetworkPolicy, a wrong
`ingressController` peer blocks all public ingress traffic to every component.

The k3d environment is a worked example of all three: `deploy.sh infra` installs KEDA,
`charts/collabhub/values-k3d.yaml` sets every peer (k3s's Traefik as the ingress controller,
and k3s does enforce NetworkPolicy), and `charts/collabhub-deps` supplies the Secret keys.

```bash
helm lint charts/collabhub -f <env-values>.yaml --set components.worker.autoscaling.enabled=false
helm template collabhub charts/collabhub -f <env-values>.yaml --api-versions keda.sh/v1alpha1
```

`helm lint` has no `--api-versions` flag, so it can't see the KEDA API either way — the
`--set` above sidesteps that check the same way a KEDA-less cluster would. `helm template`
does take `--api-versions`, so pass it there instead once your peers are set.

The chart deploys CollabHub's own workloads only. Postgres, Redis, Elasticsearch and Garage
are expected to exist already — they have their own lifecycle and backups, and bundling them
would make `helm uninstall` a data-loss command.

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

## Working in this repo

Two project skills live in `.claude/skills/` and are used throughout the book:

- **adr-writer** — captures a decision and its rationale as an ADR in `docs/adr/`.
- **stack-update-checker** — compares each entry in `docs/platform/versions.md` against its
  upstream release feed, posts a digest of anything new to Slack, and writes the watermark
  back so the same release is never announced twice.

## License

MIT — see [LICENSE](LICENSE).
