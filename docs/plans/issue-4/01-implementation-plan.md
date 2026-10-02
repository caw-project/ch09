# File attachments — implementation plan

> **For agentic workers:** this plan is executed by `scripts/deliver.sh`: the test-writer does every
> RED task, the code-writer every GREEN one. Three project rules override the superpowers skills.
> **Never commit** — every task ends with the worktree dirty. **Red first** — no production code
> until the test-reviewer has approved the failing tests. **Plans live in `docs/plans/`.**

**Goal:** Anyone who can post in a channel attaches up to ten images or PDFs to a message (pick, drop
or paste), uploaded straight to Garage; everyone who can see the message sees the images inline and
downloads the PDFs through short-lived URLs that Messaging mints.

**Architecture:** Asset gains its first table, an `ObjectStore` protocol over boto3, the public
`upload-url`/`confirm` handshake and two internal routes (`claim`, `download-url`). Messaging chooses
a message id, claims the assets from Asset with a cached service token, and only then inserts the
message and a `message_attachments` snapshot. Downloads always go through Messaging, so they follow
message visibility (new D43). The SPA keeps pending chips in the channel's draft (Zustand, client
state), uploads over XHR for progress, and fetches download URLs through TanStack Query with a
780 s staleness. A stdlib bootstrap gives Garage its layout, bucket, key and CORS in Compose, in the test
stack and on k3d.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async, Alembic, boto3 (new, Asset only), httpx,
python-socketio, pytest + testcontainers · React 19, TanStack Query v5, Zustand, Vitest + MSW ·
pytest-bdd + Playwright · Compose, Helm.

**Issue:** `docs/plans/issue-4/00-issue.md` — read it first. This plan argues from it and does not
repeat it.

**Worktree:** `../caw-issue-4`, branch `feature/issue-4`, from `main` at `950e66a`.

## Decisions

Decided by the issue:

| # | Question | Answer |
|---|---|---|
| 1 | Scope | R1–R16; *Not in this issue* stays out |
| 2 | D15 | Closed 🟢: no virus scan; the allow-list (no SVG) is the mitigation |
| 3 | Who authorizes downloads | Messaging (R10); Asset's public routes are `upload-url` and `confirm` only; Messaging's first service-token client, token reused until near expiry |
| 4 | Object key | `{workspaceId}/attachment/{assetId}`, no file name |
| 5 | What Messaging stores | A metadata snapshot from the claim's response, in a new table keyed by message and position; `messages.attachments uuid[]` dropped in the same migration |
| 6 | D13, D16 | Stay 🔴: one bucket `collabhub-assets`; nothing sweeps unsent `pending` assets or a deleted message's blobs |
| 7 | Siblings | Issues 2 and 3 may land first; the migration takes the next free number |

Taken in this plan — each needs the plan-reviewer's yes or no:

| # | Question | Answer | Why, and the alternative |
|---|---|---|---|
| 8 | Messaging table | `message_attachments (message_id, position)` PK, `asset_id` UNIQUE, no FK on `asset_id` | UNIQUE is a second guard behind the claim, and refuses a duplicate id in one send. Conventions §2: no FK across services. Alternative: a jsonb column on `messages`, which would add writes to the hottest table and lose the uniqueness |
| 9 | Where the claim lives in Asset | `assets.message_id` + `claimed_at`; claim locks the rows `FOR UPDATE` in id order, then updates | Two sends racing for one asset serialize, and id order means no deadlock. Alternative: a claims table, which is one more join for nothing |
| 10 | Scopes | `assets:claim` and `assets:download`, both granted to client `messaging` | One scope per internal route, as `assets:write-variants` does (D14) |
| 11 | Claim refusal wire shape | `409` Problem, `errors` keyed by asset id, each with one reason code: `not-found`, `not-yours`, `not-ready`, `already-attached`. Another workspace's asset is `not-found` | Every non-2xx is a Problem (Conventions §4.2). Messaging turns the first refusal in attach order into its own 409 `detail` (Interfaces). Alternative: a 200 carrying refusals, which would break the non-2xx rule |
| 12 | Send status codes | too many or duplicate ids → **400** `errors.attachmentIds`; refused claim → **409**; Asset unreachable or token unobtainable → **503** "Attachments can't be checked right now. Nothing was sent." | 400 is a malformed request, 409 is the assets' state, 503 is the dependency (R7) |
| 13 | Download route answers | `404 "No such channel."` when the message's channel isn't visible or there is no message (the existing `_visible_message` wording); `404 "No such attachment."` when the message is deleted, the asset isn't on it, or Asset answers 404; `503` when Asset is down | Keeps the existing probe-proof wording for channels (doc 02 §3.1.4) |
| 14 | Asset's public routes | `upload-url` → **201**; `confirm` → **200** `AssetResponse`; another user's or workspace's asset → **404 "No such asset."**; confirm on a non-`pending` asset returns it unchanged; Garage down → **503**, status unchanged | Confirm is idempotent, so a retried confirm is harmless |
| 15 | Confirm when the object is missing — **assumed** | `failed`, reason "The upload did not arrive." | The SPA only confirms after its PUT succeeded, so a missing object means a failed PUT. Changing to "leave pending, answer 409" later is one branch and one test |
| 16 | Content types setting — **assumed** | The allow-list is the code constant `ATTACHMENT_CONTENT_TYPES`; `ASSET_ALLOWED_CONTENT_TYPES` is removed from settings, `.env.example` (which lists SVG) and doc 04 §6 | D15's mitigation shouldn't be a value someone can widen in an env file. To restore it later, re-add the setting and intersect it with the constant |
| 17 | Size limit | `ASSET_MAX_UPLOAD_BYTES` (52 428 800 = 50 MiB) on the server; the SPA uses the same literal and says "50 MB" | The setting exists and the chart sets it |
| 18 | Garage readiness — **assumed** | Not an Asset readiness check | The same call as Elasticsearch in Messaging (doc 02 §6): a Garage blip makes `confirm` answer 503 rather than taking Asset out of rotation. Adding it later is one `http_check` |
| 19 | Asset's CORS and R1 | Asset gains `CORS_ALLOWED_ORIGINS` (Compose: the SPA's origin; chart: empty) and `REDIS_CACHE_URL` | `require_user` needs the denylist (Conventions §5.2), and the SPA calls Asset cross-origin in Compose |
| 20 | Messaging's client settings | `SERVICE_TOKEN_URL`, `ASSET_INTERNAL_URL` (both exist in `.env.example`), `MESSAGING_SERVICE_CLIENT_ID` (default `messaging`), `MESSAGING_SERVICE_CLIENT_SECRET` | Mirrors `WORKER_SERVICE_CLIENT_*` (`worker/settings.py:45-48`) |
| 21 | Token cache | `shared.ServiceTokenSource`: reused until 60 s before `expiresIn`, one fetch in flight at a time, dropped and refetched once on a 401 from Asset | Conventions §5.5 ("cache until shortly before expiry"); in `shared` because the Worker needs the same thing next |
| 22 | Public endpoint | `OBJECT_STORE_PUBLIC_ENDPOINT`: Compose `http://localhost:3900`, test stack `http://localhost:3910`, k3d `scheme://s3.<host>:<port>` from `APP_ORIGIN`, set by `scripts/deploy.sh` | R16. Two boto3 clients: the public one signs URLs, the internal one HEADs |
| 23 | Garage CORS | The bootstrap's new `ensure_cors()` (admin API `UpdateBucket`), origins from `GARAGE_CORS_ORIGINS`; methods `PUT GET HEAD`, header `Content-Type`, expose `ETag` | The issue's assumption. If v2.3.0's admin API refuses it, the fallback is a bootstrap-only key with `owner: true` calling `PutBucketCors` (stdlib SigV4), recorded in *Found while building*. Never the app key |
| 24 | The Compose bootstrap | A one-shot `garage-bootstrap` service running `charts/collabhub-deps/files/garage-bootstrap.py` in `python:3.12-slim`; `asset` waits for it to complete. The README's manual steps go | One script for Compose, the test stack, k3d and testkit |
| 25 | Messaging integration seam | Asset's internal API is a FastAPI stub built from `contracts.assets`, run with `testkit.apps.serve`; Messaging is pointed at it through `asset_internal_url` and `service_token_url`, over REST (`client_for`) and the socket (new `realtime_url_for`). The stub imports `contracts.assets` **inside the fixture**, so only the tests that need it error at red | Settings take extra keys silently (`extra="ignore"`, `messaging/settings.py:7`), so tests that need no stub build the real app today and fail on behaviour. `contracts` is production code and stays GREEN (Task 5); the alternative, writing it in RED, would put production code before the gate |
| 26 | Duplicate ids in one send — **assumed** | 400 "An attachment is listed twice." | The issue doesn't say. Silently de-duplicating would make the order ambiguous. One rule to change |
| 27 | Which pasted files are renamed — **assumed** | Only a file named `image.png` (the browser's generic name) becomes `Pasted image <yyyy-mm-dd hh.mm.ss>.png` | A JPEG renamed `.png`, or a Finder file losing its name, would be wrong. One predicate in `rules.ts` |
| 28 | A file breaking a per-file rule — **assumed** | It becomes a `failed` chip with the reason, counts towards 10 until removed, and is never uploaded | R5 says chips show the reason on failure; *Where the rules meet* counts failed chips |
| 29 | Opening an image — **assumed** | `window.open('', '_blank')` synchronously on click, then set its `location` once the fresh URL arrives (`opener = null`) | A `window.open` after an `await` loses user activation in Safari and gets blocked |
| 30 | Pending sends' attachments | The optimistic row carries the chips' metadata and fetches no URL until it is confirmed (a `temp:` id would 404) | The `temp:` prefix is already the pending marker (doc 06 §5.2) |
| 31 | Inline cap | `max-h-60 max-w-80` (240 × 320 px), `object-contain` | Left to the plan by the issue |
| 32 | The register | D15 🟢; new **D43** 🟢 once built; notes on D13, D16 and D34 | As *Record in this slice* |
| 33 | Restoring into a composer that isn't empty — **assumed** | Text: an empty draft takes the restored text; otherwise the draft becomes `restored + "\n" + current`. Chips: the restored chips go **before** the current ones and nothing is dropped, even past 10; uploads in flight carry on. Over 10, Send is disabled and the composer says "At most 10 files per message — remove 1." (the count over) | Nothing the user typed or attached is lost, and the refused send reads first because it was written first. Alternative: overwrite, which orphans in-flight uploads. Changing it is `restore()` and the draft merge, and two tests |
| 34 | When a channel's send error clears — **assumed** | When the next send **for that channel** starts (`onMutate` sets `sendErrors[variables.channelId]` to null); another channel's error is untouched | Today's `send.error` resets on the next `mutate`; this keeps that, per channel. Alternative: clear on typing, one line |
| 35 | Which channel a send's cache writes touch | Every write in `useSendMessage` — the `temp:` row in `onMutate`, its removal, the upsert, the restore, the error — keys on `variables.channelId`, never the hook's `channelId` argument | A pending mutation takes the observer's new options on re-render (`query-core/src/mutationObserver.ts:85-93`), so a closure over the hook's channel would clean up the wrong cache |
| 36 | A mounted image past 780 s | Keeps its URL. The URL query sets `staleTime: 780_000`, `refetchOnWindowFocus: false`, `refetchOnReconnect: false`, no interval; `refetchOnMount` stays default, so a **mount** that finds it stale refetches and shows no `src` until the new URL lands | The timeline's "t=780s nothing refetches; A stays on screen" and "remounts, stale → refetched before `<img>` loads". `main.tsx:15-28` leaves focus refetch on (TanStack's default) |
| 37 | Late writes to the chip store | `update(localId)` of a chip that is gone is a no-op. Each upload has an `AbortController`; `cancel(localId)` aborts it, and `uploads.ts` checks the signal before each of upload-url, PUT and confirm and passes it to each request, so nothing after a cancel is requested or written. ✕ on an uploading chip is `cancel` then `remove`; `reset()` follows `cancelAll()`. The asset stays `pending` in Asset (D16) | Three awaited steps run outside React (R15), and a ✕ or a workspace switch can land between any two |
| 38 | Whitespace-only body with attachments — **assumed** | Accepted and stored as `""` (`validate_body` already returns the stripped string, `messages.py:80-95`) | An empty and a blank body read the same. Alternative: refuse, one condition |

