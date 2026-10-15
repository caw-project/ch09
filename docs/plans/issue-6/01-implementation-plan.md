# Preview environments on k3d — implementation plan

> **For agentic workers:** this plan is executed by `scripts/deliver.sh`: the test-writer does every
> RED task, the code-writer every GREEN one. Three project rules override the superpowers skills.
> **Never commit** — every task ends with the worktree dirty. **Red first** — no production code
> until the test-reviewer has approved the failing tests. **Plans live in `docs/plans/`.**

**Goal:** `scripts/deploy.sh preview up` deploys the branch's whole app into `preview-<slug>` on
the local k3d cluster, public on two Cloudflare quick tunnels; `preview url` and `preview down`
complete the lifecycle; and the SPA's sign-in page stops showing the demo credentials.

**Architecture:** A new `scripts/lib/preview.sh` holds the parts that can be proven without a
cluster — the branch→namespace rule, reading a tunnel's URL, starting, detecting and stopping
`cloudflared` — as small bash functions. `deploy.sh` gains a `preview` command that strings them
together with the existing `cmd_cluster`, `cmd_infra` and `cmd_app`. A second origin,
`OBJECT_STORE_ORIGIN`, reaches `charts/collabhub-deps` as `objectStoreOrigin` (the Garage Ingress
host) and Asset as `OBJECT_STORE_PUBLIC_ENDPOINT`; unset, both stay `s3.<APP_ORIGIN host>`.
`charts/collabhub` gains a required `origin` value and renders Messaging's `CORS_ALLOWED_ORIGINS`
from it, so the Socket.IO handshake is checked against the configured origin in every
environment. The bash functions, the `preview` command and the chart renders are tested from
pytest, under `src/services/testkit/tests/unit/`, which drives `/bin/bash` and `helm template` as
subprocesses (decision 10, *Corrections* 4).

**Tech Stack:** bash 3.2, Helm 3, k3d/k3s Traefik, cloudflared quick tunnels · Python 3.12,
python-socketio/engine.io, pytest · React 19, Vitest + MSW.

**Issue:** `docs/plans/issue-6/00-issue.md` — read it first. This plan argues from it and does not
repeat it.

**Worktree:** `../caw-issue-6`, branch `feature/issue-6`, from `main` at `560114e`.

## Decisions

Decided by the issue:

| # | Question | Answer |
|---|---|---|
| 1 | Scope | R1–R9; *Not in this issue* stays out |
| 2 | Tunnels | Quick tunnels, no account; `cloudflared` on the host, started by the script; never watched (R6 handles a dead one on the next `up`) |
| 3 | Values | `values-k3d.yaml` and its throwaway credentials; no new `DEPLOY_ENV` |
| 4 | Accepted risk | Anyone with a preview URL can sign in as the demo users |
| 5 | The Socket.IO fix | In the chart (R5), not Traefik configuration; `[APP_ORIGIN]` in every environment |
| 6 | Concurrency | Two `up` runs at once are unsupported and documented, not locked |
| 7 | Slug collisions | `feature/a_b` and `feature/a-b` share a preview; documented |
| 8 | Register | D45 🟢; builds on D40, D41, D22; D42 untouched (a preview is https and keeps `Secure`) |

Taken in this plan — each needs the plan-reviewer's yes or no:

| # | Question | Answer | Why, and the alternative |
|---|---|---|---|
| 9 | Where the state directory lives (left to the plan) | `<git common dir>/collabhub-previews/<namespace>/`, overridable with `PREVIEW_STATE_ROOT`. Holds `app.pid app.log app.url s3.pid s3.log s3.url` | Inside `.git`, so never tracked, and shared by every worktree of the repo: a preview belongs to a branch, `BRANCH=x preview down` must work from any checkout, and two colliding slugs then share tunnels as well as a namespace — what decision 7 accepts. `$REPO_ROOT/build/` (gitignored) would be per worktree and orphan tunnels on a collision; `$TMPDIR` is machine-wide but not tied to the repo. `PREVIEW_STATE_ROOT` exists so the bash tests never touch the real one |
| 10 | How the script and chart code is tested (left to the plan) | Pure functions in `scripts/lib/preview.sh`, sourced by `deploy.sh`. Tested by two pytest files in `src/services/testkit/tests/unit/` — `test_preview_script.py` (bash, through `/bin/bash -c` subprocesses) and `test_preview_charts.py` (`helm template` subprocesses) — so `scripts/test.sh unit` runs them | `deploy.sh` runs its main body when sourced, so nothing in it can be tested in isolation; same pattern as `common.sh`'s `origin_host`. Pytest under `tests/unit/` is the one place the pipeline lets the test-writer write, the test pair run (`uv run pytest`) and the code-writer not edit (`deliver.sh:441-447, 535-569`). `testkit` already tests repo files that belong to no service (`test_images.py` reads `docker-compose.yml`). A subprocess is outside pytest-socket's reach, and neither bash nor `helm template` touches the network or Docker. Alternative: `scripts/tests/*.test.sh` run by `layer_lint`, as the issue says — the pipeline can't write, run or protect it (*Corrections* 4) |
| 26 | `helm` in the unit layer | `layer_unit` requires `helm` (`require_cmd npm helm`); the chart test module fails, never skips, when `helm` is not on `PATH` | A skipped chart test reads as green. `layer_lint` already requires it, so every machine that runs `scripts/test.sh` has it |
| 11 | Chart value names (left to the plan) | `charts/collabhub-deps`: `objectStoreOrigin` (beside the existing `origin`). `charts/collabhub`: a new top-level `origin` | Mirrors the deps chart's `origin`, whose `required` message the app chart reuses |
| 12 | How `up` detects a live tunnel (left to the plan) | Both pid files name a running process whose command line contains `cloudflared tunnel`, **and** both URL files are non-empty | `kill -0` alone is fooled by a reused pid after a reboot — exactly the dead-tunnel case R6 is for |
| 13 | Where `OBJECT_STORE_PUBLIC_ENDPOINT` is derived | `object_store_endpoint` in `common.sh`, beside `origin_s3_endpoint`; `cmd_app` passes its result as today | The app chart receives it as a literal (`values.yaml:181-186`); moving the derivation into the chart would also mean taking it out of `components.asset.env`. See *Corrections* 2 |
| 14 | Messaging's `CORS_ALLOWED_ORIGINS` | Rendered by `templates/messaging/configmap.yaml` from `required … .Values.origin`, as a one-item JSON list; `deploy.sh` sets `origin` | R5 says the chart sets it. A `--set-string components.messaging.env.CORS_ALLOWED_ORIGINS=…` from `deploy.sh` would not be "the chart", and no lint check could see it |
| 15 | Messaging's pods when the origin changes | Its `checksum/config` hashes `list $component.env $.Values.origin` | The new key comes from outside `$component.env`, so the existing checksum (`messaging/deployment.yaml:20`) would not see it. Today `AUTH_ISSUER` changes with the origin anyway; this keeps it true if that ever stops |
| 16 | `cloudflared` arguments | `cloudflared tunnel --no-autoupdate --url http://localhost:8080` (`$K3D_ORIGIN`), each under `nohup`, output to its `.log` | `--no-autoupdate`: an update restarts the process, which for a quick tunnel means a new URL nobody is told about |
| 17 | Waiting for the URLs | Both logs polled together once a second, 30 s in all (the *Timing* t0..30s); on a miss both are stopped and `up` fails naming the role and its log | As the issue's timeline |
| 18 | Stopping a tunnel | `TERM`, wait up to 5 s, then `KILL`; never signal a pid that `tunnel_alive` rejects | A pid file can outlive its process; killing whatever reused the pid would be a bug a developer never traces |
| 19 | The cut — **assumed** | When `preview-<slug>` exceeds 63, keep its first 56 characters, trim any trailing `-`, then append `-<6 hex>` | The issue says "cut … suffixed … within the 63" but not where. 56 + 7 = 63. Trimming keeps R1's "runs collapsed" true across the join. Changing it later is one line and two tests |
| 20 | A branch with no `[a-z0-9]` at all — **assumed** | Refused: `branch '<b>' has no letters or digits to name a preview after` | `preview-` is not a valid namespace. Alternative: name it from the hash alone. One branch and one test |
| 21 | Non-ASCII — **assumed** | Every *byte* outside `[a-z0-9]` becomes `-` (`LC_ALL=C`), so `fé/x` → `f-x` | The same answer on macOS and Linux whatever the locale. One test |
| 22 | Overrides the preview owns — **assumed** | `preview` refuses a set `APP_ORIGIN` or `OBJECT_STORE_ORIGIN`, a `NAMESPACE` other than `collabhub`, `DEPLOY_ENV` ≠ `k3d`, and Helm arguments after `--`. An explicit `NAMESPACE=collabhub` can't be told from the default — `common.sh:39` fills it before `deploy.sh` looks — and is ignored like the default | Each would be silently overwritten or contradict decision 3. Refusing is the smaller surprise; relaxing one later is one line |
| 23 | `preview url`'s output — **assumed** | stdout: `APP_ORIGIN=<A>` then `OBJECT_STORE_ORIGIN=<B>`; tunnels not live → `die "preview <ns>'s tunnels are not running — run scripts/deploy.sh preview up"`, exit 1 | The lines can be `eval`'d or pasted into a later command; a non-zero exit lets a script tell the cases apart. Changing either is a few lines and one test |
| 24 | `preview down` and the cluster — **assumed** | It never creates or starts the cluster. No cluster: stop tunnels, remove state, succeed. Cluster exists: uninstall each release that `helm status` finds, delete the namespace with `--ignore-not-found --wait`, then remove state | R8's "does what is left and succeeds". A stopped cluster makes `helm` fail after the tunnels are already stopped, which `set -e` reports |
| 25 | The R5 unit test | A characterisation test that **passes before any change**, as the issue's *Tests* asks | R5 changes no Python: engine.io already compares an explicit list as given. The test pins that library behaviour so a later change to `socket_allowed_origins` can't quietly undo R5 |

