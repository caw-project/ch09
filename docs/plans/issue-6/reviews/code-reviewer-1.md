# Code review — issue 6, round 1: approved

The build does what the plan says, step by step. Every check the plan names is green, and the
record is written. Neither approved test file reaches `preview up` past its tool check, or
`preview down` at all, so I drove both through the real `deploy.sh` with fake
`k3d`/`docker`/`helm`/`kubectl`/`curl`. Each probe passed: the order, the reuse path, the
dead-tunnel restart, a failed build, and `down` touching only its own namespace. Two mutants of
`preview.sh` survive the approved tests, but the real code is right on both paths, so they go
under *Unpinned*. Three minor findings, all about comments and docs, go to the human.

## Expectations

Written from the issue, the plan, the red report, both plan reviews, the test review, the two
approved test files and the pre-change `deploy.sh`, `common.sh`, `test.sh`, the Messaging and
Garage templates and `App.tsx` (`git show HEAD:`), before the green report or any changed
production file was opened. (The plan's *Found while building* is inside the plan file, so I
saw it while reading the plan: it claims no departures and that `down` skips cluster work with
no `k3d`.)

### Task 4 — `common.sh` and `preview.sh`

- **No test pins:** decision 17's *together* (one 30 s budget for both logs, not 30 s each);
  decision 18's 5 s TERM→KILL; `tunnel_alive` re-checked before KILL; `sha1sum` else `shasum`;
  `--no-autoupdate` under `nohup` (the args are pinned, `nohup` isn't); the comment on
  `origin_s3_endpoint`; the header lines for `OBJECT_STORE_ORIGIN`, `BRANCH`, `PREVIEW_STATE_ROOT`.
- **Takes for granted:** that a restart into the *same* state dir starts from a clean log. Stop
  keeps the logs (decision 18, pinned) and `tunnel_url_from_log` takes the **first** match. A
  `>>` append, or no truncation, would make the second `up` after a dead tunnel read the dead
  tunnel's URL from the top of the log — the R6 restart path deploys on a URL nobody serves. No
  test starts twice in one directory. **Most likely wrong build; mutate/probe.**
- That `$!` after `nohup cloudflared … &` is cloudflared's pid (nohup execs), and that a
  background job of a non-interactive script survives the script's exit and a Ctrl-C (async
  commands ignore SIGINT without job control) — "tunnels left running" depends on it.
- **Could go wrong:** `preview_tunnels_live` ignoring the url files (test-reviewer finding 2,
  unpinned); `die` inside a captured `$(…)` or `local x="$(…)"` swallowed; a cut that strips
  more than one `-`; `rm -rf "$state"` with an empty component.

### Task 5 — `deploy.sh preview`

- **No test pins:** the whole `up` sequence (t-3 → t-2 cluster → t-1 build → t0 tunnels → t1
  infra → t2 app → t4 print); the reuse vs restart branch (R6); that the dead-tunnel path stops
  the *surviving* tunnel before starting two new ones (else an orphan `cloudflared` per rerun);
  `IMAGE_TAG` handed to `build.sh`; `cmd_infra` passing `objectStoreOrigin`; `cmd_app` passing
  `origin` and `object_store_endpoint` in place of `origin_s3_endpoint`; `resolve_origin` via
  `normalize_origin`; `down`'s order and its never naming `keda` or `k3d cluster delete`; `down`
  without a cluster; the header and `--help`.
- **Takes for granted:** `NAMESPACE` set by `preview_guard` in the main shell before
  `cmd_infra`/`cmd_app` (both use `helm_ns`); `require_matching_context` passing (DEPLOY_ENV=k3d
  guaranteed by decision 22); that `down` and `url` need neither `cloudflared` nor a cluster;
  `set -e` live where `preview_guard` is called (not under `if`/`||`).
- **Could go wrong:** too little — `OBJECT_STORE_ORIGIN` not reaching `cmd_infra` on the reuse
  path (Garage back on `s3.<app host>`, every presigned URL 404); generic `resolve_origin` still
  run for `preview`. Too much — `down` uninstalling KEDA or deleting the cluster; `up` starting
  tunnels before a failing build.
- **Issue premise to check in the code it leans on:** "new URLs, sign in again, data kept"
  (R6). A new `APP_ORIGIN` changes Dex's issuer `{origin}/dex`. If Auth keys a federated
  identity on the upstream issuer, Ada comes back as a *new* user with no workspace — the data
  is there but not hers. Read Auth's user lookup.

### Task 6 — charts

- **No test pins:** `values.yaml` comments (D40: set by `deploy.sh`, never a values file);
  `garage.yaml`'s comment; `values-k3d.yaml` header; every `layer_lint` render gaining `origin`
  (else `scripts/test.sh lint` fails); `layer_unit` requiring `helm`.