Nothing here builds on a 🔴 entry. **D16** (retention) is nearest: unsent `pending` assets and a deleted
message's blobs and `message_attachments` rows now accumulate, and nothing here deletes any of them.
**D13** (buckets) is untouched: one bucket, `collabhub-assets`, as today.

## Corrections to the issue

1. **"The test stack publishes neither Asset nor Garage."** The journey's browser reaches both, so
   `docker-compose.test.yml` publishes Asset on `BDD_ASSET_PORT` (8014) and Garage on
   `BDD_GARAGE_PORT` (3910), and builds the frontend with `VITE_ASSET_URL`. Task 7.
2. **Compose's `OBJECT_STORE_ACCESS_KEY=collabhub-local` can't be imported by Garage**, which takes
   only `GK` + 24 hex and a 64-hex secret (`charts/collabhub-deps/values-k3d.yaml:21-24`).
   `.env.example` takes the k3d values, and every developer's `.env` has to change too. The README
   says so. Task 7.
3. **Doc 04's key layout `{workspaceId}/{purpose}/{assetId}/{fileName}`** is superseded by *Decided
   already* 4. Task 9 writes this back.
4. **"50 MB" is 50 MiB** (decision 17).

## Test approach — recommendation to the test pair

**BDD outside-in, with one journey.** This is a big capability users see, spanning four components,
and only a real browser proves the whole path: the presigned PUT, Garage's CORS, signed hosts, the
claim, the broadcast and a download of the same bytes. Write the journey first. Everything else goes
down the pyramid.

| Behaviour | Layer | File |
|---|---|---|
| Ada attaches a PNG and a PDF and sends; Grace sees the image inline and the PDF as a chip; the download is Ada's bytes; Ada sees it once | **BDD** | `tests/bdd/features/attachments.feature` |
| Upload limits, confirm's size check, claim decision, object key, Content-Disposition | unit | `asset/tests/unit/test_rules.py` |
| Token reuse, expiry margin, single flight | unit | `shared/tests/unit/test_service_tokens.py` |
| Send validation, refusal wording, tombstone redaction, which asset is on a message; Asset client error mapping | unit | `messaging/tests/unit/test_attachments.py`, `test_asset_client.py` |
| Bootstrap: S3 served, CORS preflight | integration | `testkit/tests/integration/test_garage.py` |
| Presign, signed Content-Type, HEAD, Content-Disposition | integration | `asset/tests/integration/test_object_store.py` |
| Handshake, claim, download-url, tenancy, the claim race | integration | `asset/tests/integration/test_uploads.py`, `test_internal.py` |
| Send with attachments (REST and socket), refusals, 503, history, broadcast, tombstone, edit, download route | integration | `messaging/tests/integration/test_attachments.py` |
| Rules, paste, batch, chips, send gating, restore, per-channel errors, freshness, rendering, XHR | Vitest | Task 3 |

**What no test here covers:** Garage checking expiry when a request *starts* (a 15-minute PUT is not
worth a test); the k3d Ingress path to Garage (the first real run, Task 10); boto3's own signing
code, which no test isolates from Garage. boto3 isn't installed yet (`uv.lock` has no `boto3`), so
its source can't be cited here: `test_presigned_put_signs_the_content_type` is the check, and the
code-writer cites `botocore/signers.py` by line in *Found while building*.

**Baseline**, from `docs/test-report.md` at `d4be439`: unit 565 (asset 2, messaging 94, shared 87,
testkit 59, frontend 243), integration 381 (messaging 211, testkit 4), end-to-end 20.
Expected counts are "N or more", because issues 2 and 3 may land first.

## Global constraints

- Workspace from the token's `wsp` only (CH001); in internal calls it travels in the body, put there by
  Messaging from the claim. A resource the caller can't see is a 404 (CH004). Expect CH001 to fire
  on Asset's internal routes, whose `workspaceId` comes from the body by design: waive it on the line
  with that reason ("set by Messaging from the caller's `wsp`; a service token carries none").
- `require_user` on every public route here (none is in the fail-closed set of Conventions §5.2);
  `require_service(scope)` on the internal ones, never both (CH002/CH003).
- **Commit, then publish**, as every write in `routers/messages.py` does. **Claim, then insert**: the
  claim happens before the transaction that writes the message.
- Asset never streams a blob; Messaging never sees one.
- No `OFFSET` (CH005), no interpolated SQL (CH006), no exception text in `detail` (CH007), no file
  names in logs (CH008: a file name is user content), `deleted_at IS NULL` on every `assets` select
  (CH009).
- New env vars go in `.env.example`, settings, Compose and the charts together (Task 7).

## File map

Paths are relative to `src/services/` and `src/frontend/src/` where shortened.

