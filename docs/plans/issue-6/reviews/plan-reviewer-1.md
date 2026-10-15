# Plan review — issue 6, round 1: changes_requested

The design is sound. It settles nearly every question I had before opening it, with recorded
decisions, and its claims check out against the repo. One problem stops it. Its bash and chart
RED tests live under `scripts/`, and the pipeline won't let the test-writer write there. No
test stage can run them, and nothing stops the code-writer editing them after the gate. Two
major findings come with it: expected reds the runtime won't produce, and the issue's
"check before building" assumptions, which only get checked after the build.

## Expectations

Written before the plan was opened, from the issue, `scripts/deploy.sh`, `scripts/lib/common.sh`,
`scripts/test.sh`, both charts' Ingress/Garage/Dex/secret templates and values,
`shared/cors.py` and its unit tests, `App.tsx` and `App.test.tsx`, conventions §5.6/§6, doc 04
§3, the register (D44 is the last; D45 free) and installed `engineio/base_server.py`.

**Decisions**
- R1: does the slug trim a trailing `-` left by the cut before `-<hash>` is appended? Is the
  hash over the raw branch name or the slug? What does a branch whose slug is empty (`___`)
  produce — refused, or `preview-` (an invalid namespace)? `sha1sum` (Linux) vs `shasum`
  (macOS) — which, and on bash 3.2?
- R1: "the current branch" — of which checkout: `REPO_ROOT`'s (the worktree the script lives
  in) or the caller's cwd?
- R2/R6: where is the state directory — per worktree (inside `REPO_ROOT`) or shared across
  worktrees keyed by slug? `feature/a_b` and `feature/a-b` (or `BRANCH=` from a second
  worktree) share one namespace: does a second worktree's `up`/`down` see the first's tunnels?
- R6: "still running" — how is a live tunnel detected? A bare `kill -0 <pid>` is true for a
  recycled PID after a reboot; is the process checked to be that cloudflared?
- R2: how are tunnels started so they outlive the script and the terminal (`nohup`; macOS has
  no `setsid`), and how is the URL read (which stream, what pattern, 30 s timeout)?
- R3: does the script export `IMAGE_TAG` to `build.sh --push` so build and deploy agree, and
  does the state directory stay out of `git status` so a preview's own files don't make the
  tag `-dirty`?
- R4: what chart value carries the object-store origin in each chart, and does the deps chart
  keep `GARAGE_CORS_ORIGINS` on `origin` (the "Where the rules meet" line)?
- R5: how does `charts/collabhub` learn `APP_ORIGIN` — a new value, or derived from something
  `deploy.sh` already sets? Is it `required` (and if so, which existing `helm lint`/`template`
  lines in `layer_lint` that pass no origin break), and in what wire form —
  `["https://x"]` JSON, which `pydantic-settings` needs for `list[str]`?
- R6: on a rerun with tunnels alive, does `up` still run `cmd_infra` and `cmd_app` (R3 says it
  deploys both), and does the KEDA upgrade still happen every time?
- R8: what does `down` do with the state directory, and in what order (tunnels, releases,
  namespace)? Does it `--wait` for namespace deletion?
- R9: delete the hint outright or replace it with credential-free text?
- CLI: `preview up|url|down` is two words; today's parser rejects a second positional. How do
  `-- helm args` and `--help` behave for `preview`?

**Conflicts**
- R3 "deploys … with those two origins" vs R6 "rerun … reuses tunnels": the same command
  must both start and reuse; the plan must say which wins on a half-dead pair (R6 is explicit).
- R5 "in every environment" vs the k3d values and chart comments that say
  `CORS_ALLOWED_ORIGINS` stays unset, and conventions §5.6 "empty is the default": the record
  must change those words, not only §5.6.
- *Paths*: "a failure at t1..t3 leaves both tunnels running" vs R2/`set -e`/an `EXIT` trap:
  a trap that cleans up would contradict it.
- Timing t-1: "a build failure stops here; no tunnel started" — but on a rerun with live
  tunnels, does a build failure leave them alone?