- **Takes for granted:** no values file already sets `CORS_ALLOWED_ORIGINS` (a duplicate key
  in the ConfigMap); `pydantic-settings` parses a JSON list from the env; nothing else renders
  `charts/collabhub` without `origin` (other tests, `deploy.sh status`).
- **Could go wrong:** `required` placed so the Ingress refusal at `test.sh` fires on `origin`
  first; an `objectStoreOrigin` with a port. Canvas also serves Socket.IO behind the same
  Traefik — R5 names only Messaging.

### Task 7 — SPA

- Only the paragraph goes; nothing else on the page changes. Pinned by Vitest.

### Task 8 — the record

D45 🟢 row and Settled line; an ADR (host-side quick tunnels, second tunnel not a path,
chart-set CORS list); `versions.md` cloudflared entry; doc 04 §4.1 and §6; conventions §5.6 and
§6; doc 02 :632-637 and messaging README; README preview section (commands, cloudflared,
BRANCH, rerun live/dead, 1.5–2 GB, no concurrent `up` nor `up` vs `down`, slug collisions,
sign-in risk, `~/.cloudflared/config.yml`) and a command-table row; `.env.example`; the sweep.

### Plausible wrong builds no test catches

1. Log appended/not truncated on restart → stale URL (R6 restart).
2. `preview_tunnels_live` ignores the url files.
3. Dead-tunnel path doesn't stop the survivor.
4. `cmd_app` still on `origin_s3_endpoint` / `cmd_infra` missing `objectStoreOrigin`.
5. Build after tunnels, or cluster after build.
6. `down` touching KEDA or the cluster.
7. Sequential 30 s + 30 s waits.
8. `layer_lint` renders missing `origin` → `scripts/test.sh lint` red.

## What ran

- `npm --prefix src/frontend test` → 50 files, **488 passed**. `run typecheck` clean, `run
  lint` clean, `run build` built (`dist/` is gitignored).
- `uv run pytest src/services/testkit/tests/unit src/services/messaging/tests/unit/test_realtime_server.py`
  → **100 passed**. That is testkit's 95 (60 old + 35 new) and realtime's 5.
- `uv run ruff check src/services/testkit src/services/messaging` → clean. `bash -n` on
  `deploy.sh`, `preview.sh`, `common.sh` and `test.sh` → clean. `conventions.py` over the 11
  changed script, chart, TS and Python files → no findings.
- `helm template` (app chart, k3d values, `origin` set, no `ingress.host`) → fails on `ingress.host
  is empty`. So `layer_lint`'s refusal check is still about the host, now that `origin` is
  required.
- **`scripts/test.sh` evidence.** `docs/test-report.md` shows lint passed, unit passed at 932,
  and e2e passed at 24, all at `560114e3b455-dirty`. Integration shows *not run*, which the plan
  meant. `build/test-results/{lint,unit,e2e}.json` all say `passed` at that revision.
  `e2e.xml` has `tests="24" failures="0" errors="0"`. The per-service counts sum to 932. All of
  this matches the green report's *What ran*.
- **Probes** (`build/sketch/services/testkit/tests/unit/test_review_probe.py`). They run the
  worktree's real scripts, with fakes on `PATH` that write each call to one ordered log:
  - **`preview up` three times** (probe 3) → **passed**.
    - First run: the calls go in the order `k3d cluster` → `docker build` (tag `t`) → two
      `cloudflared tunnel --no-autoupdate --url http://localhost:8080` → KEDA → deps (with
      `origin=<app>` and `objectStoreOrigin=<s3>`) → app (with `origin=<app>`,
      `OBJECT_STORE_PUBLIC_ENDPOINT=<s3>` and `ingress.host=<app host>`, in namespace
      `preview-t`) → `curl <app>/`. Stdout is exactly the two lines.
    - Second run, tunnels live: the same two lines, and no new tunnel.
    - Third run, after killing the s3 tunnel: the surviving app tunnel is stopped, two new
      tunnels start, both origins are new, deps gets the new `objectStoreOrigin`, and exactly
      two fakes are left alive.
  - **`preview up` with `docker build` failing** → **passed**. It exits non-zero and starts no
    tunnel.
  - **`preview down` on a running preview** → **passed**. It runs `uninstall collabhub --wait`,
    then `uninstall collabhub-deps --wait`, then `kubectl … delete namespace preview-t
    --ignore-not-found --wait`. No call names `keda`, no `k3d cluster delete/start/create`
    runs, and nothing touches `--namespace collabhub`. Both tunnels are stopped and the state
    dir is gone. A second `down`, with nothing installed, succeeds.
  - **`preview down` with no `k3d` on `PATH`** → **passed**. It calls no `helm` or `kubectl`,
    and removes the state.
  - **`preview down` with no `cloudflared` on `PATH`** → **passed**.
  - **`--help`** lists `preview up` and `preview down`. Bare `preview` dies with `expected
    'preview up'…` → **passed**.
  - **Plain `deploy.sh up`** → **passed**. It deploys to namespace `collabhub` with
    `origin=http://localhost:8080`, `objectStoreOrigin=` (empty) and
    `OBJECT_STORE_PUBLIC_ENDPOINT=http://s3.localhost:8080`, and starts no tunnel.
  - **Restart into the same state dir reads the new URL** (probe 1, real code) → **passed**.
  - **A live pair with an empty `s3.url` is not live** (probe 2, real code) → **passed**.