| File | Change | Responsibility | Task |
|---|---|---|---|
| `asset/tests/unit/test_rules.py` | create | the Asset rules | 1 |
| `shared/tests/unit/test_service_tokens.py` | create | token cache | 1 |
| `messaging/tests/unit/test_attachments.py` · `test_asset_client.py` | create | Messaging rules, client mapping | 1 |
| `messaging/tests/unit/test_message_body.py` | modify | empty body allowed with attachments | 1 |
| `testkit/testkit/garage.py` · `images.py` · `plugin.py` | create · modify · modify | `garage_server` fixture, `GARAGE` pin, `CONTAINER_FIXTURES` | 2 |
| `testkit/tests/integration/test_garage.py` · `tests/unit/test_images.py` | create · modify | bootstrap and CORS; the pin matches Compose | 2 |
| `asset/tests/integration/conftest.py` · `test_object_store.py` · `test_uploads.py` · `test_internal.py` | create | Asset at its boundary | 2 |
| `messaging/tests/integration/conftest.py` | modify | `TABLES` + `message_attachments`; `build_settings` defaults for the new settings; `asset_stub` and `realtime_url_for` fixtures | 2 |
| `messaging/tests/integration/test_attachments.py` | create | the seam, both transports | 2 |
| `messaging/tests/integration/test_schema.py` · `test_messages.py:57` | modify | new table, column gone; `attachments == []` stays true | 2 |
| `test/api.ts` · `test/factories.ts` | modify | `asset` + `garage` stubs, non-JSON `record()`; `anAttachment()` | 3 |
| `features/attachments/*.test.ts(x)` · `lib/upload/xhrPut.test.ts` · `stores/attachments.test.ts` | create | the SPA's red | 3 |
| `features/channels/useSendMessage.restore.test.ts` · `ChatLayout.attachments.test.tsx` | create | R13 restore; R15 workspace switch — new files, because they import modules that don't exist yet | 3 |
| `features/channels/MessageComposer.test.tsx` · `useMessages.test.ts` · `MessageItem.test.tsx` · `ChannelView.test.tsx` | modify | composer; the new `mutate` variables and timeout wording (`useMessages.test.ts:134-214`); rendering; R14 | 3 |
| `tests/bdd/features/attachments.feature` · `steps/test_attachment_steps.py` · `pages/chat_page.py` | create · create · modify | the journey | 4 |
| `tests/bdd/conftest.py` | modify | probe Asset, truncate `assets` and `message_attachments` | 4 |
| `contracts/contracts/assets.py` | create | internal request/response models | 5 |
| `shared/shared/service_tokens.py` · `__init__.py` | create · modify | `ServiceTokenSource` | 5 |
| `asset/asset/{models,db,rules,object_store,openapi,migrate,migrations}.py` · `routers/{assets,internal}.py` · `main.py` · `settings.py` | create / modify | the service | 5 |
| `asset/alembic.ini` · `asset/asset/alembic/{env.py,versions/0001_assets.py}` · `asset/pyproject.toml` | create · modify | migrations; `boto3`, `alembic` | 5 |
| `docker/asset/Dockerfile` · `docker/asset/entrypoint.sh` | modify · create | migrate on start, as Messaging does | 5 |
| `asset/tests/unit/test_health.py` | modify | the two new required settings | 5 |
| `messaging/messaging/alembic/versions/0005_message_attachments.py` · `models.py` | create · modify | table, drop column | 6 |
| `messaging/messaging/{attachments,assets}.py` · `messages.py` · `schemas.py` · `settings.py` · `main.py` | create · modify | domain, client, DTO, wiring | 6 |
| `messaging/messaging/realtime.py` | modify | `RealtimeContext` (`:103-115`) gains `assets: AssetClient`; `main.py:152-157` passes it | 6 |
| `messaging/messaging/routers/{messages,reactions,search}.py` · `realtime_writes.py` | modify | `_as_message(…, attachments=)` at every caller | 6 |
| `messaging/tests/unit/test_indexing.py` · `tests/unit/conftest.py:39` | modify | the new required argument (6 call sites); the dropped column | 6 |
| `src/frontend/openapi/{messaging,asset}.json` · `types/{messaging,asset}.ts` · `package.json` | regenerate · modify | the contracts; `generate:api` does both | 5, 6 |
| `charts/collabhub-deps/files/garage-bootstrap.py` · `templates/{garage,app-secrets}.yaml` · `values*.yaml` | modify | CORS, Garage's Ingress, Messaging's secret, `messagingClientSecret` | 7 |
| `charts/collabhub/templates/ingress.yaml` · `asset/{migrate-job,networkpolicy}.yaml` · `messaging/networkpolicy.yaml` · `values.yaml` | modify / create | `/api/v1/assets`; migrations; Messaging → Asset | 7 |
| `docker-compose.yml` · `docker-compose.test.yml` · `.env.example` | modify | bootstrap, env, test ports | 7 |
| `scripts/deploy.sh` · `scripts/test.sh:88` | modify | public endpoint; lint's `--set-string messagingClientSecret` | 7 |
| `lib/config.ts` · `lib/api/{asset,messaging}.ts` · `lib/upload/xhrPut.ts` | modify / create | URLs and clients | 8 |
| `features/attachments/{rules,uploads,useAttachmentUrl}.ts` · `AttachmentChips.tsx` · `AttachmentList.tsx` · `stores/attachments.ts` | create | the feature | 8 |
| `features/channels/{MessageComposer,MessageItem,ChannelView,ChatLayout,useMessages}.tsx?` · `stores/chat.ts` | modify | wiring, R13–R15 | 8 |
| `docs/design/{02,04,06,07}-*.md` · `docs/adr/…-attachment-downloads-follow-message-visibility.md` · `README.md` · `docs/plans/ch06/gherkin/00-scenario-vocabulary.md` | modify · create | the record; the four new phrases | 9 |

Deliberately unchanged: `realtime.py`'s `publish_message_received` (it already sends the DTO);
`indexing.py` and `contracts/indexing.py` (no file names in search: *Not in this issue*); Auth's code
(only its `AUTH_SERVICE_CLIENTS` value changes); `docker/frontend/Dockerfile` (`VITE_ASSET_URL` is
already a build arg, `:22`); `docker/postgres/init.sql` (`collabhub_asset` exists).

## How this plan runs

| Phase | Tasks | Who | Ends with |
|---|---|---|---|
| **RED** | 1–4 | test-writer | failing Python unit and integration, Vitest and BDD tests, each failing for the reason given — **test-reviewer gate** |
| GREEN — backend | 5–6 | code-writer | Tasks 1–2 pass; both OpenAPI documents regenerated |
| GREEN — infra | 7 | code-writer | Compose and the test stack come up with Garage bootstrapped; `helm lint` passes |
| GREEN — SPA | 8 | code-writer | Task 3 passes; `tsc` clean |
| Finish | 9–10 | code-writer | the record, then verification and the first real run |

Task 3's stubs are typed from the generated schemas, which only exist after Tasks 5–6, so until then
`tsc` is red for the same reason the tests are. Its expected reds are module-not-found, not type
errors: Vitest strips types.

---

## Task 1: The rules (RED)

**Interfaces** — `asset.rules` (pure; no session, no boto3):
- `ATTACHMENT_CONTENT_TYPES = ("image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf")`, `MAX_FILE_NAME_CHARS = 255`
- `class UploadRuleError(Exception)` with `.field` (`fileName|contentType|sizeBytes|purpose`) and `.message`
- `check_upload(*, file_name, content_type, size_bytes, purpose, max_bytes) -> None`. Messages: "Only images (PNG, JPEG, GIF, WebP) and PDFs can be attached." · "Files must be 50 MB or smaller." · "This file is empty." · "File names must be 1 to 255 characters." · "Only attachments can be uploaded."
- `object_key(workspace_id, asset_id) -> str` → `f"{workspace_id}/attachment/{asset_id}"`
- `confirm_outcome(*, declared_bytes, stored_bytes: int | None, max_bytes) -> tuple[Literal["ready","failed"], str | None]`: `None` → failed "The upload did not arrive."; ≠ declared → failed "The file stored is not the size it was declared to be."; > max → failed "Files must be 50 MB or smaller."
- `claim_refusal(asset: Asset | None, *, workspace_id, user_id, message_id) -> ClaimRefusal | None`, checked in this order: missing or other workspace → `NOT_FOUND`, owner ≠ user → `NOT_YOURS`, status ≠ ready → `NOT_READY`, claimed by another message → `ALREADY_ATTACHED`; claimed by *this* message → `None`
- `content_disposition(content_type, file_name) -> str`: PDF → `attachment; filename*=UTF-8''<pct-encoded>`, images → `inline; …`

`shared.service_tokens`: `ServiceTokenSource(*, token_url, client_id, client_secret, http: httpx.AsyncClient, margin_seconds=60.0, clock=time.monotonic)`, `async token() -> str`, `invalidate() -> None`, `class ServiceTokenUnavailableError(Exception)`. Posts `{grantType: "client_credentials", clientId, clientSecret}` (`auth/schemas.py:82-85`) and reads `accessToken`, `expiresIn` (`:70-73`).

`messaging.attachments` (pure half): `TooManyAttachmentsError`, `DuplicateAttachmentError`,
`check_attachment_ids(ids, *, max_attachments) -> None`, `refusal_detail(refusals: dict[UUID, ClaimRefusal], order: list[UUID]) -> str`,
`visible(message: Message, attachments: list[T]) -> list[T]` (`[]` when deleted),
`find_on(message, attachments, asset_id) -> T | None`. `messages.validate_body(raw, *, max_chars, allow_empty=False)`.
`messaging.assets`: `AssetClient(*, base_url, tokens: ServiceTokenSource, http)`, `claim(...) -> list[AttachmentMeta]`,
`download_url(...) -> DownloadUrlResponse`; `AssetUnavailableError`, `ClaimRefusedError(.refusals)`, `AttachmentNotFoundError`.