Nothing here touches a 🔴 entry. The nearest is **D37** (what the SPA does on a 401 from a token
revoked early): new tunnels give a new issuer, so old tokens fail — but they fail on a URL that no
longer resolves, and the user signs in again on the new one (*Where the rules meet*). No
renewal path changes. **D28** (preferences) is not touched: removing the sign-in hint stores no
choice.

## Corrections to the issue

1. **The cluster comes before the build.** *Timing* puts `scripts/build.sh --push` at t-1, first;
   but it pushes to `localhost:5500`, the registry `cmd_cluster` creates
   (`scripts/k3d/cluster.yaml:20-27`). So `preview up` runs `cmd_cluster` (t-2) before the build.
   A build failure still starts no tunnel.
2. **`OBJECT_STORE_PUBLIC_ENDPOINT` is not a `helm template` check.** *Tests* lists it under the
   chart checks, but `deploy.sh` sets it as a literal (`deploy.sh:166`); the chart renders whatever
   it is given. It is proven in the bash test of `object_store_endpoint` (Task 1). The Garage
   Ingress host is a chart check, as the issue says.
3. **Design doc 02 is already stale here.** `02-messaging-service.md:632-637` says
   `cors_allowed_origins` is passed as `settings.cors_allowed_origins or None`; the code passes
   `socket_allowed_origins(…)` (`realtime.py:184`). Task 8 rewrites the paragraph.
4. **The bash and chart tests run in the unit layer, from pytest, not in `scripts/test.sh lint`.**
   *Tests* asks for "`helm template` checks in `scripts/test.sh`" and "a small test `scripts/test.sh
   lint` runs". Under `scripts/deliver.sh` a file under `scripts/` is outside the test-writer's
   write scope (`deliver.sh:541-546`), neither test stage may run `bash` or `helm` directly
   (`:441-447`), and the code-writer could edit it after the gate (`write_denied`, `:560-567`). So
   the same checks are pytest tests under `src/services/testkit/tests/unit/` (decision 10), run by
   `scripts/test.sh unit`, which now needs `helm` (decision 26). They cover every clause the issue
   lists for those layers. `layer_lint`'s existing Helm renders stay where they are and gain
   `origin` (Task 6).

## Test approach — recommendation to the test pair

**TDD. No new scenario.** Everything here is a script, a chart or one SPA rule. The issue rules a
journey out (a real tunnel can't run headless), and the existing journeys already drive the
sign-in page, so they run once in verification.

| Behaviour | Layer | File |
|---|---|---|
| R1 slug rule, branch, detached HEAD; R2 two tunnels to `localhost:8080`, URL read, live/dead detection, stop; R4 `object_store_endpoint`; R7 `preview url`; R2's refusal without `cloudflared`; decision 22 | unit (pytest → `/bin/bash`) | `src/services/testkit/tests/unit/test_preview_script.py` |
| R4 Garage Ingress host from `objectStoreOrigin`, default unchanged, Garage CORS still the app origin; R5 Messaging's list in k3d and lab; `origin` required; decision 15 | unit (pytest → `helm template`) | `src/services/testkit/tests/unit/test_preview_charts.py` |
| R5 engine.io takes the explicit list as given behind a proxy that says `ws` | unit | `messaging/tests/unit/test_realtime_server.py` |
| R9 no email or password on the sign-in page | Vitest | `src/frontend/src/App.test.tsx` |
| R3, R6, R8's cluster half; the four *What this assumes* items; every *Paths* row that needs a real tunnel | the human's first real run | Task 9 hands it over |

**What no test covers:** anything that needs a running `cloudflared` against Cloudflare or a
cluster — `cmd_infra`/`cmd_app` with two https origins, Host forwarding, SigV4 through the tunnel,
Socket.IO over `wss://`, `helm uninstall` and the namespace delete. Bash 3.2 compatibility is
proven on macOS because every script test runs `/bin/bash`, which is 3.2 there.

**Nobody in the pipeline can check *What this assumes* — the human's run is the first check, after
the build.** The code-writer may not run `scripts/deploy.sh`, `cloudflared`, `curl` or `kubectl`
(`deliver.sh:503-517`), so the issue's "check before building on it" cannot happen inside this run.
The written evidence, none of it verified against an installed binary (no `cloudflared` source is
in the repo or the workspace):
- **Host forwarding** — cloudflared's origin parameter `httpHostHeader` ("sets the HTTP Host header
  on requests sent to the local service") defaults to empty, which leaves the browser's Host as it
  arrived; and dev servers behind quick tunnels are widely reported refusing the
  `*.trycloudflare.com` Host, which only happens if it is forwarded.
