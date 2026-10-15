# Test review — issue 6, round 1: approved

34 of the 34 tests the plan expects to fail fail, each on the reason the plan gives; the 6
green-by-design tests pass and are declared. The tests are sound against the plan's wrong
builds. No critical or major finding is open; two minors go to the code pair.

## Expectations

Written from the issue, the plan, plan-reviewer-2 and the current `deploy.sh`/`common.sh`,
before the tests were opened.

**Slug / namespace (R1).** Today: no `preview_namespace` — each test fails `command not found`.
Vacuous: a single mixed case that doesn't separate lowercase, dash-collapse and trim; "63 not
cut" with a name never near the limit; a hash literal computed by the code under test. Clauses:
"only then suffixed" (63 exact → no suffix, 64 → suffix, both sides); hash of the *branch* not
the slug; "within the 63". Wrong builds: cut at 63 then suffix (70 chars); always suffix; hash
the slug. Detached HEAD needs both "refused without BRANCH" and "allowed with" in a real repo.

**Tunnels (R2, R6, R8).** Today: functions absent. Vacuous: `tunnel_alive` passing with
`kill -0` only (needs a reused-pid case); "stop kills only cloudflared" with no live bystander;
"two URLs" from one fake. Wrong builds: both tunnels to one URL; one dead of two read as live;
stop that signals a reused pid.

**Object store origin (R4).** `object_store_endpoint` absent. Needs default and override;
Garage Ingress host from `objectStoreOrigin`, default unchanged, Garage CORS still the app
origin. Wrong build: CORS derived from the object-store origin.

**Socket.IO (R5).** `CORS_ALLOWED_ORIGINS` rendered `["<origin>"]` in k3d and lab; required when
empty; checksum rolls Messaging. Characterisation tests need both halves. Wrong builds: list
only on k3d; empty list; checksum not including origin.

**`preview` command (R7, R3).** At red every `deploy.sh preview …` dies with the same message,
so each test must assert something behaviour-specific and carry a positive half.

**R9.** Must wait for the page before asserting absence; covers email and password.

**Existing tests.** Untouched.

## What ran

- `uv run pytest test_preview_script.py test_preview_charts.py test_realtime_server.py` →
  34 failed, 6 passed (the 6: 3 existing messaging tests, 2 new messaging characterisation
  tests, `test_garage_defaults_to_s3_of_the_app_host`). Script tests fail at
  `missing: /bin/bash: <fn>: command not found`, or for `deploy.sh` at
  `unexpected argument 'up'|'url' (Helm arguments go after --)`. Chart tests fail on the
  assertion on the new behaviour (host `s3.quiet-fox-runs…`, no CORS key, render succeeds).
  All match the report's *Observed red* and the plan's *Expected red*.
- `npm --prefix src/frontend test -- src/App.test.tsx` → 1 failed, 5 passed; the failure is
  `not.toMatch(/\S+@\S+\.\S+/)` against `…try ada@collabhub.dev with the password collabhub.`
- `git status` / `git diff`: only the three named test files changed or added (plus
  `docs/plans/issue-6/`); both diffs to existing files are purely additive.
- Ruff and the typecheck: **not re-run** (Bash was denied for that call); the report's "clean"
  is unverified by me. No test imports a missing TS module, so the typecheck risk is nil.
- **No sketch run.** `sketch.sh` copies only a frontend or a Python service; the code under
  test here is bash in `scripts/` and chart templates, which it can't copy. I instead traced
  each test against the correct and the wrong builds by reading (see *Checked and sound*) and
  confirmed by reading `garage.yaml:201-202` that `GARAGE_CORS_ORIGINS` is a `name/value`
  env entry, so `_find_env` can find it at green.

## Coverage

| Plan test or expectation | Test as written | Outcome |
|---|---|---|
| 10 slug/namespace tests, 3 branch tests | present, with literals via `hashlib` | present (hash departure accepted) |
| `object_store_endpoint` ×2, `normalize_origin` | present | present |
| URL read, decoy, wait | present, with both halves | present |
| `tunnel_alive`, start, one-dead, no-URL, stop | present | present |
| refusal without cloudflared (with positive), `url` ×2, refusals (with positive) | present | present |
| `preview_state_dir` | added | added, sound |
| Charts ×6 | present, YAML-parsed not text-matched | present |
| Messaging ×2, Vitest ×1 | present | present |
| R6 reuse/restart branch of `up`, R8 `down` | none | per plan: the human's run |