| Test (file) | Proves | Expected red |
|---|---|---|
| `test_rules.py`: `test_each_allowed_type_passes` · `test_svg_is_refused` · `test_a_type_with_parameters_is_refused` (`image/png; x=1`) | the allow-list, exact match | `ModuleNotFoundError: No module named 'asset.rules'` |
| `test_the_limit_itself_passes_and_one_more_byte_fails` · `test_zero_bytes_is_refused` · `test_one_byte_passes` | both sides of each size bound | same |
| `test_255_characters_pass_and_256_fail` · `test_an_empty_name_fails` · `test_a_purpose_other_than_attachment_fails` | name and purpose, each alone with the others valid | same |
| `test_the_object_key_has_no_file_name` | Decided 4 | same |
| `test_confirm_ready_when_sizes_match` · `_failed_when_missing` · `_failed_when_one_byte_short` · `_failed_when_one_byte_over` · `_failed_over_the_limit_even_when_declared` | confirm, each reason | same |
| `test_claim_refusals_in_order` (parametrized: one fixture per row, each failing exactly one check) · `test_claimed_by_this_message_is_no_refusal` · `test_another_workspace_reads_as_not_found` | the claim decision, idempotency | same |
| `test_pdf_downloads_as_attachment` · `test_images_open_inline` · `test_a_non_ascii_name_is_percent_encoded` | Content-Disposition | same |
| `test_service_tokens.py`: `test_one_fetch_serves_until_the_margin` (clock at `expiresIn-61` → cached, `-59` → refetched) · `test_two_concurrent_callers_fetch_once` (fetch held by an `asyncio.Event`) · `test_invalidate_forces_a_fetch` · `test_a_refused_grant_raises_unavailable` · `test_auth_unreachable_raises_unavailable` | Decision 21; httpx `MockTransport` (no socket) | `ModuleNotFoundError: shared.service_tokens` |
| `test_attachments.py`: `test_ten_ids_pass_eleven_fail` · `test_a_duplicate_id_fails` · `test_refusal_detail_names_the_first_in_attach_order` (two refusals, the second-listed first in the dict) · `test_a_tombstone_shows_no_attachments` (plus the live row showing them) · `test_find_on_misses_another_messages_asset` · `test_find_on_misses_on_a_tombstone` | Messaging's rules | `ModuleNotFoundError: messaging.attachments` |
| `test_message_body.py` (add): `test_an_empty_body_passes_when_allowed` · `test_whitespace_passes_as_empty_when_allowed` (returns `""`, decision 38) · `test_whitespace_still_fails_when_not_allowed` | R6 | `TypeError: … unexpected keyword argument 'allow_empty'` |
| `test_asset_client.py`: `test_a_409_becomes_claim_refused_with_reasons` · `test_a_5xx_becomes_unavailable` · `test_a_connect_error_becomes_unavailable` · `test_a_401_refetches_the_token_once_then_succeeds` · `test_a_second_401_is_unavailable` · `test_download_404_is_not_found` | the client's mapping; `MockTransport` | `ModuleNotFoundError: messaging.assets` |

Each test gets the house one-line docstring saying what breaks without the rule. Leave uncommitted.

## Task 2: Garage, Asset and Messaging at their boundaries (RED)

**Interfaces** — the wire contract Tasks 3, 5, 6 and 8 depend on:

```
Asset, public (require_user):
POST /api/v1/assets/upload-url            → 201 UploadUrlResponse
  UploadUrlRequest  = { fileName, contentType, sizeBytes, purpose: "attachment" }
  UploadUrlResponse = { assetId, uploadUrl, method: "PUT", headers: { "Content-Type": <contentType> }, expiresAt }
  400 validation-error, errors.<field> = [rule message]
POST /api/v1/assets/{assetId}/confirm      → 200 AssetResponse
  AssetResponse = { id, fileName, contentType, sizeBytes, status: "pending"|"ready"|"failed", failureReason: string|null }

Asset, internal (contracts/assets.py, camelCase):
POST /api/v1/internal/assets/claim                       require_service("assets:claim")
  ClaimRequest  = { workspaceId, userId, messageId, assetIds: uuid[1..10] }
  ClaimResponse = { items: AttachmentMeta[] }            ← in assetIds order
  AttachmentMeta = { assetId, fileName, contentType, sizeBytes }
  409 conflict, errors = { "<assetId>": ["not-found"|"not-yours"|"not-ready"|"already-attached"] } — nothing claimed
POST /api/v1/internal/assets/{assetId}/download-url      require_service("assets:download")
  DownloadUrlRequest = { workspaceId, messageId }  →  200 DownloadUrlResponse = { url, expiresAt }
  404 — other workspace, not claimed by that message, or not ready

Messaging:
SendMessageRequest = { body, attachmentIds: uuid[] = [] } · send_message = { channelId, body, attachmentIds? }
Attachment         = { assetId, fileName, contentType, sizeBytes }; MessageResponse.attachments: Attachment[]
GET /api/v1/messages/{messageId}/attachments/{assetId}/download-url → 200 { url, expiresAt }
409 details: not-found "An attachment could not be found." · not-yours "An attachment was uploaded by
someone else." · not-ready "An attachment has not finished uploading." · already-attached "An
attachment is already on another message."
```

**Fixtures.** `garage_server` (session, `testkit/garage.py`, in `CONTAINER_FIXTURES`): `images.GARAGE =
"dxflrs/garage:v2.3.0"`, `docker/garage/garage.toml` mounted at `/etc/garage.toml`, ports 3900 and
3903. It sets `GARAGE_*` env vars (key `GK000000000000000000000001`, the toml's admin token,
`GARAGE_CORS_ORIGINS=http://spa.test`), loads `charts/collabhub-deps/files/garage-bootstrap.py` by path
with `importlib`, calls its `main()`, and restores the environment. The real bootstrap, not a copy: today's `main()`
already does layout, bucket, key and allow, so only CORS is red. It yields `GarageServer(endpoint,
access_key, secret_key, bucket)`. `asset/tests/integration/conftest.py` imports `asset.*` **inside
fixtures**, so each file fails on its own import.