- **The URL banner** — the `|  https://<words>.trycloudflare.com  |` box on stderr, which the fake
  and `tunnel_url_from_log` follow; the first run records the installed version's actual format.
- **Traefik's `X-Forwarded-Proto`** — R5 is right whether or not it holds.
- **DNS for a new host** — no evidence either way; `check_origin`'s 60 s is the issue's assumption.

If the human's run finds `Host` rewritten, that is the issue's "the plan stops here": record it,
change nothing, and take it back to the issue — no `--http-host-header` workaround, which would
collapse both tunnels onto one Ingress host. If a new host fails to resolve within `check_origin`,
it is the fourth assumption failing, not a routing bug; rerunning `preview up` reuses the tunnels
and retries the check.

**Baseline**, from `docs/test-report.md` at `b192d9d8eaa9-dirty` (not the base commit; it is the
last run recorded): unit 894 passed (frontend 487, messaging 134, shared 94), integration 531,
end-to-end 24, lint passed. Expected counts are "N or more".

## Global constraints

- **bash 3.2**: no associative arrays, no `${x,,}`, `mapfile` or `readarray`; empty arrays as
  `${a[@]+"${a[@]}"}` (`common.sh:20-22`). Lowercase with `tr 'A-Z' 'a-z'`.
- **`die` inside `$(…)` only ends the subshell.** Every call that can `die` and is captured is
  an assignment on its own line (`NAMESPACE="$(preview_namespace "$branch")"`), which `set -e`
  turns into an exit; never inside a `local x="$(…)"`, which swallows the status.
- Every `kubectl`/`helm` call names `KUBE_CONTEXT` (`kube`, `helm_ns`, or explicit flags), as
  `deploy.sh:30-33` does. `preview` runs only where `require_local_cluster` passes.
- `charts/collabhub-deps` keeps no credential default (D41); `values-k3d.yaml` is unchanged.
- No new public route: the Ingress allow-list (`templates/ingress.yaml:48-103`) is untouched
  (checked). No service Python changes.
- New environment variables `BRANCH`, `OBJECT_STORE_ORIGIN`, `PREVIEW_STATE_ROOT` go into
  `.env.example`'s deploy section (lines 75-94) and `common.sh`'s header.
- Everything else is as CLAUDE.md says.

## File map

| File | Change | Responsibility | Task |
|---|---|---|---|
| `src/services/testkit/tests/unit/test_preview_script.py` | create | tests of the preview functions and the `preview` command, through `/bin/bash` | 1 |
| `src/services/testkit/tests/unit/test_preview_charts.py` | create | `helm template` checks for R4, R5, decision 15 | 2 |
| `scripts/test.sh` | modify | every `charts/collabhub` render in `layer_lint` gains `--set-string origin=…`; `layer_unit` requires `helm` | 6 |
| `src/services/messaging/tests/unit/test_realtime_server.py` | modify | R5's characterisation tests | 3 |
| `src/frontend/src/App.test.tsx` | modify | R9 | 3 |
| `scripts/lib/common.sh` | modify | `normalize_origin`, `object_store_endpoint`, `OBJECT_STORE_ORIGIN`, header | 4 |
| `scripts/lib/preview.sh` | create | slug, branch, state dir, tunnel functions | 4 |
| `scripts/deploy.sh` | modify | `preview up/url/down`; `resolve_origin` via `normalize_origin`; `cmd_infra` and `cmd_app` pass the new values; header | 5 |
| `charts/collabhub/values.yaml` · `templates/messaging/configmap.yaml` · `templates/messaging/deployment.yaml` | modify | `origin`; Messaging's list; its checksum | 6 |
| `charts/collabhub/values-k3d.yaml` | modify | header comment (line 6 says the list stays unset) | 6 |
| `charts/collabhub-deps/values.yaml` · `templates/garage.yaml` | modify | `objectStoreOrigin`; the Ingress host and its comment | 6 |
| `src/frontend/src/App.tsx` | modify | the hint at lines 45-48 goes | 7 |
| `docs/design/07-open-decisions-register.md` · `docs/adr/<yymmdd>-preview-environments-on-quick-tunnels.md` · `docs/platform/versions.md` · `docs/design/04-asset-service.md` · `docs/design/00-platform-conventions.md` · `docs/design/02-messaging-service.md` · `src/services/messaging/README.md` · `README.md` · `.env.example` | modify · create · modify ×7 | the record | 8 |

Deliberately unchanged, each checked:
- `src/services/shared/shared/cors.py` — its docstring (lines 7-10, 72-79) describes the empty-list
  fallback, which is still what Auth, Asset and Compose use; R5 changes no service code.
- `charts/collabhub/templates/ingress.yaml`, `charts/collabhub-deps/templates/ingress.yaml` — Dex
  and the app stay on `APP_ORIGIN`'s host.
- `charts/collabhub-deps/templates/dex.yaml`, `app-secrets.yaml` — already derive everything from
  `origin`; Dex's pods roll on it (`dex.yaml:89`), Auth's on `AUTH_ISSUER` in its env, and the Garage
  bootstrap Job reruns post-upgrade and *replaces* the bucket's CORS rules
  (`garage-bootstrap.py:152`), so new tunnels need nothing more there.
- `docker-compose*.yml` — Compose sets its own `CORS_ALLOWED_ORIGINS`; no preview runs there.
- `tests/bdd/**` — no page object or step reads the hint (grep for `collabhub.dev` and
  `Locally this is Dex`: only `App.tsx:46`).
- No sibling branch is unmerged (`git branch --no-merged main` is empty).

## How this plan runs

| Phase | Tasks | Who | Ends with |
|---|---|---|---|
| **RED** | 1–3 | test-writer | failing bash, chart and Vitest tests, each for the reason given; the R5 unit tests passing as declared — **test-reviewer gate** |
| GREEN — scripts | 4–5 | code-writer | Task 1 passes |
| GREEN — charts | 6 | code-writer | Task 2 passes |
| GREEN — SPA | 7 | code-writer | Task 3's Vitest passes |
| Finish | 8–9 | code-writer | the record, then verification and the first real run |

Every stage runs the new tests the same way: `uv run pytest
src/services/testkit/tests/unit/test_preview_script.py` (or `…/test_preview_charts.py`), never
`scripts/test.sh` before Task 9. The code-writer may not edit either file. One RED phase: nothing
here is typed from a generated contract.

---

## Task 1: The preview functions and command (RED)

**Files:** `src/services/testkit/tests/unit/test_preview_script.py` (create)

**Interfaces** — produced for Tasks 4 and 5. In `scripts/lib/common.sh`:

```
normalize_origin <name> <value>        stdout: value minus one trailing "/".
    dies "<name> must start with http:// or https:// (got '<value>')"
    dies "<name> is an origin, with no path (got '<value>')"        ← the wording deploy.sh:52-58 has today
object_store_endpoint <app_origin> [<object_store_origin>]
    stdout: the second when non-empty, else origin_s3_endpoint <app_origin>
OBJECT_STORE_ORIGIN="${OBJECT_STORE_ORIGIN:-}"
```