## Findings

### 1. Exact-stdout assertions on function output — minor
**Where:** `test_preview_script.py`, `test_the_object_store_endpoint_*`, `test_normalize_origin_*`
(`stdout == "…"`) · **Checked:** read.
The plan's interface says "stdout: value" without saying whether a newline follows. These pin
no trailing newline, so a correct `printf '%s\n'` fails. Existing `origin_s3_endpoint` prints
none, so the writer's guess is the likely build; but `.strip()`/`rstrip("\n")` as the other
tests do would not weaken them. The code-writer should build to the tests (no newline).

### 2. A missing URL file isn't what makes a preview "not live" — minor
**Where:** `test_one_dead_tunnel_makes_the_preview_not_live` · **Checked:** read.
Only a dead pid is flipped. A `preview_tunnels_live` that ignores the `.url` files passes every
test, and `preview url` would then print empty origins for a half-written state. The plan's
interface requires the URL files (decision 12). Not worth a round; for the code-writer.

## Left for later stages

- **Code-writer:** build `preview_tunnels_live` to require non-empty `app.url` and `s3.url`
  (finding 2) and print function output without a trailing newline (finding 1).
- **Code-writer:** from the report — redirect each `cloudflared`'s stdout and stderr to its log,
  or the `subprocess.run(capture_output=…)` waits on the inherited pipe and times out; check the
  `app` role first in the double-timeout message.
- **The human's run** (accepted by the plan, plan-reviewer-2 and the issue): R6's reuse/restart
  branch and R8's "nothing else" for `down` (KEDA, cluster, other namespaces) have no automated
  test. A `down` test with fake `k3d`/`helm`/`kubectl` recording their calls on `PATH` would
  cheaply pin "never names `keda`, never deletes the cluster"; the plan chose not to. Worth
  considering in a later issue.
- Chart: no test for an `objectStoreOrigin` carrying a port; the plan's regex drops it, which is
  right for an Ingress host. Unpinned, harmless.

## Checked and sound

- Red for the right reason: every failure is the behaviour missing; `sb.fn` turns exit 127 into
  `missing: …`, so no function test fails on an empty stdout, and `preview.sh` is sourced only
  if present so `common.sh` functions aren't hidden behind a load failure.
- Slug: 55/56 and BDASH literals check by hand (63; 56 → 63; 55+7 → 62). Wrong builds — suffix at
  63, cut to 55 or 57, no trailing-dash trim, hash of the slug, `echo` for the hash — each fail
  at least one test.
- `preview_branch`: runs in a real temp repo with an identity and `--allow-empty`; ignoring the
  directory argument would return `feature/issue-6`, not `topic/x`.
- `tunnel_alive` has the reused-pid case (`sleep 30`), the exited pid, and no file; the stop test
  has a live bystander in `s3.pid` and a second call.
- Start test: two distinct URLs (fake embeds `$$`), two pids, the argument line asserted twice.
- Refusal tests: the "without" half proves `cloudflared` is checked first; the "with fake" half
  moves to `'k3d' is required`. Owned-overrides test has its positive at the end, and runs with a
  live preview so only the refusal can fail it.
- Chart tests: k3d and lab both asserted; the refusal has its positive; the checksum test differs
  in `origin` only; Garage CORS stays the app origin; default guard passes by design.
- Messaging characterisation tests pair https-admitted with http-refused, and the reverse for the
  empty list, so neither passes for lack of a filter.
- Vitest waits for the button and the subtitle before asserting absence, and covers email,
  "password" and the lowercase demo password separately.
- Fakes are killed in a finalizer from the pid file and the `Popen` list; env is built from
  nothing; no real network or cluster.
- Existing assertions: none changed or removed; no production code, config or docs written.