Messaging (`tests/integration/conftest.py`): `build_settings` gains `asset_internal_url="http://asset.invalid"`,
`service_token_url="http://auth.invalid/token"` and `messaging_service_client_secret="test-secret"`, so
every existing test still builds the app once those settings exist (ignored today). `asset_stub`
imports `contracts.assets` **inside the fixture body**, serves a FastAPI app built from it with
`testkit.apps.serve`, records each claim and download-url request, takes scripted refusals and a "down"
switch (answers 503), and also answers `POST /token` (`{accessToken, expiresIn}`, counting calls). It
yields `AssetStub(url, token_url, …)`. `client_for(asset_internal_url=stub.url, service_token_url=stub.token_url)`
points REST at it; the new **`realtime_url_for(**overrides)`** does the same for the socket — `client_for`'s
shape over `serve(build_asgi_app(build_settings(…, **overrides)))` (`conftest.py:114-123` builds from
`app_settings` and can't be pointed anywhere). At red, every test that requests `asset_stub` errors
in setup with `ModuleNotFoundError: No module named 'contracts.assets'`; the tests marked *no stub*
below never request it and show their own red.

| Test | Proves | Expected red |
|---|---|---|
| `testkit test_garage.py::test_the_bootstrap_makes_the_bucket_and_allows_the_key` — admin API `GET /v2/GetBucketInfo?globalAlias=collabhub-assets` with the bearer token (stdlib `urllib`, as the bootstrap's `call()` does, `garage-bootstrap.py:43-54`): the key is listed with `read` and `write`; and an unsigned `GET {endpoint}/collabhub-assets/` answers a 4xx with an S3 XML `<Error>` body, so the S3 API is up. No S3 client: `uv.lock` has none, and Asset's tests sign | fixture works | passes at red — harness check (the bootstrap already does layout, bucket, key and allow) |
| `::test_cors_preflight_allows_only_the_app_origin` — one test: an `OPTIONS` preflight for `PUT` with `Content-Type` from `http://spa.test` gets `access-control-allow-origin: http://spa.test`, and the same preflight from `http://evil.test` gets no such header | R16 CORS, both sides in one test | assertion on the first half: no `access-control-allow-origin` (no CORS rules yet) |
| `test_images.py` gains `("garage", "GARAGE")` | pin matches Compose | passes at red |
| `test_object_store.py::test_presigned_put_stores_the_bytes` · `::test_presigned_put_signs_the_content_type` (PUT with `text/plain` → 403) · `::test_head_reports_the_size` · `::test_head_of_a_missing_key_is_none` · `::test_presigned_get_carries_the_disposition` · `::test_urls_are_signed_for_the_public_endpoint` (two endpoints, URL host is the public one) | the `ObjectStore` against real Garage | `ModuleNotFoundError: asset.object_store` |
| `test_uploads.py::test_upload_url_reserves_a_pending_asset` · `::test_upload_url_refuses_svg_with_the_field` · `::test_confirm_marks_ready_after_the_put` · `::test_confirm_fails_a_short_upload` · `::test_confirm_fails_a_missing_object` · `::test_confirm_twice_is_unchanged` · `::test_another_users_asset_is_404` · `::test_another_workspaces_asset_is_404` (each asserts `detail == "No such asset."`) · `::test_the_object_key_is_workspace_attachment_id` | R1, R2, Decided 4 | error at setup: `ModuleNotFoundError: No module named 'asset.migrations'`, raised by the database fixture |
| `test_internal.py::test_claim_returns_metadata_in_request_order` · `::test_claim_is_all_or_nothing` (one ready + one pending → 409, the ready one still unclaimed) · `::test_claim_again_for_the_same_message_is_ok` · `::test_two_messages_claiming_one_asset_at_once_one_wins` (`asyncio.gather`, both orders) · `::test_a_user_token_cannot_claim` (401) · `::test_the_wrong_scope_is_403` · `::test_download_url_for_the_claiming_message` · `::test_download_url_for_another_message_is_404` · `::test_download_url_for_another_workspace_is_404` | R7, R10, D43 | `ModuleNotFoundError: asset.migrations` |
| `messaging test_attachments.py::test_rest_send_carries_attachments_in_order` (history and the response agree) | R6, R8 | setup error: `ModuleNotFoundError: No module named 'contracts.assets'` (`asset_stub`) — so are all rows marked *stub* |
| `::test_socket_send_acks_attachments_and_broadcasts_them` (`realtime_url_for`; ack and `message_received` equal) | R6, R8 | *stub* |
| `::test_a_body_may_be_empty_only_with_an_attachment` — one test: `""` with no ids → 400 `"A message cannot be empty."`, then `""` with one ready asset → 201 | R6, guard and positive together | *stub* |
| `::test_eleven_ids_are_400` · `::test_a_duplicate_id_is_400` — *no stub*: refused before any call to Asset | R2, decision 26 | 201: the field is ignored today |
| `::test_a_refused_claim_is_409_and_nothing_is_saved` (history empty after) · `::test_a_retry_after_a_lost_ack_is_already_attached` | R7, the timeline | *stub* |
| `::test_asset_down_is_503_and_nothing_is_saved` (stub "down"; parametrized REST and socket — the socket acks the 503 Problem) | R7 | *stub* |
| `::test_token_endpoint_down_is_503` — *no stub*: `client_for(service_token_url="http://auth.invalid/token")` and one random asset id; `detail` is decision 12's | R7 | 201: the id is ignored |
| `::test_the_claim_carries_the_callers_workspace_and_the_new_message_id` (stub's recorded request vs the token's `wsp` and the response id) · `::test_the_token_is_reused_across_sends` (two sends, one `/token` call) | CH001, claim-then-insert, Decided 3 | *stub* |
| `::test_a_deleted_message_shows_no_attachments` (asserts the pre-delete attachments first; then REST, `message_deleted` payload, history) · `::test_an_edit_keeps_the_attachments` | R12 | *stub* |
| `::test_download_url_for_an_invisible_channel_is_404` — *no stub*: a message in Ada's private channel, Grace asks with a random asset id; `detail == "No such channel."` | R10 | 404 `"Not Found"` (no route): the detail tells it apart |
| `::test_download_url_for_a_visible_message` · `::test_download_url_for_a_deleted_message_is_404` · `::test_download_url_for_an_asset_not_on_the_message_is_404` (both `"No such attachment."`) · `::test_download_url_with_asset_down_is_503` | R10 | *stub* |
| `test_schema.py::test_message_attachments_key_and_uniqueness` · `::test_messages_has_no_attachments_column` | Decided 5, decision 8 | table missing / column present |

Leave uncommitted.

## Task 3: The SPA's red (RED)

**Helpers first.** `test/api.ts`: `asset.post(path, reply)` and `asset.problem(...)` typed from
`types/asset.ts` (the same `stub()` with `ASSET_URL`); `garage.put(status = 200)` and
`garage.putFails()` (`HttpResponse.error()`) on `http://garage.test/*`; `record()` parses JSON only
when the request's `content-type` is JSON and keeps `{ size }` otherwise. `factories.ts`:
`anAttachment(overrides)`. MSW's XHR interceptor fires `upload` `loadstart/progress/load/loadend`
for a request with a body (`@mswjs/interceptors/src/interceptors/XMLHttpRequest/XMLHttpRequestController.ts:305-326`,
installed at the primary checkout), so progress is testable without a real network.

**Interfaces** (`src/frontend/src`):
- `lib/config.ts`: `ASSET_URL` (dev fallback `http://localhost:8004`)
- `lib/api/asset.ts`: `requestUploadUrl(token, {fileName, contentType, sizeBytes})`, `confirmUpload(token, assetId)`; `lib/api/messaging.ts`: `getAttachmentUrl(token, messageId, assetId)`, `type Attachment`
- `lib/upload/xhrPut.ts`: `putFile({url, file, headers, onProgress(fraction), signal}): Promise<void>`; rejects `new Error('Upload failed')` on non-2xx or a network error
- `features/attachments/rules.ts`: `MAX_FILES = 10`, `MAX_FILE_BYTES = 52_428_800`, `MAX_NAME_CHARS = 255`, `checkFile({name,size,type}): string | null` (the server's wording, Task 1), `batchRefusal(attached, added): string | null` → `"At most 10 files per message — 3 attached, 12 added."`, `pastedName(date): string`, `filesFromPaste(data: DataTransfer): File[] | null` (`null` = let the browser paste)
- `stores/attachments.ts`: `Chip = {localId, fileName, contentType, sizeBytes, status: 'uploading'|'ready'|'failed', progress, assetId: string|null, error: string|null}`; `useAttachmentStore` with `chips: Record<channelId, Chip[]>`, `add`, `update(localId, patch)` (a no-op when no chip has that `localId`, decision 37), `remove(channelId, localId)`, `restore(channelId, chips)` (restored chips first, then the current ones, nothing dropped — decision 33), `clear(channelId)`, `reset()`
- `features/attachments/uploads.ts`: `addFiles(channelId, files, getToken): string | null` (returns the batch refusal), `cancel(localId)`, `cancelAll()`. It runs upload-url → `putFile` → confirm outside React, so a channel switch can't stop it; one `AbortController` per chip, checked before each step and passed to each request (decision 37)
- `features/attachments/useAttachmentUrl.ts`: `URL_STALE_MS = 780_000`, `attachmentUrlKeys.one(ws, messageId, assetId)`, `useAttachmentUrl(...) → { url: string | null }` — the cached URL while mounted, stale or not; `null` only while a mount that found it stale (or empty) is fetching (decision 36), `freshAttachmentUrl(queryClient, token, ws, messageId, assetId): Promise<string>`
- `stores/chat.ts`: `sendErrors: Record<channelId, string>`, `setSendError(channelId, text | null)`
- `useSendMessage` variables become `{ channelId, body, attachments: Chip[] }`; every cache and store write keys on `variables.channelId` (decision 35). `onMutate` clears that channel's send error (decision 34); the **hook-level** `onError` merges text and chips back into `variables.channelId`'s draft (decision 33) and sets that channel's send error. TanStack Query v5 keeps one `#mutateOptions`, replaced by every `mutate` call (`query-core/src/mutationObserver.ts:132-142`), and runs it only for the current mutation (`:164-208`). That is why today's per-call `onError` misses an earlier send.
- testids for the BDD suite only: `attach-files` (input), `attachment-chip` (`data-file-name`, `data-status`), `message-attachment-image`, `message-attachment-file` (both `data-file-name`), `message-attachment-download`

| Test (file) | Proves | Expected red |
|---|---|---|
| `rules.test.ts`: allow-list incl. SVG refused; 0 / 1 / limit / limit+1 bytes; 255 / 256 chars; `batchRefusal(3, 7)` null, `(3, 8)` the exact sentence; `pastedName` with fake `Date` pads every field; `filesFromPaste` → `null` with `text/plain` + a file, files with no text, renames only `image.png` | R2, R3, R4, decision 27 | `Failed to resolve import "./rules"` |
| `xhrPut.test.ts`: sends the signed `Content-Type`, reports progress then resolves; 403 rejects "Upload failed"; network error rejects; abort rejects | R5 | `Failed to resolve import` |
| `uploads.test.ts`: a file runs upload-url → PUT → confirm and ends `ready` with its `assetId`; a confirm answering `failed` shows `failureReason`; a refused file is a `failed` chip and never requested; an 11th file refuses the whole batch with nothing added (and 10 is accepted); a failed chip counts, and removing it makes room; an upload started in one channel finishes into that channel's chips after `activeChannel` changes; **`cancel` while upload-url is held** (deferred MSW handler): released, the chip stays gone and `requests()` holds no PUT and no confirm; **`reset()` while confirm is held**: released, `chips` stays `{}`; and the positive in each — the same held step, released with no cancel, ends `ready` | R2, R4, R5, R15, decision 37 | `Failed to resolve import` |
| `stores/attachments.test.ts`: `update` of an unknown `localId` changes nothing, and of a known one patches it; `restore` puts the restored chips before the current ones and keeps all 11 when 8 meet 3 | decisions 33, 37 | `Failed to resolve import` |
| `MessageComposer.test.tsx` (add): the paperclip input attaches; a drop attaches; Send is disabled while a chip uploads and **enabled once all are ready** (same test); Send with only chips emits `{channelId, body: '', attachmentIds}` in chip order; ✕ removes a ready chip; ✕ on an uploading chip (PUT held) removes it and no confirm follows the release; with 11 chips Send is disabled and "At most 10 files per message — remove 1." shows, and with 10 it is enabled; the batch refusal is shown | R3, R5, R6, decisions 33, 37 | `getByLabelText('Attach files')` throws — there is no paperclip control |
| `MessageComposer.test.tsx` (add, one test): **paste** — focus the box, then `user.paste(stub)` (as `:75-76` already pastes; never `fireEvent.paste`, which inserts nothing in jsdom — user-event does the default insert unless prevented, `user-event` 14.6.7 `event/behavior/paste.js:6-15`). The stub carries `types`, `files`, and `getData` answering both `'text'` and `'text/plain'`. A paste with text and a file inserts the text and adds no chip; then a paste with only a file named `image.png` (`getData` → `''`) adds a chip `Pasted image <yyyy-mm-dd hh.mm.ss>.png` | R3, decision 27 | the first half passes at red (user-event inserts the text); the second half: `findByText(/Pasted image/)` times out — nothing handles a paste |
| `useMessages.test.ts` (modify): every `mutate('…')` (`:134, 157, 181, 196, 214`) becomes `mutate({ channelId: CHANNEL, body: '…', attachments: [] })`; `:204` expects "The server did not confirm that message — it may still arrive." | R13 wording | the old hook takes the object as the body: `:139`'s `toMatchObject({ body: 'lunch is at one' })` and `:141`'s emitted payload fail on an object body; `:204` fails on the old wording. The other three still pass (their outcome doesn't read the body) |
| `useSendMessage.restore.test.ts` (new; every test asserts on chips, so the load failure hides nothing): **two sends in flight, the first refused** — A's text and chips return to A while B's send is pending; **re-rendered for B mid-send** — A's refusal restores to A, sets `sendErrors[A]` only, and removes the `temp:` row from A's cache, leaving B's alone; **into a non-empty draft** — A holds "new" and one chip, the refused "old" with two chips → draft `"old\nnew"`, chips old, old, new; **the next send for A clears `sendErrors[A]`**, while `sendErrors[B]` stays | R13, R14, decisions 33–35 | `Failed to resolve import "../../stores/attachments"` |
| `ChannelView.test.tsx` (add): an error shown in A's composer is gone in B and back on returning to A | R14 | error still shown in B |
| `ChatLayout.attachments.test.tsx` (new; `ChatLayout.test.tsx`'s shell and session setup): a workspace switch empties every channel's chips and aborts a held upload; unmounting (sign-out) does too | R15 | `Failed to resolve import "../../stores/attachments"` |
| `AttachmentList.test.tsx`: images render `<img>` with the fetched URL, size-capped; a PDF renders name, size and a download link; a tombstone renders none; a pending (`temp:`) message requests no URL; an `<img>` error refetches once then shows "Couldn't load — retry", and retry refetches | R9, R11, decision 30 | `Failed to resolve import` |
| `useAttachmentUrl.test.ts` (`vi.useFakeTimers({ toFake: ['Date'] })`): at 779 999 ms a remount uses the cached URL with no request; at 780 001 ms it requests first and exposes `url: null` until the new one lands; **at 781 000 ms, still mounted, a re-render, a focus (`focusManager.setFocused(false)` then `true`, `query-core/src/focusManager.ts:59-72`) and a reconnect (`onlineManager.setOnline(false)` then `true`) leave `url` unchanged and record no request** — reset both managers to `undefined`/`true` after; `freshAttachmentUrl` refetches only when stale; a click opens the window synchronously and sets its location after the fetch | R11, decisions 29, 36 | `Failed to resolve import` |

Leave uncommitted.

## Task 4: The journey (RED)

```gherkin
@bdd
Feature: File attachments

  A message can carry files: images to look at and PDFs to download. They go
  straight from the sender's browser to storage and back, and anyone who can
  see the message can open them.

  Background:
    Given Ada is signed in

  # The one journey a browser is needed for: the upload, storage's CORS, the
  # claim, the broadcast and a download of the same bytes. The limits, the
  # claim rules, paste, freshness and restore are proven lower down.
  Scenario: Grace sees the image and the PDF Ada sends
    Given Ada has created a public channel named "general"
    And Grace is looking at the "general" channel
    When Ada attaches "diagram.png" and "notes.pdf"
    And Ada sends "the plans"
    Then Grace sees "the plans" in the channel without reloading
    And Grace sees "diagram.png" shown inline with "the plans"
    And Grace sees "notes.pdf" as a download with "the plans"
    And the "notes.pdf" Grace downloads is the file Ada attached
    And "the plans" appears in Ada's channel exactly once
```

- Reused verbatim: `Ada is signed in`, `Ada has created a public channel named`, `Grace is looking
  at the "{name}" channel` (`steps/conftest.py:54`), `Ada sends` (`:143`), `Grace sees "{body}" in
  the channel without reloading` (`test_realtime_steps.py:57`), `"{body}" appears in Ada's channel
  exactly once` (`:77`). New phrases: the attach step and the three `Then`s before the last, in
  `test_attachment_steps.py`.
- The attach step builds its bytes in the step (a valid 1×1 PNG and a minimal PDF), passes them to
  `ChatPage.attach_files([...])` as Playwright file payloads (`{name, mimeType, buffer}`) on
  `attach-files`, and waits until every `attachment-chip` has `data-status="ready"`. The inline
  check waits on `naturalWidth > 0` through `expect`; the download uses `page.expect_download()`
  and compares bytes. Selectors live in `ChatPage` only.
- Harness (`tests/bdd/conftest.py`): `MESSAGING_TABLES` gains `message_attachments`; `stack_ready`
  probes `BDD_ASSET_PORT` (default 8014) `/health/ready`; `reset_messaging` also truncates `assets`
  in `collabhub_asset`.
- Expected red: `--collect-only` parses; `--generate-missing` lists exactly the four new steps (the
  attach step and three `Then`s — the last `Then` is reused).
  It runs in Task 10.

Leave uncommitted.

## Task 5: Shared, contracts and Asset (GREEN)

```python
# asset 0001_assets.py — the claim and the key are the constraints that matter.
op.create_table("assets",
    sa.Column("id", UUID, primary_key=True),                 # uuid7, app-generated
    sa.Column("workspace_id", UUID, nullable=False),          # Auth's: no FK
    sa.Column("owner_id", UUID, nullable=False),              # Auth's: no FK
    sa.Column("file_name", sa.Text, nullable=False), sa.Column("content_type", sa.Text, nullable=False),
    sa.Column("size_bytes", sa.BigInteger, nullable=False), sa.Column("purpose", sa.Text, nullable=False),
    sa.Column("bucket", sa.Text, nullable=False), sa.Column("object_key", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False, server_default="pending"),
    sa.Column("failure_reason", sa.Text), sa.Column("checksum", sa.Text),
    sa.Column("message_id", UUID),                            # Messaging's: no FK; set once by claim
    sa.Column("created_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
    sa.Column("confirmed_at", TIMESTAMPTZ), sa.Column("claimed_at", TIMESTAMPTZ), sa.Column("deleted_at", TIMESTAMPTZ),
    sa.UniqueConstraint("bucket", "object_key"))
```

- [ ] `contracts/assets.py` to Task 2's internal shapes, plus `ClaimRefusal(StrEnum)` and the two
  scope constants. `shared/service_tokens.py` to Task 1. Task 1's shared tests pass.
- [ ] Asset: settings (+`object_store_public_endpoint`, `redis_cache_url` — both required, so
  `asset/tests/unit/test_health.py:10-15`'s `Settings(...)` gains them — `cors_allowed_origins`;
  −`asset_allowed_content_types`), `db.py`, `models.py`, Alembic copied from Messaging's shape,
  `migrate.py`, `entrypoint.sh` (`RUN_MIGRATIONS`), `rules.py`, `object_store.py`
  (`ObjectStore` Protocol: `presign_put(key, content_type) -> (url, expires_at)`,
  `presign_get(key, content_disposition) -> (url, expires_at)`, `async head(key) -> int | None`;
  `S3ObjectStore` with two clients, `region_name="garage"`, `Config(signature_version="s3v4",
  s3={"addressing_style": "path"})`; `head` runs `head_object` on a thread and maps 404 to `None`).
- [ ] `routers/assets.py` and `routers/internal.py`. Claim: `SELECT … WHERE id = ANY(:ids) AND
  deleted_at IS NULL ORDER BY id FOR UPDATE`, decide every row with `claim_refusal`, refuse all or
  update all. `main.py`: `install_cors`, `install_problem_handlers`, `install_security` with a `Denylist` on
  R1, both routers. Rewrite the module docstring (no longer a scaffold). `openapi.py` like Messaging's.
- [ ] `python -m asset.openapi > src/frontend/openapi/asset.json`; `generate:api` also emits
  `src/types/asset.ts`. Tasks 1–2's Asset and testkit tests pass, except CORS (Task 7).
- [ ] Leave uncommitted.

## Task 6: Messaging (GREEN)

```python
# 0005_message_attachments.py (or the next free number) — drop the never-used array in the same step.
op.create_table("message_attachments",
    sa.Column("message_id", UUID, sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False),
    sa.Column("position", sa.SmallInteger, nullable=False),     # attach order, 0-based
    sa.Column("asset_id", UUID, nullable=False),                # Asset's: no FK (Conventions §2)
    sa.Column("file_name", sa.Text, nullable=False), sa.Column("content_type", sa.Text, nullable=False),
    sa.Column("size_bytes", sa.BigInteger, nullable=False),
    sa.PrimaryKeyConstraint("message_id", "position"), sa.UniqueConstraint("asset_id"))
op.drop_column("messages", "attachments")   # downgrade re-adds it: uuid[] NOT NULL DEFAULT '{}'
```

- [ ] Model `MessageAttachment`; drop `Message.attachments`; settings (decision 20); `main.py`
  builds an `httpx.AsyncClient` (3 s timeout), a `ServiceTokenSource` and an `AssetClient` on
  `app.state.assets`, closed in the lifespan, and passes the client into `RealtimeContext`
  (`realtime.py:103-115` gains `assets: AssetClient`; built at `main.py:152-157`).
- [ ] `attachments.py`: the Task 1 rules plus `async for_messages(session, ids) -> dict[UUID,
  list[MessageAttachment]]` (one query, `ORDER BY message_id, position`) and `add(...)`.
  `messages.create` gains `message_id` and `attachments`, and passes `allow_empty=bool(attachments)`.
- [ ] `_as_message(row, *, reactions, attachments)`: both required, `visible()` applied. Every caller
  loads them page-wide, as reactions do: `routers/messages.py` (4), `reactions.py`, `search.py`,
  `realtime_writes.py` (3), `tests/unit/test_indexing.py` (6 call sites, `attachments=[]`).
- [ ] Send, REST and socket: visibility → `check_attachment_ids` + body → `uuid7()` → `claim` (only
  when there are ids) → insert → commit → publish → index. `ClaimRefusedError` → 409
  `refusal_detail`; `AssetUnavailableError` → 503. The socket handler acks the same Problem.
- [ ] `GET /api/v1/messages/{message_id}/attachments/{asset_id}/download-url` on the existing router
  (Ingress already allows `/api/v1/messages`, `ingress.yaml:57`).
- [ ] Schema docstrings that say attachments are "always empty" (`schemas.py:196-198, 238-241`,
  `realtime_writes.py:60-73`, `models.py:149-154`) are rewritten.
- [ ] Regenerate `openapi/messaging.json` and the types. Tasks 1–2 pass; Messaging integration 211 or
  more + new.
- [ ] Leave uncommitted.

## Task 7: Garage, Compose and the charts (GREEN)

- [ ] `garage-bootstrap.py`: `ensure_cors(bucket_id)` from `GARAGE_CORS_ORIGINS` (comma-separated;
  read with a default of empty → skip), called after `allow`; idempotent. If v2.3.0's admin API
  doesn't take CORS rules, use decision 23's fallback and record it. testkit's CORS tests pass.
- [ ] `.env.example`: `OBJECT_STORE_ACCESS_KEY`/`_SECRET_KEY` in Garage format (k3d's values),
  `OBJECT_STORE_PUBLIC_ENDPOINT=http://localhost:3900`, `GARAGE_ADMIN_TOKEN`, `GARAGE_CORS_ORIGINS=http://localhost:5173`,
  `MESSAGING_SERVICE_CLIENT_ID=messaging`, `MESSAGING_SERVICE_CLIENT_SECRET=messaging-local-secret`,
  `AUTH_SERVICE_CLIENTS` gains `{"client_id":"messaging","secret":"messaging-local-secret","scopes":["assets:claim","assets:download"]}`;
  `ASSET_ALLOWED_CONTENT_TYPES` removed; `BDD_ASSET_PORT=8014`, `BDD_GARAGE_PORT=3910`.
- [ ] `docker-compose.yml`: `garage-bootstrap` (one-shot, `restart: "no"`, `python:3.12-slim`, script
  mounted read-only, `GARAGE_ADMIN_URL=http://garage:3903`); `asset` waits for it to complete
  (`service_completed_successfully`) and gets `REDIS_CACHE_URL`, `CORS_ALLOWED_ORIGINS` and
  `OBJECT_STORE_PUBLIC_ENDPOINT`; `messaging` gets the four client vars and `depends_on: asset`
  (`service_started`). `docker-compose.test.yml`: publish `asset` on `BDD_ASSET_PORT` and `garage`
  3900 on `BDD_GARAGE_PORT`, `AUTH_ISSUER` + `CORS_ALLOWED_ORIGINS` for `asset`, the public endpoint
  `http://localhost:3910`, `GARAGE_CORS_ORIGINS=http://localhost:5183`, and frontend `VITE_ASSET_URL`.
- [ ] `charts/collabhub`: Ingress `range` for Asset with `/api/v1/assets` only, replacing the "no
  public API yet" comment; `asset/migrate-job.yaml` like Messaging's; `RUN_MIGRATIONS: "false"`;
  `values.yaml` env for both services; NetworkPolicies: Messaging egress to `asset`, Asset ingress
  from `messaging`.
- [ ] `charts/collabhub-deps`: `messagingClientSecret` credential (required, no default; k3d value
  `messaging-local-secret`, lab header lists it); `app-secrets.yaml` adds the messaging service
  client, `SERVICE_TOKEN_URL` and `MESSAGING_SERVICE_CLIENT_SECRET` to Messaging's Secret,
  `REDIS_CACHE_URL` to Asset's; `garage.yaml` an Ingress for `s3.<host>` → `garage:3900` and
  `GARAGE_CORS_ORIGINS={{ .Values.origin }}` on the Job.
- [ ] `scripts/deploy.sh`: `--set-string components.asset.env.OBJECT_STORE_PUBLIC_ENDPOINT=<scheme>://s3.<host>[:port]`
  derived from `APP_ORIGIN` beside the `AUTH_ISSUER` lines (`:160-165`). `scripts/test.sh:88` gains
  `--set-string messagingClientSecret=lint-messaging-secret`.
- [ ] `scripts/test.sh lint` passes (it renders both charts and checks the Ingress). Leave uncommitted.

## Task 8: The SPA (GREEN)

- [ ] `config.ts`, `lib/api/asset.ts`, `getAttachmentUrl`, `xhrPut.ts`, `rules.ts`, `stores/attachments.ts`,
  `uploads.ts` to Task 3's interfaces. Chips are client state (D24); URLs and messages stay in Query.
- [ ] `MessageComposer`: paperclip button + hidden multi-file `input` (`accept` from the allow-list),
  `onDrop`/`onDragOver`, `onPaste` through `filesFromPaste`, `AttachmentChips` (✕ = `cancel` + `remove`),
  the batch refusal, and Send enabled when connected, every chip is ready, there are at most 10, and
  there is text or a chip (over 10: decision 33's sentence). The error shown is `sendErrors[channelId]`.
  `ChannelView` keys the composer by channel.
- [ ] `useSendMessage`: Task 3's variables, every write on `variables.channelId`; the optimistic row
  carries chip metadata; new timeout wording; `onMutate` clears the channel's error; hook-level
  `onError` merges back (decision 33). `ChatLayout`: on workspace change and on unmount,
  `cancelAll()` + `reset()`.
- [ ] `useAttachmentUrl` with decision 36's query options.
- [ ] `MessageItem` renders `AttachmentList`: images through `useAttachmentUrl`, one `onError` refetch,
  then the retry placeholder; PDFs as a chip with `formatBytes` and a download through
  `freshAttachmentUrl` → `location.assign`.
- [ ] Task 3 passes; `npm --prefix src/frontend run typecheck` clean. Leave uncommitted.

## Task 9: The record

- [ ] Doc 04: §3 the four routes built, and that `GET /assets/{id}` and the public download route are
  not built (Messaging mints downloads, D43); "viewer" means "can see the message"; §4 the table as
  built; §4.1 the key layout and the public endpoint; CORS; §6 the settings; §9 D15 closed.
- [ ] Doc 02: §3.1.3 `attachmentIds`, `Attachment`, the empty-body rule; §3.1.4 tombstones carry no
  attachments, edits keep them; the download route; §3.2 `send_message` payload and the 409/503
  acks; §4 `message_attachments` and the dropped column; §6 the four settings.
- [ ] Doc 06 §6: the composer, paste naming, all-or-none batches, freshness at 780 s, restore and
  per-channel errors; §5.2's timeout wording.
- [ ] Register: D15 🟢; D43 🟢 (attachment downloads follow message visibility, minted through
  Messaging; strict claim); D13 note (still one bucket); D16 note (unsent and deleted blobs
  accumulate); D34 note (Garage fixture landed). ADR for D43 and the strict claim, with the
  `adr-writer` skill. README: the manual Garage steps go, the `.env` key change and the new lab
  `--set-string` are added.
- [ ] Doc 04 §4.2/§5: confirm enqueues no `jobs:thumbnail` here (*Not in this issue*). Vocabulary:
  the four new phrases into `docs/plans/ch06/gherkin/00-scenario-vocabulary.md`.
- [ ] Sweep: `grep -rn "skeleton\|no public API yet\|always empty\|attachmentIds" docs/design src/services charts`
  for anything that still says attachments don't exist; `testkit/images.py:6-7` docstring;
  CLAUDE.md's "republishes only the five ports" and `tests/bdd/conftest.py`'s docstrings (now seven);
  `docker/garage/garage.toml:4-6` ("one-off manual step"); `messaging/README.md:111`.

## Task 10: Verification

- [ ] **First**, `cp .env.example .env`: the worktree's `.env` was copied from the old `.env.example`
  (`scripts/deliver.sh:231`) and Compose reads it (`docker-compose.yml:16`), so without this the test
  stack starts with the unimportable `collabhub-local` key, no Messaging client and no
  `GARAGE_CORS_ORIGINS`.
- [ ] `scripts/test.sh lint unit integration`, then `scripts/test.sh e2e` — each once, the whole e2e
  layer, because the journeys' stack changes (Asset, Garage, the bootstrap). Counts at or above
  baseline. `-- -k attachments` only to iterate.
- [ ] `python3 .claude/hooks/checks/conventions.py $(git diff --name-only HEAD)` and
  `.claude/hooks/security.sh`; a waiver names every checker that fires on its line.
- [ ] **First real run** on Compose, with Ada and Grace in two
  browsers: the six *Acceptance* checks in the issue, plus one upload and one download on k3d
  through `s3.localhost:8080`. Expect it to find something; fix it with a test and record it below.
- [ ] If issue 2 or 3 merged meanwhile, merge `main`, renumber the migration if taken, rerun the above.
- [ ] Fill in *Found while building*. Leave the worktree dirty and report.

## Found while building

*Filled in by the code-writer, round 1.*

- **Garage CORS: the admin API takes it, in S3's element names.** `UpdateBucket` accepts
  `corsRules` on v2.3.0, but each rule uses `ID`, `AllowedOrigin`, `AllowedMethod`, `AllowedHeader`,
  `ExposeHeader`, `MaxAgeSeconds` (singular, PascalCase); the camelCase plural names are refused with
  a 400. No fallback key was needed. **`AllowedHeader` must be lower-case `content-type`**: Garage
  compares it to the browser's lower-cased `Access-Control-Request-Headers` as written, and
  `Content-Type` made the preflight fail. The bootstrap now stops at once on a 4xx instead of
  retrying for two minutes. Pinned by `testkit … test_cors_preflight…` (first half passes; the second
  is sent back — see the send-back file, Garage decorates its own 403 with `*`).
- **`botocore` signs `Content-Type`**: `botocore/auth.py:242-250` signs every header not in
  `SIGNED_HEADERS_BLACKLIST` (`:64`), and `generate_presigned_url` puts `ContentType` in the request
  headers. Pinned by `test_presigned_put_signs_the_content_type` (passes).
- **`ASSET_INTERNAL_URL` is Asset's origin, with no path.** `.env.example` and the chart carried
  `…/api/v1/internal`; Messaging (and later the Worker) appends `/api/v1/internal/…` itself and the
  test stub is at the root. Changed in `.env.example`, `charts/collabhub/values.yaml` (Messaging and the
  Worker), the READMEs. The Worker reads it nowhere yet. No test (configuration).
- **`.env.example` takes the k3d Garage key** (`GK00000000000000000c011ab0`), not the test fixture's.
- **Messaging settings default to empty** (`SERVICE_TOKEN_URL`, `ASSET_INTERNAL_URL`,
  `MESSAGING_SERVICE_CLIENT_SECRET`), as the Worker's do, so existing unit tests that build `Settings`
  still pass; an unset URL makes a send with files answer 503. Decision 20 did not say.
- **`messages.create` returns `(Message, list[MessageAttachment])`** and takes `message_id` and
  `attachments`; body validation runs *before* the claim in both transports (so a bad body never
  claims files), and the shared `attachments.claim_for_send` maps refusals to the 409/503 Problems.
  Pinned by `test_a_refused_claim_is_409…`, `test_asset_down_is_503…`.
- **Internal routes take `_caller: ServicePrincipal = Depends(require_service(scope))`**, not
  `dependencies=[…]`, because CH003 reads the parameter list. CH001 did not fire, so no waiver.
- **`MessageItem` takes an `attachments` slot (a `ReactNode`)** filled by `MessageList`, not
  `accessToken`/`workspaceId` props: `MessageItem.test.tsx` was not extended and builds the row
  without them. The composer's key is `composer-<channelId>` — `MessageList` is keyed by the bare id
  and sibling keys must differ (React duplicated both lists otherwise; found by `ChannelView.test.tsx`).
- **A PDF downloads with `window.location.assign`**, an image click uses `window.open` (decision 29).
- **`generate:api` now also emits `types/asset.ts`**; `openapi/*.json` were written with the editor
  (a shell redirect is not available to this stage) and checked identical to `python -m …openapi`
  with `diff`; docstrings on the route functions were kept ASCII so they round-trip.
- **The one-shot `garage-bootstrap` under `up --wait`**: the stack came up with `asset` waiting on it
  (the plan-reviewer's open question) — `--wait` accepts the exited(0) service.
- **The e2e stack is now per worktree.** The shared `collabhub-test` Postgres volume held a Messaging
  revision `0005` from another worktree, so `message_attachments` was never created. On the human's
  answer, `scripts/test.sh e2e` passes `-p collabhub-test-<repo directory>` and runs `down -v
  --remove-orphans` before `up`; the lock stays for the fixed ports. The journey then ran green (e2e
  21 passed). No test (script behaviour); the old `collabhub-test_*` volumes are the human's to remove.
- **Send-back to the test pair**: see `reviews/code-writer-sendback-3.md` (existing tests that
  construct `Message(attachments=…)`, `_as_message`, `RealtimeContext`, Asset's `Settings`; a
  `contype` bytes comparison; Garage's `*` on its 403).

## Not in this plan

Thumbnails and `jobs:thumbnail` · the retention sweep and `DELETE /assets/{id}` (D16) · attachments
on edit or on thread replies · search over file names · a virus scan · avatars and canvas images.

## Self-review

- **Issue coverage:** R1 → Tasks 2, 5; R2 → 1, 2, 3, 5, 8; R3 → 3, 8; R4 → 3, 8; R5 → 3, 8; R6 → 1, 2, 6;
  R7 → 1, 2, 5, 6; R8 → 2, 4, 6; R9 → 3, 4, 8; R10 → 2, 4, 5, 6; R11 → 3, 8; R12 → 1, 2, 6; R13 → 3, 8;
  R14 → 3, 8; R15 → 3, 8; R16 → 2, 4, 7. *Where the rules meet*: counts → `uploads.test.ts`; pending
  refused → `test_claim_refusals_in_order`; lost ack → `test_a_retry_after_a_lost_ack_is_already_attached`;
  claim then insert → `…carries_the_callers_workspace_and_the_new_message_id`; delete vs downloads →
  `test_download_url_for_a_deleted_message_is_404`; response and echo → the socket test plus the journey's last step;
  restore → `useSendMessage.restore.test.ts`. *Paths*: losing access → `…invisible_channel_is_404`; Asset down while
  viewing → `AttachmentList.test.tsx`'s retry; while sending → `test_asset_down_is_503…` plus restore.
- **Names:** `attachmentIds` on the wire; `Attachment` = `AttachmentMeta`; scopes `assets:claim`, `assets:download`.
- **Known ripple:** `_as_message`'s ten callers and `RealtimeContext` (Task 6), the `mutate('text')`
  calls (Task 3), every developer's `.env` (Garage key format; Task 10 first).

## Review responses

Round 1: 1 **fixed** — `contracts` stays GREEN (decision 25); stub tests' red is the setup error;
no-stub tests named. 2 **fixed** — new files for restore and workspace switch; the five `mutate`
calls rewritten with real reds. 3 **fixed** — each guard shares a test with its positive. 4 **fixed** —
admin API plus an unsigned S3 request, no client. 5 **fixed** — decision 36, the 781 s test.
6 **fixed** — decisions 33–35 and their tests. 7 **fixed** — decision 37 and the held-step tests.
8 **fixed** — `realtime_url_for`. 9 **fixed** — `realtime.py` mapped. 10 **fixed** — Task 10 refreshes
`.env` first. Minors taken: four new steps; Task 9's sweep and vocabulary; decision 38; doc 04 §4.2/§5;
the CH001 waiver. 780 s stays a literal, as the issue states it.
Round 2: 1 **fixed** — the paste test drives `user.paste` on the focused box with a stub answering `'text'`; red restated (first half passes, second times out). Minors left for a later stage: the restore file's fourth test gives its own red; the bootstrap exit under `--wait` (Task 10); `URL_STALE_MS` beside the TTL.