**Tests**
- Lint: CORS list rendered as `[origin]`; Garage Ingress host and `OBJECT_STORE_PUBLIC_ENDPOINT`
  from the object-store origin when set and `s3.<host>` when not — two origins whose hosts
  differ, so a build reading the wrong one fails. `OBJECT_STORE_PUBLIC_ENDPOINT` is set by
  `deploy.sh` (`origin_s3_endpoint`), not the chart — how can a `helm template` check reach
  it, unless the plan moves the derivation into the chart?
- Bash: each slug clause alone — case, substitution, collapse, trim, a name of exactly 63
  (no suffix) and 64 (cut + suffix, length 63), detached HEAD refused and `BRANCH=` accepted
  on a detached HEAD, `main` allowed. How is a detached HEAD produced without touching the
  worktree's own checkout?
- Pytest: the explicit-list case passes today (`socket_allowed_origins` returns the list and
  engine.io does exact membership, `base_server.py:312-316`). Does the plan say it is green at
  red, and does it drive engine.io's own check rather than only `== origins`?
- Vitest: a guard ("shows no email and no password") needs its positive — the sign-in page is
  rendered (the button). How is "no password" asserted without matching the "CollabHub"
  heading case-insensitively?
- What can't be tested (tunnels, `up`/`down`/`url`, R6) — declared under what no test covers,
  with the acceptance run as the proof.

**Risks**
- cloudflared forwarding `Host` unchanged — the issue says "stops here" if false; did the plan
  check the installed or documented behaviour, and a `~/.cloudflared/config.yml` interfering
  with a quick tunnel?
- Two writers of one preview: two worktrees on one slug; `up` racing `down`; the shared KEDA
  release (declared unsupported).
- R6 dead tunnel → new origins: does every origin-derived thing follow — Dex issuer and
  redirect URI (checksum restarts Dex), Garage bootstrap CORS (`UpdateBucket` replaces —
  fine), Garage Ingress host, Asset endpoint, Messaging CORS list, Auth issuer?
- `check_origin` and DNS for a brand-new trycloudflare host — negative caching longer than 60 s.
- Background processes left behind by a failed t0..30s (one URL found, the other not).

## Coverage

| Issue item or expectation | Plan | Outcome |
|---|---|---|
| R1 named from the branch: lowercase, substitutions, collapse, trim | T1 tests, T4 `preview_slug` | covered |
| R1 cut only past 63, `-<6 hex of sha1(branch)>` within 63 | dec 19 (assumed: 56 + trailing-dash trim), B55/B56/B56U/BDASH literals | settled |
| R1 `BRANCH=` overrides; detached HEAD refused; `main` allowed | T1 temp-repo tests, `preview_branch` | covered |
| R1 empty slug | dec 20 (assumed, refused) | settled |
| R2 two background tunnels to `http://localhost:8080`; refuse without `cloudflared` | dec 16, T1 start/refusal tests | covered (but see F1, F2) |
| R3 build and push at the usual tag, then deps and app, k3d context only, cluster created/started | T5 t-3…t2; Corrections 1 (cluster first, checked against `cluster.yaml:20-35`) | covered; real run only |
| R4 object-store origin → endpoint and Garage host; unset → `s3.<host>` | T1 `object_store_endpoint`, T2 Garage tests, Corrections 2 (`deploy.sh:166` is a literal — checked) | covered |
| R5 `[APP_ORIGIN]` in every environment, from the chart | dec 14/15, T2 k3d + lab + refusal + checksum | covered |
| R6 rerun: live → reuse; either dead → stop other, two new, redeploy | dec 12, T1 live/dead tests, T5 t0 | covered at function level; composition real run only |
| R7 `preview url` | dec 23 (assumed), T1 tests | covered |
| R8 `down`: tunnels, both releases, namespace, nothing else; idempotent | dec 24, T5, T1 stop test | covered for tunnels; cluster half real run only |
| R9 no credentials on sign-in; console line kept | T3 Vitest with positive half; `check_origin` untouched | covered |
| Decided 1–7 | decision rows 1–8 | covered |
| Tests: lint/helm, bash, pytest, Vitest, no BDD | T1–T3 | misread on placement — F1 |
| Record: D45, ADR, versions.md, doc 04, §5.6, README, header | T8, T5 header | covered (doc 04 section — F8) |
| Not in this issue | restated | covered |
| *What this assumes* — check before building | T9 step 1–2 only | missing — F3 |
| Exp: state dir location / shared across worktrees | dec 9 | settled |
| Exp: PID reuse | dec 12, 18 + test | settled |
| Exp: tunnels outlive the script | dec 16 `nohup` | settled |
| Exp: build/deploy tag agreement, state not dirtying the tree | T5 t-1, dec 9 (inside `.git`) | settled |
| Exp: chart learns the origin; `required` ripple in `layer_lint` | dec 11/14, T2 lists all seven renders (checked: 114, 117, 120, 130, 154, 189, 192) | settled |
| Exp: JSON list wire form | T2 interface `list … \| toJson \| quote` | settled |
| Exp: pytest green at red, through engine.io's own check | dec 25, T3 via `server.eio._cors_allowed_origins` | settled |
| Exp: Vitest "no password" vs "CollabHub" | T3 case-sensitive `\bcollabhub\b` | settled |
| Exp: failure t1..t3 leaves tunnels; no cleanup trap | T5 table | settled |
| Exp: R6 origin change reaches Dex, Garage CORS, Asset, Messaging | file map "deliberately unchanged" (checked `dex.yaml:89`, `garage-bootstrap.py:152`) + dec 15 | settled |
| Exp: DNS negative caching for a new host | not addressed beyond the issue's assumption | left for later |