In `scripts/lib/preview.sh` (sourced after `common.sh`):

```
preview_slug <branch>          stdout: lowercased; every byte outside [a-z0-9] → "-" (LC_ALL=C);
                               runs of "-" collapsed; leading/trailing "-" trimmed. May be empty.
preview_namespace <branch>     stdout: "preview-<slug>", cut per decision 19 with
                               "-<first 6 hex of sha1(branch)>" only when cut. Dies per decision 20.
                               sha1: `sha1sum` if on PATH, else `shasum -a 1`.
preview_branch [<repo dir>]    stdout: $BRANCH if non-empty; else `git symbolic-ref --quiet --short HEAD`
                               in <repo dir> (default $REPO_ROOT). Detached and no BRANCH:
                               dies "HEAD is detached — set BRANCH to name the preview".
preview_state_dir <namespace>  stdout: "${PREVIEW_STATE_ROOT:-<abs git common dir>/collabhub-previews}/<namespace>"
tunnel_url_from_log <log>      stdout: first match of https://[a-z0-9]+(-[a-z0-9]+)+\.trycloudflare\.com ;
                               status 1 when none. (The hyphen rule excludes api.trycloudflare.com.)
preview_wait_for_url <log> <seconds>   stdout: the URL once it appears; status 1 at the deadline.
tunnel_alive <pidfile>         status 0 iff the file holds a pid that `kill -0` accepts and whose
                               `ps -p <pid> -o command=` contains "cloudflared tunnel".
preview_tunnels_live <dir>     status 0 iff tunnel_alive for app.pid and s3.pid, and app.url, s3.url non-empty.
preview_start_tunnels <dir> [<seconds>=30]
                               mkdir -p; starts two `cloudflared tunnel --no-autoupdate --url $K3D_ORIGIN`;
                               writes {app,s3}.{pid,log}; waits (decision 17); writes {app,s3}.url.
                               Timeout: preview_stop_tunnels, then status 1 with
                               "no quick-tunnel URL from the <role> tunnel in <n>s — see <log>" on stderr.
preview_stop_tunnels <dir>     decision 18 for each of app.pid, s3.pid; removes the pid and url files,
                               keeps the logs; status 0 with nothing to stop.
```

And in `deploy.sh`: `preview up | url | down` (Task 5).

**The harness** — pytest, in the module, no new `testkit` helper. `REPO = Path(__file__).resolve().parents[5]`
(as `test_images.py` finds `docker-compose.yml`).
- **One runner**, `_run(argv, env, cwd=REPO, timeout=30) -> CompletedProcess` (`text=True`,
  `capture_output=True`), the module's only `subprocess.run`, carrying `# noqa: S603 — argv is
  the test's own: /bin/bash and literals`. Every program is named by absolute path (`/bin/bash`),
  so S607 never fires.
- **`_fn(snippet, env)`** runs `/bin/bash -c 'set -u; . scripts/lib/common.sh; [ ! -f
  scripts/lib/preview.sh ] || . scripts/lib/preview.sh; <snippet>'`. Sourcing `preview.sh` only if
  it exists means each test fails at red on its own `command not found`, and the tests of
  `common.sh`'s functions aren't hidden behind a load failure.
- **The env is built from nothing**, never `os.environ`: `PATH` (the fake's dir first where a test
  needs it, then `/usr/bin:/bin`, plus `dirname "$(command -v git)"` when that is elsewhere),
  `HOME=<tmp_path>`, `IMAGE_TAG=t` (so sourcing `common.sh` runs no `git`, `common.sh:52-57`),
  `PREVIEW_STATE_ROOT=<tmp_path>/state`, `FAKE_CLOUDFLARED_ARGS`, `FAKE_CLOUDFLARED_PIDS`, and what
  the test itself sets. So no developer's `APP_ORIGIN`, `NAMESPACE`, `KUBE_CONTEXT` or `BRANCH`
  leaks in.
- **Every fake is killed** by a fixture finalizer that reads `FAKE_CLOUDFLARED_PIDS` — each fake
  appends its own `$$` there, whoever started it — and sends `KILL` to each pid still alive,
  and to every `Popen` the test made itself (the reused-pid `sleep`s).
  Finalizers run when a test fails, so a red run leaves no loop behind.
- Assert on stdout, stderr and the return code separately.

**The fake `cloudflared`**, written by a fixture into `<tmp_path>/bin/cloudflared`, mode 0755:

```bash
#!/bin/bash
# Stand-in for cloudflared. No `exec`: the process must keep "cloudflared tunnel"
# in its command line, as the real one does, or tunnel_alive can't be tested.
echo $$ >>"$FAKE_CLOUDFLARED_PIDS"
printf '%s\n' "$*" >>"$FAKE_CLOUDFLARED_ARGS"
echo "2026-10-15T10:00:00Z INF Requesting new quick Tunnel on trycloudflare.com..." >&2
[ "${FAKE_TUNNEL_SILENT:-}" = 1 ] ||
    echo "2026-10-15T10:00:01Z INF |  https://fake-$$-tunnel.trycloudflare.com  |" >&2
while :; do sleep 1; done
```

**A running preview without the code under test**, for the `deploy.sh` tests: a fixture starts
two fakes itself (`subprocess.Popen(["/bin/bash", fake, "tunnel", "--no-autoupdate", "--url",
"http://localhost:8080"], …)`, same `# noqa`) and writes decision 9's files by hand into
`<state>/preview-t/`: `app.pid`/`s3.pid` (their pids), `app.url`/`s3.url`
(`https://quiet-fox-runs.trycloudflare.com`, `https://bold-owl-sings.trycloudflare.com`). So those
tests fail at red on `deploy.sh` alone, not on a missing `preview_start_tunnels`.

**A `PATH` with nothing on it** for the refusal test: a `<tmp_path>/minbin` holding symlinks to
`bash dirname git tr sed cat ps sleep mkdir rm` and to `shasum`/`sha1sum`, whichever exist — each
found with `shutil.which` — and nothing else. `PATH=<minbin>` alone, so no `cloudflared` on any
machine, and no `k3d`, `docker` or `helm` that the script could reach.

**Fixtures.** `B55 = "feature/" + 47×"a"` (namespace exactly 63). `B56 = "feature/" + 48×"a"`
(64 before the cut). `B56U = "feature_" + 48×"a"` (same slug as B56). `BDASH = "feature/" + 39×"b" +
"/" + 20×"c"` (the 56th character of the name is `-`). Hex suffixes are **literals** computed once
with `printf %s <branch> | shasum -a 1` and written into the test with that command in a comment —
never computed by the code under test.

