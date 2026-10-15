# Red tests — issue 6, round 1

TDD, no BDD scenario (as the plan says). 41 tests written across Tasks 1–3: 29 bash tests
and 5 chart tests that fail as planned, 3 characterisation tests that pass by design
(2 Messaging, 1 Garage default), and 1 Vitest test that fails as planned. One extra
bash test was added (state directory).

## Baseline
| File | Before | After |
|---|---|---|
| `messaging/tests/unit/test_realtime_server.py` | 3 passed | 3 passed + 2 new passing (by design) |
| `frontend/src/App.test.tsx` | 5 passed | 5 passed + 1 new failing |
| `testkit/tests/unit/test_preview_script.py`, `test_preview_charts.py` | new | 29 failed, 5 failed + 1 passed (by design) |

`npm ci` was run first (the worktree had no `node_modules`).

## Tests
Command: `uv run pytest <3 python files>` → 34 failed, 6 passed (3 existing + 3 by design).

| File · test | Layer | Task | Expected red (plan) | Observed red | Match |
|---|---|---|---|---|---|
| script · 10 slug/namespace tests (lowercase, dashes, collapse, non-ASCII, main, 63, 64, hash-of-branch, dash cut, no-letters, shared slug) | unit | 1 | `preview_namespace: command not found` | `missing: /bin/bash: preview_namespace: command not found` | yes |
| script · `test_the_checked_out_branch_names_the_preview`, `test_BRANCH_overrides_the_checkout`, `test_a_detached_head_needs_BRANCH` | unit | 1 | `preview_branch: command not found` | `missing: /bin/bash: preview_branch: command not found` | yes |
| script · `test_the_state_directory_is_under_the_root_or_the_git_common_dir` (added) | unit | 1 | — | `missing: …preview_state_dir: command not found` | added |
| script · 2 `object_store_endpoint` tests | unit | 1 | `object_store_endpoint: command not found` | same | yes |
| script · `test_normalize_origin_trims_a_slash_and_refuses_a_path_or_scheme` | unit | 1 | `normalize_origin: command not found` | same | yes |
| script · 2 `tunnel_url_from_log` tests | unit | 1 | `tunnel_url_from_log: command not found` | same | yes |
| script · `test_waiting_returns_the_url_once_it_appears` | unit | 1 | `preview_wait_for_url: command not found` | same | yes |
| script · `test_a_live_tunnel_is_a_running_cloudflared` | unit | 1 | `tunnel_alive: command not found` | same | yes |
| script · starting / one-dead / no-url / stopping (4) | unit | 1 | `preview_start_tunnels` / `preview_stop_tunnels` not found | `preview_start_tunnels: command not found` | yes |
| script · `test_preview_up_refuses_without_cloudflared` | unit | 1 | `unexpected argument 'up' (Helm arguments go after --)` | `assert "'cloudflared' is required" in "error: unexpected argument 'up' (Helm arguments go after --)"` | yes |
| script · `test_preview_url_prints_both_origins` | unit | 1 | `unexpected argument 'url'…` | `AssertionError: error: unexpected argument 'url' (Helm arguments go after --)` | yes |
| script · `test_preview_url_says_when_the_tunnels_are_down` | unit | 1 | same | `'tunnels are not running' in "error: unexpected argument 'url'…"` | yes |
| script · `test_preview_refuses_what_it_owns` | unit | 1 | same | `(['preview','url'], {'APP_ORIGIN': 'http://x'}, "error: unexpected argument 'url'…` | yes |
| charts · `…cors_is_the_app_origin_on_k3d` / `_on_the_lab` | unit | 2 | no such key | `assert None == '["https://quiet-fox-runs.trycloudflare.com"]'` / `'["http://lab.example"]'` | yes |
| charts · `test_the_app_chart_refuses_no_origin` | unit | 2 | render succeeds | `assert 0 != 0` | yes |
| charts · `test_messaging_rolls_when_the_origin_changes` | unit | 2 | checksums equal | `'9729db0a…' != '9729db0a…'` | yes |
| charts · `test_garage_is_routed_on_the_object_store_origin` | unit | 2 | host is `s3.quiet-fox-runs…` | `['s3.quiet-fox-runs.trycloudflare.com'] == ['bold-owl-sings.trycloudflare.com']` | yes |
| charts · `test_garage_defaults_to_s3_of_the_app_host` | unit | 2 | passes (by design) | passes | green by design |
| messaging · `test_an_explicit_origin_is_matched_as_given_behind_a_tls_tunnel`, `test_without_a_list_a_tunnel_origin_is_refused_behind_traefik` | unit | 3 | pass (decision 25) | pass | green by design |
| `App.test.tsx` · `shows no email address and no password on the sign-in page` | Vitest | 3 | first assertion reports `ada@collabhub.dev` | `expected 'CollabHubSign in with your CollabHub …Locally this is Dex — try ada@collabhub.dev with the password collabhub.' not to match /\S+@\S+\.\S+/` | yes |