## Findings

### 1. The bash and chart RED tests can't be written, run or protected by the pipeline — critical
**Where:** Test approach table; File map rows 1–3; Tasks 1, 2, 4, 5, 9 · **Checked:**
`scripts/deliver.sh:441-456` (`test_bash`, `check_bash`), `:535-569` (`write_scope`, `write_denied`).
The test-writer's write scope is `src/frontend/src/**.test.ts(x)`, `src/frontend/src/test/`,
`src/services/*/tests/`, `src/services/testkit/`, `tests/bdd/` and its report. Tasks 1–2 create
`scripts/tests/preview.test.sh` and `scripts/tests/charts.test.sh`, and change `scripts/test.sh`.
None of those paths is in that scope, so the write check stops the run at the first RED task.

Even if the files existed, neither test stage may run `bash …` or `helm template`.
`test_bash` allows only `npm --prefix src/frontend test|typecheck|lint`, `uv run pytest` and
`uv sync`. So the test-reviewer couldn't gate them, and Tasks 4, 5 and 9 tell the code-writer
to run `bash scripts/tests/…`, which isn't in its allowed commands either.

`write_denied` for the code-writer covers `^tests/` but not `scripts/tests/`. It could
therefore edit the approved red tests freely, which undoes the gate.

To settle it, put the RED tests where the test-writer may write, the test pair may run them,
and the code-writer may not edit them. A pytest file under a `tests/unit/` directory that
calls bash and `helm template` through a subprocess meets all three; the plan picks the place.
The `scripts/test.sh` edits then move into a GREEN task. Wherever this departs from the
issue's "a small test `scripts/test.sh lint` runs", say so in *Corrections* or a decision row,
including which layer now runs the tests and whether `helm` is needed there.

### 2. Expected reds the runtime won't report — major
**Where:** Task 1 table, the four `deploy.sh` rows · **Checked:** `deploy.sh:223-240`.
Argument parsing runs before the command `case`. So `deploy.sh preview up` dies with
`unexpected argument 'up' (Helm arguments go after --)`, not `unknown command 'preview'`.
`test_preview_url_prints_both_origins` fails even earlier: it calls `preview_start_tunnels`
first, so its red is `preview_start_tunnels: command not found` and `deploy.sh` never runs.
The tests are still red, but the test-reviewer gates on the stated reason, so state the real
ones.

### 3. The issue's "check before building on it" assumptions are only checked after the build, and maybe never — major
**Where:** Test approach "What no test covers"; Task 9 step 1–2; Self-review · **Checked:** the
issue's *What this assumes* ("If it is false, the plan stops here"); `deliver.sh:503-517`. The
code-writer may not run `scripts/deploy.sh`, `cloudflared`, `curl` or `kubectl`.
The plan names no evidence that cloudflared forwards `Host` unchanged, or what form the banner
takes. Its only check is Task 9's "if … the stage may run deploy.sh". The stage may not, so in
practice the first check is the human's acceptance run, after everything is built. Say that
plainly. Give whatever written evidence exists, such as cloudflared's `httpHostHeader` default.
Say what follows if the human finds `Host` rewritten: a stop, not a workaround. The same goes
for the DNS assumption.