| Test | Proves | Expected red |
|---|---|---|
| `test_a_branch_is_lowercased_and_separators_become_dashes` | `Feature/ISSUE_6` → `preview-feature-issue-6` | `preview_namespace: command not found` |
| `test_runs_of_dashes_collapse_and_the_ends_are_trimmed` | `--Feature//a__b--` → `preview-feature-a-b` | same |
| `test_bytes_outside_a_to_z_and_digits_become_dashes` | `fé/x` → `preview-f-x` (decision 21) | same |
| `test_main_is_allowed` | `main` → `preview-main` | same |
| `test_a_name_of_exactly_63_is_not_cut` | B55 → 63 characters, no suffix | same |
| `test_a_name_of_64_is_cut_and_suffixed_within_63` | B56 → `preview-feature-` + 40×`a` + `-<hex(B56)>`, length 63 | same |
| `test_the_suffix_hashes_the_branch_not_the_slug` | B56 and B56U: same first 56 characters, different namespaces, each its own literal hex | same |
| `test_a_cut_ending_in_a_dash_is_trimmed_before_the_suffix` | BDASH → `preview-feature-` + 39×`b` + `-<hex(BDASH)>`, length 62, no `--` | same |
| `test_a_branch_with_no_letters_or_digits_is_refused` | `___` → status ≠ 0, stderr names decision 20's message | same |
| `test_branches_differing_only_in_separators_share_a_preview` | `feature/a_b` and `feature/a-b` → one namespace | same |
| `test_the_checked_out_branch_names_the_preview` | temp repo (`git init`, one commit with `-c user.name= -c user.email=`) on `topic/x`, `BRANCH` unset → `topic/x` | `preview_branch: command not found` |
| `test_BRANCH_overrides_the_checkout` | same repo, `BRANCH=other` → `other` | same |
| `test_a_detached_head_needs_BRANCH` | after `git checkout --detach`: unset → status ≠ 0 and the message; `BRANCH=x` → `x` in the same test | same |
| `test_the_object_store_endpoint_defaults_to_s3_of_the_app_origin` | `http://localhost:8080` → `http://s3.localhost:8080`; `https://a.example` → `https://s3.a.example` | `object_store_endpoint: command not found` |
| `test_an_object_store_origin_is_the_endpoint_as_given` | (`https://a.example`, `https://bold-owl-sings.trycloudflare.com`) → the second | same |
| `test_normalize_origin_trims_a_slash_and_refuses_a_path_or_scheme` | `https://b.example/` → `https://b.example`; `https://b.example/x` and `b.example` → status ≠ 0, message names `OBJECT_STORE_ORIGIN` | `normalize_origin: command not found` |
| `test_the_tunnel_url_is_read_past_a_decoy` | log with an error line holding `https://api.trycloudflare.com/tunnel` *before* the banner → the banner URL | `tunnel_url_from_log: command not found` |
| `test_a_log_with_no_tunnel_url_gives_nothing` | only the decoy and the "Requesting…" line → empty, status 1 | same |
| `test_waiting_returns_the_url_once_it_appears` | a background writer appends the banner after 1 s; `preview_wait_for_url log 5` → the URL. Then a fresh empty log with `… 1` → status 1 | `preview_wait_for_url: command not found` |
| `test_a_live_tunnel_is_a_running_cloudflared` | fake running → 0; a plain `sleep 30` pid in the file → 1 (reuse); a pid that has exited → 1; no file → 1 | `tunnel_alive: command not found` |
| `test_starting_gives_two_tunnels_to_the_k3d_load_balancer` | `preview_start_tunnels dir 10` → two live pids, two **different** URLs in `app.url`/`s3.url`; both recorded argument lines are `tunnel --no-autoupdate --url http://localhost:8080`; `preview_tunnels_live` → 0 | `preview_start_tunnels: command not found` |
| `test_one_dead_tunnel_makes_the_preview_not_live` | start, then kill only the s3 fake and wait for it → `preview_tunnels_live` 1 | same |
| `test_a_tunnel_with_no_url_stops_both_and_fails` | `FAKE_TUNNEL_SILENT=1`, `preview_start_tunnels dir 2` → status 1, stderr names `app` and its log; both fakes gone; no pid files | same |
| `test_stopping_stops_cloudflared_and_nothing_else` | start; kill the s3 fake and wait for it; write a running `sleep 60`'s pid into `s3.pid` (a reused pid) → `preview_stop_tunnels` stops the app fake, leaves the `sleep` running, removes the pid and url files; a second call succeeds | `preview_stop_tunnels: command not found` |
| `test_preview_up_refuses_without_cloudflared` | `PATH=<minbin> BRANCH=t /bin/bash scripts/deploy.sh preview up` → status 1, stderr contains `'cloudflared' is required`. Then, in the same test, the fake `cloudflared` linked into `minbin` → stderr now contains `'k3d' is required` and not `cloudflared` — the refusal was for `cloudflared`, and it comes first (t-3) | stderr is `unexpected argument 'up' (Helm arguments go after --)` (`deploy.sh:229-230`: the arguments are parsed before the command is looked at) |
| `test_preview_url_prints_both_origins` | the running-preview fixture; `BRANCH=t /bin/bash scripts/deploy.sh preview url` → status 0, stdout exactly `APP_ORIGIN=https://quiet-fox-runs.trycloudflare.com` and `OBJECT_STORE_ORIGIN=https://bold-owl-sings.trycloudflare.com` | stderr is `unexpected argument 'url' (Helm arguments go after --)` |
| `test_preview_url_says_when_the_tunnels_are_down` | no state → status 1, stderr contains `tunnels are not running`. Then the running-preview fixture with its s3 fake killed (and waited for) → status 1 and the same message: one dead tunnel is not live | same |
| `test_preview_refuses_what_it_owns` | with the running-preview fixture, so only the refusal can fail it: `APP_ORIGIN=http://x` → status 1, stderr names `APP_ORIGIN`; `DEPLOY_ENV=lab` → names `DEPLOY_ENV`; `NAMESPACE=other` → names `NAMESPACE`; `preview url -- --set x=y` → names Helm arguments. Each on its own, then none → status 0 (the positive) | same |

Every `deploy.sh` test asserts the message, not only the status: at red every one of them exits 1.

- [ ] Write the file. Run `uv run pytest src/services/testkit/tests/unit/test_preview_script.py`:
  every test fails as above, and `uv run ruff check` on it is clean.
- [ ] Leave uncommitted.

## Task 2: The chart checks (RED)

**Files:** `src/services/testkit/tests/unit/test_preview_charts.py` (create)

**Interfaces** — produced for Task 6:

```
charts/collabhub        origin: ""     required by templates/messaging/configmap.yaml when Messaging is enabled:
                        "origin is empty: set it to APP_ORIGIN, as scripts/deploy.sh does"
                        renders   CORS_ALLOWED_ORIGINS: "[\"<origin>\"]"      (list <origin> | toJson | quote)
charts/collabhub-deps   objectStoreOrigin: ""   non-empty → the Garage Ingress host is its host part;
                        empty → "s3.<origin host>" as today. GARAGE_CORS_ORIGINS stays `origin`.
```

The same runner shape as Task 1, its own copy in this module (`# noqa: S603` on its one
`subprocess.run`). A module fixture takes `helm` from `shutil.which("helm")` and **fails**
(`pytest.fail("helm is required for the chart tests — scripts/test.sh lint needs it too")`), never
skips, when it is missing (decision 26). `DEPS_CHART_FILES` comes from the real list:
`/bin/bash -c '. scripts/lib/common.sh; printf "%s\n" "${DEPS_CHART_FILES[@]}"'` with
`IMAGE_TAG=t`, never a copy. Renders use `--values …/values-k3d.yaml` (the deps one carries
throwaway credentials), `--api-versions keda.sh/v1alpha1`, and `--show-only` the one template.
Every `charts/collabhub` render sets `ingress.host=a.localhost` (or `lab.example`), because Helm
renders every template before `--show-only` picks one, so an empty host would fail it first.
`A=https://quiet-fox-runs.trycloudflare.com`, `B=https://bold-owl-sings.trycloudflare.com`.

