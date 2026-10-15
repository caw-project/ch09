# Green — issue 6, round 1

`scripts/deploy.sh preview up|url|down`, `scripts/lib/preview.sh`, the chart `origin` and
`objectStoreOrigin` values and the sign-in page change are built, and the record is written.
Every test and check this stage can run is green. The real run against cloudflared and the
cluster is the human's.

## Baseline
Matches the red report: script tests 29 failed (all on `command not found` or the `unexpected
argument` message), chart tests 5 failed + 1 passed by design, Messaging 3 + 2 passing, `App.test.tsx`
1 failing of 6. I did not re-run the baseline separately before building; the first run after the
scripts were written moved script tests 0 → 29 passed.

## Built
| Task | Files | Tests now | Notes |
|---|---|---|---|
| 4 | `scripts/lib/common.sh`, `scripts/lib/preview.sh` | script tests 29/29 | `normalize_origin`, `object_store_endpoint`, preview functions |
| 5 | `scripts/deploy.sh` | same file | `preview` command, header, guard, `resolve_origin` via `normalize_origin` |
| 6 | charts, `values*.yaml`, `scripts/test.sh` | chart tests 6/6 | `origin` required; Messaging list and checksum; Garage host |
| 7 | `src/frontend/src/App.tsx` | `App.test.tsx` 6/6 | hint paragraph removed |
| 8 | register D45, ADR 261015, versions.md, docs 00/02/04, messaging README, README, `.env.example` | — | sweep grep found nothing stale |

## What ran
- `uv run pytest` over the three Python test files: 40 passed.
- `npm --prefix src/frontend test`: 50 files, 488 passed (baseline 487).
- `scripts/test.sh lint unit`: passed (lint incl. frontend lint/typecheck and every helm render;
  unit 932 passed).
- `scripts/test.sh e2e`: passed, 24 passed, 0 failed (whole layer).
- `.claude/hooks/security.sh`: clean. `conventions.py` on the changed script/TS files: no findings.
- Not run separately: `npm run build` (the e2e layer builds the frontend image).

## Beyond the tests
- `deploy.sh` header documents the three commands, `BRANCH`, the two-tunnel model, no concurrent
  `up` (README too). `.env.example` and `common.sh` header list the new variables.
- Messaging's checksum includes `origin` (`messaging/deployment.yaml`); `values-k3d.yaml` header
  and `garage.yaml` comment updated; `layer_unit` requires `helm`.
- `preview down` never calls `k3d cluster delete` or names `keda`; without a cluster it removes
  tunnels and state and succeeds.

## Departures from the plan
None of substance. `check_origin` keeps its credentials log line (R9).

## Picked up from earlier reviews
- No trailing newline on `object_store_endpoint`/`normalize_origin` output; `preview_tunnels_live`
  requires both URL files; each cloudflared's output goes to its log with stdin `/dev/null`; the
  `app` role is checked first on a double timeout.

## Left for the human
The first real run (`scripts/deploy.sh preview up`), in this order:
1. `preview up` prints two URLs; `curl` the app URL's `/` and `/.well-known/jwks.json` (200 proves
   Host arrived unchanged) and the S3 URL (an S3 XML error, not Traefik's 404). A Traefik 404 on the
   app URL means Host was rewritten: stop and take it back to the issue — no workaround.
2. Record the installed `cloudflared` version in `docs/platform/versions.md` (left blank) and
   check its banner format against `tunnel_url_from_log`.
3. `preview up` again: same URLs. Kill one cloudflared; `preview up`: new URLs, data kept.
4. `preview url`, then `preview down`; `scripts/deploy.sh status` for `collabhub` is unaffected,
   `kubectl get ns` shows no `preview-…`, KEDA still running.
5. The issue's *Acceptance* list: two browsers on another network, upload/download, `wss://`.
Also unproven: DNS for a new tunnel host within `check_origin`'s 60 s.