- **Mutants.** Each is a copy of `preview.sh` in `build/sketch/repo/scripts/lib/`. The six
  approved function tests ran against it through the approved module, rooted at the copy:
  - **M1, log appended (`>>`) instead of truncated** → the approved tests **survived** (6/6
    pass). Probe 1 failed against it: the restart read the dead tunnel's URL.
  - **M2, `preview_tunnels_live` ignores the url files** → **survived** (6/6). Probe 2 failed
    against it.
  - **M3, stop signals any live pid** → **caught** by
    `test_stopping_stops_cloudflared_and_nothing_else`.
  - **M4, `tunnel_alive` accepts any live process** → **caught** by
    `test_a_live_tunnel_is_a_running_cloudflared` and the stop test.
  - **Not mutated:** `deploy.sh`'s preview commands. No approved test runs them past t-3, so
    every mutant there survives by construction; probes 3 and 4 hold them instead. The charts
    weren't mutated either: the red run is their mutant, since all five chart reds failed on
    the unchanged templates, and the tests parse YAML for the exact values.

## Conformance

| Plan task or decision | Code | Outcome |
|---|---|---|
| T4 `normalize_origin`, `object_store_endpoint`, `OBJECT_STORE_ORIGIN`, header, `origin_s3_endpoint` comment | `common.sh` | as planned |
| T4 slug/namespace (d19–21), `preview_branch`, `preview_state_dir` (d9) | `preview.sh:14-67` | as planned |
| T4 URL read, wait, `tunnel_alive` (d12), live, start (d16, d17 together), stop (d18) | `preview.sh:71-163` | as planned. KILL after 5 s without re-checking `tunnel_alive`; harmless |
| T5 source `preview.sh`; `resolve_origin` via `normalize_origin`; `cmd_infra`/`cmd_app` values | `deploy.sh` | as planned (probe 3, plain-`up` probe) |
| T5 argument parsing, Helm args refused (d22), generic `resolve_origin` skipped | `deploy.sh:311-379` | as planned |
| T5 `preview_guard` (d22), one assignment a line | `deploy.sh:242-252` | as planned |
| T5 `cmd_preview_up` t-3…t4 | `deploy.sh:254-281` | as planned (probe 3) |
| T5 `url` (d23), `down` (d24) | `deploy.sh:283-309` | as planned (probe 4, approved url tests) |
| T5 header and `--help` | `deploy.sh:12-24` | as planned |
| T6 `origin` value, Messaging list, checksum (d14, d15) | configmap, deployment, values | as planned |
| T6 `objectStoreOrigin`, Garage host and comment | deps values, `garage.yaml` | as planned |
| T6 Messaging's comment block says its list comes from `origin` | `values.yaml` | **departed**: the note landed in Asset's block (finding 1) |
| T6 `values-k3d.yaml` header; `layer_lint` origins; `layer_unit` needs helm (d26) | | as planned |
| T7 hint removed | `App.tsx` | as planned |
| T8 D45, ADR, versions, doc 04, conventions §5.6/§6, doc 02, messaging README, README, `.env.example` | | as planned; two stale phrases (findings 1, 2) |
| T8 sweep | | **incomplete** — `values.yaml:187` matches the plan's own grep pattern (finding 1) |
| T9 verification | test report | as planned; `versions.md` version left blank for the human |

## Findings

### 1. `charts/collabhub/values.yaml` comments: one stale, one misplaced — minor
**Where:** `charts/collabhub/values.yaml:186-190`, `:196` · **Checked:** read; Grep for the
plan's sweep pattern.

Asset's `OBJECT_STORE_PUBLIC_ENDPOINT` comment still says "Derived from APP_ORIGIN
(s3.<host>)". It is now `OBJECT_STORE_ORIGIN` when that is set. This line matches the sweep
pattern Task 8 names (`s3\.<host>`), so the report's "sweep grep found nothing stale" is not
quite true.