| Test | Proves | Expected red |
|---|---|---|
| `test_messaging_cors_is_the_app_origin_on_k3d` | `origin=$A`, `ingress.host=a.localhost` → `messaging/configmap.yaml` has `CORS_ALLOWED_ORIGINS: "[\"$A\"]"` | `AssertionError`: no such line (Helm ignores the unknown `origin`) |
| `test_messaging_cors_is_the_app_origin_on_the_lab` | `values-lab.yaml`, `ingress.host=lab.example`, `origin=http://lab.example` → `"[\"http://lab.example\"]"` | same |
| `test_the_app_chart_refuses_no_origin` | `ingress.host=a.localhost`, no `origin` → the render exits non-zero **and** stderr contains `origin is empty`. Then the same render with `origin=$A` → exit 0 (the positive) | `AssertionError`: the render succeeds |
| `test_messaging_rolls_when_the_origin_changes` | `checksum/config` in `messaging/deployment.yaml`: equal for `$A` twice, different for `$A` and `$B` | the two checksums are equal |
| `test_garage_is_routed_on_the_object_store_origin` | deps, `origin=$A objectStoreOrigin=$B` → Ingress `host: "bold-owl-sings.trycloudflare.com"`, no `s3.quiet-fox-runs`, and `GARAGE_CORS_ORIGINS` is `"$A"` | the host is `s3.quiet-fox-runs…` |
| `test_garage_defaults_to_s3_of_the_app_host` | deps, `origin=http://localhost:8080`, no `objectStoreOrigin` → `host: "s3.localhost"` | **passes at red** — the guard that plain k3d and the lab don't move (R4) |

- [ ] Run `uv run pytest src/services/testkit/tests/unit/test_preview_charts.py`: five fail as
  above, one passes. Leave uncommitted.

## Task 3: Socket.IO behind TLS, and the sign-in page (RED)

**Files:** `src/services/messaging/tests/unit/test_realtime_server.py`,
`src/frontend/src/App.test.tsx` (both modify)

