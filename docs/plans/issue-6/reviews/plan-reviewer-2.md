# Plan review — issue 6, round 2: approved

All eight round-1 findings are fixed, and each fix checks out against the repo. The bash and
chart tests now sit where the test-writer may write them, the test pair may run them and the
code-writer may not edit them. The expected reds match what `deploy.sh` reports. The untestable
assumptions are handed to the human openly, with a stop and no workaround. No critical or major
finding is open. One new minor point, and two notes, go to later stages.

## Responses checked

| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1. RED tests outside the pipeline's reach — critical | Moved to `src/services/testkit/tests/unit/test_preview_{script,charts}.py`, driving `/bin/bash` and `helm template` as subprocesses. Decision 10, new decision 26, *Corrections* 4. `scripts/test.sh` edits moved to GREEN Task 6 | **resolved.** Checked `deliver.sh:541-546`: test-writer scope includes `src/services/testkit/`. `:441-447`: `uv run pytest *` is in `test_bash`. `:560-567`: `src/services/testkit/` is in the code-writer's `write_denied`. `testkit/plugin.py:132` disables sockets with `allow_unix_socket=True` and does not touch subprocesses; `test_plugin.py` and `test_journeys.py` already run subprocesses from this directory. Root `pyproject.toml:68` `testpaths` includes `src/services`, so `scripts/test.sh unit` (`-m unit`) collects them. `parents[5]` matches `test_images.py:17`. The departure from "`scripts/test.sh lint`" is recorded in *Corrections* 4 |
| 2. Wrong expected reds for `deploy.sh preview …` — major | Reds are now `unexpected argument 'up'\|'url' (Helm arguments go after --)`; the url test uses a hand-built running-preview fixture | **resolved.** `deploy.sh:223-231` parses the second positional before the command `case`, so every one of the four tests (including `preview url -- --set x=y`, where `$1` is still `url`) dies with that message at red |
| 3. "Check before building" assumptions only checked after the build — major | *Test approach* says plainly that the human's run is the first check. It gives the written evidence (`httpHostHeader`'s empty default, the banner) and says DNS has none. A rewritten Host is a stop with no `--http-host-header` workaround. Task 9 puts Host first | **resolved.** `deliver.sh:503-517` confirms the code-writer may not run `deploy.sh`, `cloudflared`, `curl` or `kubectl` |
| 4. Refusal render needs `ingress.host` — minor | Every app-chart render sets it; the refusal test proves its positive with `origin` set | resolved |
| 5. `PATH=/usr/bin:/bin` keeps a `.deb` cloudflared — minor | `minbin` of symlinks only; positive half adds the fake and expects `'k3d' is required` | **resolved.** Traced: `preview_guard` → `require_local_cluster` (pure, `deploy.sh:40-42`). `BRANCH=t` means no `git` call, the short name means no sha1, and `PREVIEW_STATE_ROOT` means no `git rev-parse`. `IMAGE_TAG=t` skips `common.sh:52-57`. So `require_cmd cloudflared` (`common.sh:82-87`, message `'<cmd>' is required and is not on PATH`) is the first thing that can fail |
| 6. Harness can't kill fakes it didn't start — minor | Each fake appends `$$` to `FAKE_CLOUDFLARED_PIDS`; finalizer kills them and every `Popen` | resolved. With no `exec` in the fake and `nohup` exec'ing it, `$!` and `$$` are one pid |
| 7. Decision 22 can't see an explicit `NAMESPACE=collabhub` — minor | Refuses only `NAMESPACE` ≠ `collabhub`, and says why (`common.sh:39`) | resolved |
| 8. Doc 04 stale text is §4.1 — minor | Task 8 names §4.1 `:167-171` and the §6 row | resolved |
| Left for later (round 1) | Task 9 names files literally; DNS note in *Test approach*; README covers `up`/`down` race and `~/.cloudflared/config.yml`; `HOME` is a temp dir in tests | taken up |

## What else the changes reach

- **Decision 26** (`layer_unit` requires `helm`): `layer_lint` already has `require_cmd npm helm git
  python3` (`test.sh:93`), so the unit layer needs no tool the everyday run doesn't already
  require. Failing rather than skipping when `helm` is missing is the right call for a gate.
- **Task 6's hand-run of the `layer_lint` lines**: `check_bash` (`deliver.sh:452-457`) gives
  the code-writer `helm lint *`, `helm template *` and `bash -n *`. Task 9's `scripts/test.sh
  lint unit` is a form the script accepts (`test.sh:5, 32-48`).
- **Chart reds**: the messaging `checksum/config` is `toYaml $component.env | sha256sum`
  (`messaging/deployment.yaml:20`), so at red it is the same for `$A` and `$B`, as stated. No
  values file sets `CORS_ALLOWED_ORIGINS` today (`values.yaml:191`, `values-k3d.yaml:6` only
  comment on it), so "no such line" is the red.
- **Slug literals**: B55 → 16+47 = 63; B56 → 56 + 7 = 63; BDASH puts `-` at position 56 → 55 + 7 =
  62. The fake's `fake-<pid>-tunnel` host matches the URL regex. The decoy `api.` doesn't.
- **`tunnel_alive` against the fakes**: both the fixture's `Popen(["/bin/bash", fake, "tunnel", …])`
  and a PATH-started fake show `…/cloudflared tunnel …` in `ps -o command=`, so the check sees
  them.
- **Vitest anchors**: `App.tsx:31` holds `Sign in with your CollabHub account.` and `:43` the
  `Sign in` button. Nothing else on the page says "password" or holds an `@`.

## Findings

### 1. The plan is over the length limit — minor
**Where:** whole plan · **Checked:** `wc -l` would count it; the Read showed 626 lines.
The exemplar's limit is 600. Most of the overrun is the Review responses section. This needs
no rework, so it goes under *Left for later stages*.

## Left for later stages

- **Test-writer — the temp repo's identity.** Task 1 says `-c user.name= -c user.email=` for the
  temp repo's commit. Taken literally, git refuses an empty ident (`empty ident name not
  allowed`), and with `HOME=<tmp_path>` no global config fills it in. Give both a value, and use
  `--allow-empty` or commit a file. Otherwise the branch tests fail on the fixture, not on
  `preview_branch`.
- **Test-writer — which role a double timeout names.** `test_a_tunnel_with_no_url_stops_both_and_fails`
  silences both fakes and expects `app` in stderr. The plan's interface takes that to mean the
  app role is checked first. The code-writer should build it that way rather than read the
  test as over-pinning.
- **Plan length** (finding 1).
- Carried from round 1, still open and for the human's run: DNS negative caching for a new
  trycloudflare host; R6 and R8 composition (the t0 reuse/restart branch, `down` with no
  cluster) tested only through their functions.

## Checked and sound

- Header and base commit `560114e` match `git log -1`. RED Tasks 1–3 come before GREEN, with
  the test-reviewer as the gate. *Found while building* is empty, and no task commits.
- No 🔴 is built on (D37 and D28 are named and left alone). The record task covers D45, the
  ADR, versions.md, doc 04 §4.1 and §6, conventions §5.6 and §6, doc 02, README and
  `.env.example`.
- Every function in Task 1's *Interfaces* has a named test, and the new `origin` and
  `objectStoreOrigin` values have chart tests.
- The guard tests prove their positives: Garage default against the object-store test,
  no-origin refusal against `origin` set, the refusal tests' "none → 0", and the Vitest
  page-rendered anchors.