### 4. The "no origin" chart refusal needs `ingress.host` set — minor
**Where:** Task 2 `test_the_app_chart_refuses_no_origin`. With `--show-only`, Helm still renders
every template. If `ingress.host` is also empty, either `required` can fire first, and the
assertion on `origin is empty` fails a correct build. Set `ingress.host` in that test.

### 5. `test_preview_up_refuses_without_cloudflared` depends on where the machine keeps its tools — minor
**Where:** Task 1. On Linux, the cloudflared `.deb` installs to `/usr/bin` and docker sits there
too, so `PATH=/usr/bin:/bin` doesn't remove cloudflared. A `PATH` made of a temp dir holding
only the tools the script needs before t-3 (bash, git, ps, …) proves the refusal on any machine.

### 6. The harness can't kill fakes it didn't start — minor
**Where:** Task 1 harness. `preview_start_tunnels`, the code under test, starts the fakes, not
the harness. The `EXIT` trap has to find them through the `*.pid` files under the temp root,
or have the fake record `$$`. Otherwise a failing test leaves `while sleep` loops running.

### 7. Decision 22 can't tell a `NAMESPACE` that was set from the default — minor
`common.sh:39` assigns `NAMESPACE="${NAMESPACE:-collabhub}"` before `deploy.sh` can look, so
an explicit `NAMESPACE=collabhub` passes. Either read the raw value first, or drop that clause.

### 8. Doc 04's stale text is in §4.1, not §6 — minor
`04-asset-service.md:167-171` (§4.1) says k3d's endpoint is `s3.<host>` "set from APP_ORIGIN".
§6 holds only the table row. Task 8 names §6; its sweep grep would catch §4.1, but name it.

## Left for later stages
- **DNS for a new trycloudflare host** (unverified): a lookup made before the record exists may
  be cached as NXDOMAIN by macOS longer than `check_origin`'s 60 s. If the human's run sees it,
  the code pair should know it is the issue's fourth assumption failing, not a bug in routing.
- **`~/.cloudflared/config.yml`** may interfere with a quick tunnel (unverified). A line in the
  README, if the first run shows it.
- **R6 and R8 composition** (the t0 reuse/restart branch, `down` with no cluster) is tested
  only through its functions. A fake `k3d` on `PATH` would reach `down`'s no-cluster path
  cheaply, if the test pair has room.
- `up` racing `down` on one preview is no more supported than two `up`s; the README could say so.
- Task 9's `python3 … $(git diff --name-only HEAD)` uses a command substitution the code-writer's
  allowed commands may refuse. Pass the file names literally.

## Checked and sound
- Header and base commit `560114e` match `git log -1`; 519 lines; all exemplar sections are
  present, RED 1–3 come before GREEN, *Found while building* is empty, and no task commits.
- No 🔴 is built on; D37 and D28 are named and correctly left untouched.
- Corrections 1–3 hold: the registry is created by `cmd_cluster` (`cluster.yaml:20-35`);
  `OBJECT_STORE_PUBLIC_ENDPOINT` is a literal (`deploy.sh:166`); doc 02:632-637 is stale
  against `realtime.py:184`.
- engine.io (installed `base_server.py:284-317`) compares an explicit list as given and asks
  a callable with `HTTP_ORIGIN`. Decision 25's two tests are sound, and the second proves why R5 exists.
- The messaging ConfigMap/checksum (`configmap.yaml:16-18`, `deployment.yaml:20`) match
  decisions 14–15. `App.test.tsx` has `aFirstVisit` and `describe('App routes')`.
  `test_realtime_server.py` has `_settings`/`_server`.
- Sweep: no unmerged sibling branch (`git branch --no-merged main` is empty); the Ingress
  allow-list is untouched; no BDD page or step reads the hint; the new env vars go to `.env.example`.
- The Vitest guard has its positive half; the Garage default guard is paired with the
  object-store test; dec 12's `ps … command=` check is exercised by a reused-pid fixture.