**Messaging** — through the file's own `_server(_settings(cors_allowed_origins=[…]))`, reading
`server.eio._cors_allowed_origins(environ)`. That private method is where engine.io decides: the
handshake refuses an `Origin` not in what it returns (`engineio/async_server.py:226-232`); a list
is returned as given, a callable is asked with `environ["HTTP_ORIGIN"]`
(`engineio/base_server.py:284-317`, the workspace's installed engine.io). The environ is
`{"HTTP_HOST": "quiet-fox-runs.trycloudflare.com", "wsgi.url_scheme": "http",
"HTTP_X_FORWARDED_PROTO": "ws"}` — what Traefik hands on behind the tunnel.

| Test | Proves | Expected red |
|---|---|---|
| `test_an_explicit_origin_is_matched_as_given_behind_a_tls_tunnel` | list `["https://quiet-fox-runs…"]` → `https://…` allowed **and** `http://…` not | **passes at red** (decision 25) |
| `test_without_a_list_a_tunnel_origin_is_refused_behind_traefik` | `[]`, with `HTTP_ORIGIN` set in the environ: `https://…` refused, and `http://…` allowed in the same test — the predicate works, it rebuilds the wrong scheme. This is why R5 exists | **passes at red** |

Each gets the house one-line docstring saying what breaks if it goes.

**The SPA** — one test in `App.test.tsx`'s `describe('App routes')`:

| Test | Proves | Expected red |
|---|---|---|
| `it('shows no email address and no password on the sign-in page')` | `aFirstVisit()`, route `/sign-in`; await the `Sign in` button and `Sign in with your CollabHub account.` (the page rendered); then the rendered container's `textContent` matches none of `/\S+@\S+\.\S+/`, `/password/i`, and case-sensitive `/\bcollabhub\b/` (the demo password; the heading's `CollabHub` doesn't match) | all three assertions fail on `App.tsx:45-48`; the first reports `ada@collabhub.dev` |

- [ ] Run `uv run pytest src/services/messaging/tests/unit/test_realtime_server.py` (2 new pass) and
  `npm --prefix src/frontend test -- src/App.test.tsx` (1 fails as above). Leave uncommitted.

---

## Task 4: The functions (GREEN)

**Files:** `scripts/lib/common.sh`, `scripts/lib/preview.sh` (create)

- [ ] `common.sh`: `normalize_origin`, `object_store_endpoint`, `OBJECT_STORE_ORIGIN`, and header
  lines for `OBJECT_STORE_ORIGIN`, `BRANCH`, `PREVIEW_STATE_ROOT`. Update `origin_s3_endpoint`'s
  comment: it is now the default, used when no object-store origin is given.
- [ ] `preview.sh` to Task 1's interfaces. The slug, the only part worth showing:

```bash
preview_slug() {
    printf '%s' "$1" | LC_ALL=C tr 'A-Z' 'a-z' | LC_ALL=C tr -c 'a-z0-9' '-' |
        tr -s '-' | sed 's/^-//; s/-$//'
}
# preview_namespace: name="preview-$slug"; if [ ${#name} -gt 63 ]: name="${name:0:56}",
# strip one trailing "-" (tr -s leaves at most one), append "-${hex:0:6}".
```

  The absolute git common dir: `(cd "$REPO_ROOT" && cd "$(git rev-parse --git-common-dir)" && pwd)`
  — `git rev-parse --git-common-dir` prints `.git`, relative, in a primary checkout.
- [ ] Run `uv run pytest src/services/testkit/tests/unit/test_preview_script.py`: all but the four
  `deploy.sh` tests pass (under `/bin/bash`, so 3.2 on macOS). Leave uncommitted.

## Task 5: `deploy.sh preview` (GREEN)

**Files:** `scripts/deploy.sh`

- [ ] Source `lib/preview.sh` after `common.sh`.
- [ ] `resolve_origin`: keep the k3d default, then `APP_ORIGIN="$(normalize_origin APP_ORIGIN
  "$APP_ORIGIN")"`, and the same for `OBJECT_STORE_ORIGIN` when non-empty.
- [ ] `cmd_infra`: `--set-string "objectStoreOrigin=$OBJECT_STORE_ORIGIN"` (empty is the default).
  `cmd_app`: `--set-string "origin=$APP_ORIGIN"`, and `OBJECT_STORE_PUBLIC_ENDPOINT=$(object_store_endpoint
  "$APP_ORIGIN" "$OBJECT_STORE_ORIGIN")` in place of line 166.
- [ ] Argument parsing: `preview` takes a subcommand `up|url|down` before any `--`; anything else
  dies `expected 'preview up', 'preview url' or 'preview down'`. Helm arguments are refused for
  `preview` (decision 22). The generic `resolve_origin` call (line 272) is skipped for it.
- [ ] `preview_guard` (all three): `require_local_cluster preview`; decision 22's refusals, each
  naming the variable. Then `branch="$(preview_branch)"`, `NAMESPACE="$(preview_namespace
  "$branch")"`, `state="$(preview_state_dir "$NAMESPACE")"` — each its own line (Global constraints).
- [ ] `cmd_preview_up`, in this order — the issue's *Timing* with *Corrections* 1:

  | Step | Does | On failure |
  |---|---|---|
  | t-3 | `require_cmd cloudflared`, then `require_cmd k3d docker helm kubectl curl` | nothing started |
  | t-2 | `cmd_cluster` | nothing else started |
  | t-1 | `IMAGE_TAG="$IMAGE_TAG" "$REPO_ROOT/scripts/build.sh" --push` — the tag `common.sh` fixed at start, so build and deploy can't disagree | no tunnel started |
  | t0 | `preview_tunnels_live` → `log "reusing …"`; else `preview_stop_tunnels`, then `preview_start_tunnels` | both stopped, nothing deployed |
  | t1–t2 | `APP_ORIGIN=<app.url>`, `OBJECT_STORE_ORIGIN=<s3.url>`, `resolve_origin`, `cmd_infra`, `cmd_app` (which rolls a `-dirty` rebuild and ends in `check_origin`) | tunnels left running and recorded; the next `up` reuses them |
  | t4 | `log` the namespace, then the two lines of decision 23 on stdout | — |

  `check_origin` keeps its k3d credentials line (R9).
- [ ] `cmd_preview_url`: decision 23. `cmd_preview_down`: `preview_stop_tunnels`, then decision 24
  (`helm_ns status` / `helm_ns uninstall <release> --wait` for `collabhub` then `collabhub-deps`;
  `kubectl --context "$KUBE_CONTEXT" delete namespace "$NAMESPACE" --ignore-not-found --wait`),
  then `rm -rf "$state"`. It never names `keda` or calls `k3d cluster delete`.
- [ ] Header (`deploy.sh:1-22`): the three commands, `BRANCH`, the two-tunnel model, "no
  concurrent `up`". `--help` prints it.
- [ ] Run `uv run pytest src/services/testkit/tests/unit/test_preview_script.py`: all pass, and
  `bash -n` on each of `scripts/deploy.sh`, `scripts/lib/preview.sh`, `scripts/lib/common.sh`, one
  call per file. Leave uncommitted.

## Task 6: The charts (GREEN)

**Files:** see the file map, Task 6 rows.

```yaml
# charts/collabhub/templates/messaging/configmap.yaml, after the range over env.
# Always the configured origin, never empty: engine.io then compares the browser's
# Origin with it as given, rather than rebuilding one from X-Forwarded-Proto, which
# k3s's Traefik sets to http/ws even when the browser came in over https (R5).
  CORS_ALLOWED_ORIGINS: {{ list (required "origin is empty: set it to APP_ORIGIN, as scripts/deploy.sh does" $.Values.origin) | toJson | quote }}
```

```yaml
# charts/collabhub-deps/templates/garage.yaml — the Ingress host
{{- $s3Host := printf "s3.%s" $host }}
{{- with .Values.objectStoreOrigin }}
{{- $s3Host = regexReplaceAll "^[a-z]+://([^:/]+).*$" . "${1}" }}
{{- end }}
```

- [ ] `values.yaml` of each chart: the new value, with a comment saying `deploy.sh` sets it and it
  never goes into a values file (D40). Messaging's comment block says its list comes from `origin`.
- [ ] Messaging's checksum: `{{ list $component.env $.Values.origin | toJson | sha256sum }}`.
- [ ] `garage.yaml:118-125` comment: the host is `objectStoreOrigin`'s when given; CORS stays
  `origin` because the browser's origin is the app's, whichever host it uploads to.
- [ ] `values-k3d.yaml:4-10`: the header no longer says `CORS_ALLOWED_ORIGINS` stays unset.
- [ ] `scripts/test.sh` `layer_lint`: add `--set-string origin=<an origin>` to every
  `charts/collabhub` render and lint — lines 114-116, 117-119, 120-122, 130-134, 154-156, 189-191,
  192-194. At 154-156 it is what keeps that refusal about `ingress.host` now that `origin` is
  required too. `layer_unit`: `require_cmd npm helm` (decision 26).
- [ ] Run `uv run pytest src/services/testkit/tests/unit/test_preview_charts.py`: all pass. Then
  each changed `layer_lint` line once by hand (`helm lint …`/`helm template …` as written there),
  since `scripts/test.sh` waits for Task 9. Leave uncommitted.

## Task 7: The sign-in page (GREEN)

- [ ] Delete `App.tsx:45-48`, the hint paragraph. Nothing replaces it.
- [ ] Run `npm --prefix src/frontend test -- src/App.test.tsx` and `npm --prefix src/frontend run
  typecheck`. Leave uncommitted.

## Task 8: The record

- [ ] Register: a **D45** row, 🟢, *Cross-cutting (scripts, charts)*, and a "Settled" line under
  the D40–D42 block (`07-open-decisions-register.md:42-50`): preview environments, a k3d instance
  per branch on two quick tunnels; Messaging's Socket.IO list always set.
- [ ] ADR with the `adr-writer` skill: host-side quick tunnels over an in-cluster `cloudflared` or
  a named tunnel; a second tunnel for object storage rather than a path on the app's host (a
  presigned URL's host is signed, and the app's host routes to the SPA); the chart-set CORS list.
- [ ] `docs/platform/versions.md`: a `cloudflared` entry in the existing shape — `check_url:
  https://github.com/cloudflare/cloudflared/releases`, the version installed for Task 9, `notes:`
  host-side, local previews only, quick tunnels need no account.