The old Asset note "No CORS_ALLOWED_ORIGINS: behind the one ingress…" became "CORS_ALLOWED_ORIGINS
is not set here: Messaging's comes from `origin`", on one overlong line, still inside Asset's
block. Task 6 asked for Messaging's comment block to say where its list comes from, and that
block has no such comment. A reader of Messaging's `env` won't learn that the configmap adds
the key.

**What settles it:** reword `:187`, and move the sentence into Messaging's block.

### 2. Doc 04 §4.1 ends on a half-stale clause — minor
**Where:** `docs/design/04-asset-service.md:170-172` · **Checked:** read.

The sentence says k3d uses `OBJECT_STORE_ORIGIN` when it is set, else `s3.<host>`, then ends
"`scripts/deploy.sh` sets it from `APP_ORIGIN`". The §6 row has it right. Change the end to
"from `OBJECT_STORE_ORIGIN` or `APP_ORIGIN`".

### 3. `preview down` says "no k3d cluster" when Docker is down — minor
**Where:** `deploy.sh:292-309` · **Checked:** read (`cluster_exists` is `k3d cluster get`).

With `k3d` installed but Docker stopped, `cluster_exists` fails. `down` then logs "no k3d
cluster", removes the state and succeeds, while the namespace and both releases stay in the
stopped cluster. Nothing is lost: the namespace comes from the branch, so `down` run again
once Docker is up removes them. But the message misleads. Decision 24 accepts a stopped cluster
failing loudly, and this case comes out quiet instead. It is the human's call whether to say
so in the log line.

## Unpinned

What only reading, or my probes, protect. A later change can break any of these with every
approved test still green:

- **The restart truncates each log** (`preview.sh:122`, `>`). Mutant M1 survived. Without the
  truncation, the R6 restart would deploy on the dead tunnel's URL. Probe 1 shows the real
  code reads the new one.
- **`preview_tunnels_live` needs both url files** (`:108-109`). Mutant M2 survived; probe 2
  passes on the real code.
- **The whole `preview up` sequence**, as probe 3 checked it: the order, `objectStoreOrigin`
  and `OBJECT_STORE_PUBLIC_ENDPOINT` reaching the charts, the reuse path, and the survivor
  stopped on restart. Also **a failed build starting no tunnel**.
- **`preview down`'s scope**, as probe 4 checked it: no KEDA, no cluster change, only
  `preview-<slug>`.
- **One 30 s budget for both URLs** (`:125-138`). Read, not tested; a sequential build would
  pass every test.
- A test file built from these probes, with fake `k3d`/`helm`/`kubectl` recording their calls,
  would pin all of the above cheaply. That is for a later issue; nothing here is wrong.

## Left for the human

- **Findings 1–3** (minor): one comment fix and one comment move in `values.yaml`, a clause in
  doc 04, and optionally the wording of `down`'s log line.
- **`docs/platform/versions.md`**: cloudflared's `current_stable` is blank. Fill it in from
  the first real run, as the green report says.
- **The first real run** (green report, *Left for the human* 1–5). Check Host forwarding
  first. Then compare the banner format with `tunnel_url_from_log`, check DNS for a new host
  within `check_origin`'s 60 s, and run the issue's *Acceptance* list.
- **Checked, not a risk:** R6's "sign in again, data kept". Auth keys a federated identity on
  `oidc:<provider name>` plus the subject (`auth/oidc.py:72-74`), not on the issuer URL. So
  Dex's issuer moving to a new tunnel doesn't turn Ada into a new user.

## Checked and sound

- Mutants M3 (stop signals any live pid) and M4 (`tunnel_alive` without the command check):
  caught.
- Probes 3 and 4, the `--help` probe and the plain-`up` probe: passed on the real code (above).
- `die` inside a capture: every capture in `preview_guard` and `preview_start_tunnels` is its
  own assignment under `set -e`. `preview_namespace`'s `slug="$(…)"` is a plain assignment.
- `nohup … >log 2>&1 </dev/null &`: `$!` is cloudflared's pid, and no pipe is held open
  (the approved start tests would hang otherwise).
- `CORS_ALLOWED_ORIGINS` is set by no values file, so the ConfigMap has no duplicate key.
  `messaging/settings.py:33` is `list[str]`, which pydantic-settings reads as JSON.
- Canvas doesn't call `socket_allowed_origins`, so R5's Messaging-only scope leaves no
  Socket.IO server behind on the predicate.
- R9: only the paragraph went. `check_origin`'s k3d credentials line is unchanged.
- Nothing outside the file map changed. The approved test files match the red report, and the
  only change to `App.test.tsx` and `test_realtime_server.py` is the red tests. No generated
  file was touched.
- The docs: the D45 row and Settled line, the ADR, conventions §5.6 and §6, doc 02, the
  Messaging README, the README section and table row, and `.env.example` all say what the code
  does.