## Types
`npm --prefix src/frontend run typecheck`: clean — no test imports a missing module (all are
bash or Helm subprocesses, or existing exports). `ruff check` on the three Python files: clean.

## BDD
None. No feature or step was added or changed.

## Departures from the plan
- **Hex suffixes are computed with `hashlib.sha1` in the test**, not pasted literals: `shasum`
  isn't runnable from this stage. It is independent of the bash under test (the shell uses
  `sha1sum`/`shasum`), so a wrong build still fails; `_sha6` documents the equivalent command.
- **Added** `test_the_state_directory_is_under_the_root_or_the_git_common_dir` — `preview_state_dir`
  is an interface in Task 1 with no test of its own in the table. It pins decision 9's override and
  its default under the absolute git common dir.
- **Chart tests parse the rendered YAML** (`CORS_ALLOWED_ORIGINS` data key equal to
  `json.dumps([origin])`) rather than match a text line; same assertion, independent of quoting.
- **`Sandbox.fn` fails with `missing: …` when bash exits 127**, so every function test's red names
  the missing function instead of an empty-stdout diff.
- The temp repo's identity is `user.name=Test`, `user.email=test@example.com` with `--allow-empty`
  (plan-reviewer round 2, *Left for later stages*).
- `test_preview_refuses_what_it_owns` also refuses `OBJECT_STORE_ORIGIN` (decision 22 lists it).

## Picked up from earlier reviews
- Temp repo identity: done as above.
- Double timeout names `app`: `test_a_tunnel_with_no_url_stops_both_and_fails` asserts `app` and
  `app.log` in stderr; the code-writer should check the app role first.

## For the code-writer
- `preview_start_tunnels` must redirect each cloudflared's stdout/stderr to its log (and not leave
  a pipe open): the test's subprocess captures output, and an inherited pipe would hang it.
- `preview_stop_tunnels` must TERM a pid only when `tunnel_alive` accepts it; the bystander test
  writes a live `sleep 60`'s pid into `s3.pid`. Logs are kept (`app.log` asserted).
- Output of `preview url` is exactly two lines on stdout; the "not running" case prints nothing
  to stdout and says `tunnels are not running` on stderr, exit 1.
- `preview_tunnels_live` is true only with both pid files running `cloudflared tunnel` **and**
  both url files present, as the dead-tunnel test relies on `s3.pid`'s process being gone.
- The refusal tests use `BRANCH=t`, `IMAGE_TAG=t`, `PREVIEW_STATE_ROOT`, so the refusal for
  `cloudflared` must precede any `git`, sha1 or cluster call (PATH holds only a handful of
  symlinks: bash dirname git tr sed cat ps sleep mkdir rm shasum sha1sum).
- Charts: parsed as YAML, so the Garage Ingress must have exactly one rule host.
- Nothing ran `scripts/test.sh`; `helm` 3 was found at `/opt/homebrew/bin/helm`.

## Right-reason notes (wrong build each guard fails)
- Garage default (green by design) fails a build that moves the host when `objectStoreOrigin` is empty.
- Messaging `_admits` pairs: a build that ignored the explicit list (predicate path) fails the first;
  the second proves the predicate really refuses https, so the first isn't passing for lack of a filter.
- No-origin refusal: its positive (render with `origin`) fails a build that always dies.