- [ ] Doc 04 §4.1 (`04-asset-service.md:167-171`, which says k3d's endpoint is `s3.<host>` "set
  from APP_ORIGIN") and its §6 table row: `OBJECT_STORE_PUBLIC_ENDPOINT` is `OBJECT_STORE_ORIGIN`
  when that is set, else `s3.<APP_ORIGIN host>`.
- [ ] Conventions §5.6: Messaging's list is always `[APP_ORIGIN]` in the chart, and why; §6's CORS
  bullet: the empty-list predicate stays as the answer for a deployment that sets no list, but the
  chart always sets one, so it is no longer the deployed path.
- [ ] Doc 02 lines 632-637 (*Corrections* 3) and `messaging/README.md:153-156`: the same fact.
- [ ] `README.md`: a *Preview environments* section after *Deploying to Kubernetes* — the three
  commands; cloudflared on `PATH`; `BRANCH`; what a rerun does with live and dead tunnels (sign in
  again, data kept); roughly 1.5–2 GB per preview, most of it Elasticsearch; no concurrent `up`
  (both upgrade KEDA), nor `up` racing `down`; colliding slugs share a preview; the accepted
  sign-in risk; a `~/.cloudflared/config.yml` written for a named tunnel is not meant for these. A row in the
  command table (`README.md:279-287`).
- [ ] `.env.example` lines 75-94: `BRANCH`, `OBJECT_STORE_ORIGIN`, `PREVIEW_STATE_ROOT`, commented.
- [ ] Sweep: `grep -rn "s3\.<host>\|CORS_ALLOWED_ORIGINS stays\|behind the one ingress it is
  empty\|cloudflared" docs charts scripts src/services/*/README.md` for anything still saying the
  old thing; fix each, or note why not.

## Task 9: Verification

- [ ] `scripts/test.sh lint unit` — `unit` now runs both new pytest files, under `/bin/bash`
  (3.2 on macOS) — then `scripts/test.sh e2e`, the whole layer once: every journey drives the
  sign-in page Task 7 changes. No `integration`: no service's Python, SQL or stream changes. Counts
  at or above the baseline, unit up by the new tests.
- [ ] `python3 .claude/hooks/checks/conventions.py` with every changed file named literally (no
  `$(…)`), and `.claude/hooks/security.sh`.
- [ ] **The first real run is the human's**, not this stage's: the code-writer may not run
  `scripts/deploy.sh`, `cloudflared`, `curl` or `kubectl` (`deliver.sh:503-517`). Copy this list
  into the green report, under "still to do — the human", with the issue's *Acceptance* list
  (two browsers on another network) after it:
  1. **Before anything else, *What this assumes* 1:** `scripts/deploy.sh preview up` on this
     branch prints two URLs; `curl` the app URL's `/` and `/.well-known/jwks.json` (the Ingress
     matches on Host, so a 200 proves Host arrived unchanged), and the S3 URL (an S3 XML error,
     not Traefik's 404). A Traefik 404 on the app URL means Host was rewritten: stop there, as the
     issue says, and take it back to the issue — no workaround (*Test approach*).
  2. Record the `cloudflared` version and its banner format against `tunnel_url_from_log`.
  3. `preview up` again: same URLs. Kill one `cloudflared`; `preview up`: new URLs, data kept.
  4. `preview url`, then `preview down`; `scripts/deploy.sh status` for `collabhub` unaffected,
     `kubectl get ns` shows no `preview-…`, KEDA still running.
- [ ] Fill in *Found while building*. Leave the worktree dirty and report.

## Found while building

- **Departures:** none from the plan's code. `preview_guard` also refuses nothing beyond decision
  22. `preview down` skips cluster work when `k3d` is absent or has no cluster (decision 24),
  pinned by no test (the plan leaves it to the human's run).
- **Build to the tests:** function output carries no trailing newline for
  `normalize_origin`/`object_store_endpoint`, as the tests assert; `tunnel_url_from_log` prints
  one. The `app` role is checked first on a double timeout.
- **No bug found by a run:** every test passed first time against the build; nothing found.
- **Not run (by pipeline rule):** `scripts/deploy.sh preview up`, `cloudflared`, `curl`,
  `kubectl` — the first real run is the human's (green report).

## Not in this issue

As the issue lists: CI calling `preview`, named tunnels and stable hosts, Cloudflare Access,
per-preview passwords, watching or restarting tunnels, cleaning up deleted branches' previews, a
lock, any cluster but k3d.

## Self-review

- **Requirements:** R1 → Tasks 1, 4, 5 (slug tests, branch tests, `preview_guard`); R2 → 1, 4, 5
  (start/URL/refusal tests); R3 → 5 (t-3..t2), Task 9; R4 → 1, 2, 4, 5, 6 (endpoint and Garage host
  tests, default guard); R5 → 2, 3, 6; R6 → 1 (live/dead tests), 5 (t0), Task 9; R7 → 1, 5; R8 → 1
  (stop test), 5, Task 9; R9 → 3, 7, and `check_origin` untouched.
- ***Paths*:** first `up` → 5, 9; `up` with live tunnels → 1 (`preview_tunnels_live`), 5, 9; dead
  tunnels → 1 (one-dead test), 5, 9; failed after URLs → 5 (t1–t2 row), 9; second preview → 9 (a
  per-namespace signing key, `app-secrets.yaml:23-34`); plain `up` → 1 (endpoint default), 2 (Garage
  default), 6; the lab → 2 (lab CORS test); upload/inline/download and `wss://` → 9.
- ***Where the rules meet*:** new URL signs users out → 8 (README), 9; previews coexisting → 2
  (hosts), 8 (no concurrent `up`); one slug → 1 (`share a preview` test), 8; the CORS list
  everywhere → 2, and Garage CORS stays `origin` → 2.
- **Names:** `objectStoreOrigin` (deps) and `origin` (app) everywhere; `OBJECT_STORE_ORIGIN` the
  variable; `preview_*` and `tunnel_*` functions exactly as Task 1's interfaces.
- **Known ripple:** every `charts/collabhub` render in `layer_lint` needs `origin`, and `layer_unit`
  needs `helm` (Task 6 does both).
- **Pipeline fit:** both new test files are under `src/services/testkit/tests/unit/` — inside the
  test-writer's write scope, run with `uv run pytest`, and in the code-writer's `write_denied`.

## Review responses

Round 1 (`reviews/plan-reviewer-1.md`):

1. **Fixed.** The bash and chart tests are now pytest files under
   `src/services/testkit/tests/unit/` driving `/bin/bash` and `helm template` as subprocesses
   (decision 10, new decision 26, *Corrections* 4). The `scripts/test.sh` edits moved to Task 6
   (GREEN); every run step now says `uv run pytest …`; the unit layer runs them and requires `helm`.
2. **Fixed.** The four `deploy.sh` reds are now `unexpected argument 'up'|'url' (Helm arguments go
   after --)` (`deploy.sh:229-230`). `test_preview_url_prints_both_origins` no longer calls
   `preview_start_tunnels`: a fixture starts the fakes and writes the state files by hand, so its
   red is `deploy.sh`'s alone.
3. **Fixed.** *Test approach* now says plainly that nobody in the pipeline can check *What this
   assumes* and that the human's run is the first check, gives the written evidence for each
   assumption (`httpHostHeader`'s empty default; the banner; none for DNS), and says a rewritten
   Host is a stop with no workaround. Task 9 hands the run to the human, Host first.
4. **Fixed.** Every `charts/collabhub` render in Task 2 sets `ingress.host`; the refusal test also
   proves the same render passes with `origin` set.
5. **Fixed.** The refusal test runs with `PATH` set to a temp dir of symlinks to the few tools the
   script needs before t-3, and proves its positive by adding the fake and seeing `'k3d' is
   required` instead.
6. **Fixed.** Each fake appends its own `$$` to `FAKE_CLOUDFLARED_PIDS`; a fixture finalizer kills
   every pid there and every `Popen` the test made, pass or fail.
7. **Fixed.** Decision 22 now refuses a `NAMESPACE` other than `collabhub`, and says an explicit
   `NAMESPACE=collabhub` can't be told from the default (`common.sh:39`) and is ignored. The
   `deploy.sh` refusal test covers `NAMESPACE=other`.
8. **Fixed.** Task 8 names doc 04 §4.1 (`:167-171`) as well as the §6 row.

Left for later stages: the Task 9 command substitution is gone (files named literally); the DNS note is in
*Test approach*; the README (Task 8) now says `up` racing `down` is unsupported and mentions
`~/.cloudflared/config.yml`; the tests set `HOME` to a temp dir, so no developer's config reaches
them. R6/R8 composition beyond what the `preview url` tests reach stays with the human's run.
