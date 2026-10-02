# Green — issue 4, round 1 (after the test pair's fixes to send-back 3)

Every GREEN task is built (shared token source, `contracts.assets`, Asset, Messaging, Garage/Compose/charts, the SPA)
and the record is written (docs 02/04/06/07, ADR, README, vocabulary). The test pair has since fixed the six test-file
faults in `reviews/code-writer-sendback-3.md`, and **every layer is now green**, including the journey.

## Baseline
The red set matched the red report: the new Python tests errored on `asset.models`, `contracts.assets`,
`shared.service_tokens` and `messaging.assets` (missing) and on `allow_empty`; Vitest had 9 new files failing to load.
The typecheck was red for the same missing modules, as the plan says.

## Built
| Task | Files | Tests now | Notes |
|---|---|---|---|
| 5 | `contracts/assets.py`, `shared/service_tokens.py`, Asset: `settings, db, models, rules, object_store, migrations, migrate, alembic/*, routers/{assets,internal}, main, openapi`, `docker/asset/{Dockerfile,entrypoint.sh}`, `asset.json`, `types/asset.ts` | shared, Asset unit and integration all pass | |
| 6 | `0005_message_attachments`, `models`, `attachments`, `assets`, `messages`, `schemas`, `settings`, `main`, `realtime(_writes)`, three routers, download route, `messaging.json` | Messaging unit and integration all pass | |
| 7 | `garage-bootstrap.py` (CORS), compose ×2, `.env.example`, charts (ingress, asset migrate Job, NetworkPolicies, values, deps secrets/Garage Ingress/`messagingClientSecret`), `deploy.sh`, `common.sh`, `test.sh` | `scripts/test.sh lint` passes; `test_garage.py` 2/2 | |
| 8 | `config`, `lib/api/asset`, `getAttachmentUrl`, `xhrPut`, `rules`, `stores/attachments`, `uploads`, `useAttachmentUrl`, `AttachmentChips`, `AttachmentList`, `format`, `MessageComposer`, `useMessages`, `MessageItem/List`, `ChannelView`, `ChatLayout`, `stores/chat` | Vitest all pass | |
| 9 | docs 02/04/06/07, ADR `261002-…`, README, vocabulary §33, shared docstring, garage.toml, messaging README | — | |

## What ran
- `uv run pytest` over messaging, asset and shared unit and `contracts` → 251 passed; `test_schema.py` + `test_garage.py` → 17 passed.
- `npm --prefix src/frontend test` → all pass (36 files); `typecheck`, `lint` and `build` clean.
- `scripts/test.sh lint unit integration` → **passed**: unit 720 (including Vitest), integration **443 passed**, 0 failed.
  (The report write failed on that call with a transient `uv` interpreter error, so I ran `scripts/test.sh integration` again: 443 passed.)
- `scripts/test.sh e2e` (whole layer) → **passed, 21 of 21**, including `attachments.feature` (the journey's red-to-green).
  The stack runs under the per-worktree project `collabhub-test-caw-issue-4`, `down -v` first.
- `docs/test-report.md`: Lint ✅, Unit ✅ 720, Integration ✅ 443, End-to-end ✅ 21.
- `python3 .claude/hooks/checks/conventions.py` (all changes since HEAD) → no findings. `.claude/hooks/security.sh` could not be run this pass
  (Bash was refused); the last run showed only the old `testkit/report.py` XML finding, not from this work.

## Beyond the tests
- Module and doc-comments for every new module and its decisions (claim-then-insert, two S3 clients, why no SVG setting).
- Asset readiness omits Garage (`asset/main.py` docstring); only `ASSET_MAX_UPLOAD_BYTES` is a setting (constant allow-list in `rules.py`).
- Messaging: body validated before the claim in both transports (`routers/messages.py`, `realtime_writes.py`), duplicate ids 400, tombstone `visible()`, the download route's own record check before calling Asset.
- SPA: batch all-or-none, failed chips count, restore ordering (`useMessages.restoreRefusedSend`), per-channel `sendErrors`, `variables.channelId` everywhere, 780 s staleness with focus/reconnect refetch off, synchronous `window.open`, cancel/reset (`ChatLayout` cleanup).
- Chart: Ingress `/api/v1/assets` only; Asset migrate Job; NetworkPolicies Messaging→Asset; `messagingClientSecret` required; `s3.<host>` Ingress; `OBJECT_STORE_PUBLIC_ENDPOINT` from `APP_ORIGIN`.
- `scripts/test.sh e2e`: per-worktree project name, `-p` on every call, `down -v --remove-orphans` before `up`, machine-wide lock kept (human's answer).

## Departures from the plan
All in the plan's *Found while building*: Garage CORS through the admin API (S3 element names, lower-case header); `ASSET_INTERNAL_URL` is an origin; Messaging settings default empty; `messages.create` returns `(Message, rows)`; `_caller: ServicePrincipal = Depends(require_service(...))`; `MessageItem` `attachments` slot and `composer-<id>` key; PDF via `location.assign`; k3d Garage key in `.env.example`; OpenAPI files written by the editor and `diff`-checked; e2e project name per worktree.

## Picked up from earlier reviews
`useSendMessage` sends `attachmentIds` only when non-empty ✓; composer names and classes per the red report ✓; `putFile` rejects from the abort listener ✓; focus/reconnect refetch off ✓; `up --wait` with the bootstrap works ✓; `URL_STALE_MS` kept a literal beside the TTL (commented) ✓; global `afterEach` reset in `setup.ts` is a test file, left (optional, nothing fails without it); `boto3` signing cited in *Found while building*.

## Left for the human
1. Remove the old shared volumes: `docker compose -p collabhub-test down -v`.
2. `CLAUDE.md` should say that the e2e stack's project name is per worktree, that every run starts from empty volumes, and that "five ports" is now seven (Asset 8014, Garage 3910). This stage may not edit it.
3. The first real run on Compose with Ada and Grace in two browsers (the six acceptance checks), and one upload and download on k3d through `s3.localhost:8080`. Look for: CORS on the PUT, the PDF download not navigating the page, the image click opening a tab.
4. Update any developer `.env` (README says what). The lab needs `--set-string messagingClientSecret=…`.
5. If issue 2 or 3 lands first, renumber `0005_message_attachments` (issue 3 already has a `0005`) and rerun.
6. Assumed decisions 15, 16, 18, 26–29, 33, 34 and 38 stand as the plan recorded them.
7. Stale docstrings in test files (`testkit/images.py`, `tests/bdd/conftest.py` "five ports", `test_messages.py:56`) are the test pair's, left alone.

## Review responses (round 2, after code-reviewer send-back 4)
1. **Fixed.** `MessageComposer.attach` now reads `session.snapshot()` for the token at each upload step, falling back to the prop ref only when the session is not signed in. The test pair's two new tests (renewal, and renewal after a channel switch) pass.
2. **Fixed.** README's e2e paragraph now says the project name is per worktree and every run starts with `down -v`; the later "`down` without `-v`" sentence is corrected to match.
3. **Left for a later stage** (minor, optional; Asset never sends an empty `errors`).

Reran after the change: Vitest 331 passed (36 files), typecheck, lint, build clean; `scripts/test.sh lint unit` passed; `scripts/test.sh e2e` (whole layer) passed. `docs/test-report.md` is from that last e2e run.

Earlier: Send-back 3 items 1–6 were answered by the test pair (red report, round 3) and now pass against the unchanged code.
