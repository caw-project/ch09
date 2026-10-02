# Red tests — issue 4, round 1

BDD outside-in as the plan recommends (one journey, written first), with everything else pushed
down the pyramid: Python unit (4 files + 1 extended), Python integration (Garage, Asset, Messaging),
Vitest (10 files + 3 extended) and the one scenario. Every new test fails today or errors at
load/setup, except the harness checks marked *green by design* below. 211 Messaging integration
tests, 243 existing unit tests (Python) and 241 of the 243 existing Vitest tests still pass.

## Baseline

| Files changed | Before | After |
|---|---|---|
| Python unit: asset 2, messaging 94, shared 87, testkit 59 (242 incl. `test_message_body.py`) | 242 pass | 243 pass + 4 new failing (`test_message_body.py` 9 → 13; `test_images.py` +1 passing) |
| Messaging integration `test_schema.py` + `test_messages.py` | 45 pass | 43 pass + 2 new failing; the whole Messaging integration directory: 211 pass |
| testkit integration `test_containers.py` | 4 pass | 4 pass (+ `test_garage.py`: 1 pass, 1 fail) |
| Vitest (35 files) | 243 pass | 241 pass, 4 fail (2 new, 2 of the five reworked `useMessages` tests — as the plan says), 9 new files fail to load |
| `tests/bdd` collect | 20 | 21; `--generate-missing` prints nothing (every step binds) |

## Tests

First line of each failure is verbatim. "Match" is against the plan's expected red.

| File · test | Layer | Task | Proves | Observed red | Match |
|---|---|---|---|---|---|
| `asset/tests/unit/test_rules.py` | unit | 1 | allow-list, size/name/purpose bounds, key, confirm outcomes, claim order, disposition | `ModuleNotFoundError: No module named 'asset.models'` | differs, see below |
| `shared/tests/unit/test_service_tokens.py` | unit | 1 | margin (−61/−59 s), single flight, invalidate, failures not cached | `ModuleNotFoundError: No module named 'shared.service_tokens'` | yes |
| `messaging/tests/unit/test_attachments.py` | unit | 1 | count, duplicate, refusal wording, tombstone, `find_on` | `ModuleNotFoundError: No module named 'contracts.assets'` | differs, see below |
| `messaging/tests/unit/test_asset_client.py` | unit | 1 | claim body, 409/5xx/connect/401 mapping, download | `ModuleNotFoundError: No module named 'messaging.assets'` | yes |
| `messaging/tests/unit/test_message_body.py` (+4) | unit | 1 | `allow_empty`, decision 38 | `TypeError: validate_body() got an unexpected keyword argument 'allow_empty'` | yes |
| `testkit/tests/integration/test_garage.py::test_the_bootstrap_makes_the_bucket_and_allows_the_key` | integ. | 2 | fixture + real bootstrap | passes — **green by design** (harness check) | yes |
| `…::test_cors_preflight_allows_only_the_app_origin` | integ. | 2 | R16 CORS, both origins | `AssertionError: assert '*' == 'http://spa.test'` | differs, see below |
| `testkit/tests/unit/test_images.py` (+1 `garage`) | unit | 2 | pin matches Compose | passes — **green by design** | yes |
| `asset/tests/integration/test_object_store.py` (6) | integ. | 2 | presign, signed type, HEAD, disposition, public host | `ModuleNotFoundError: No module named 'asset.object_store'` (5 at setup, 1 in body) | yes |
| `…/test_uploads.py` (13), `test_internal.py` (15) | integ. | 2 | handshake, claim, race, download-url, tenancy | `ModuleNotFoundError: No module named 'asset.migrations'` (setup) | yes |
| `messaging/tests/integration/test_attachments.py` — 20 stub tests | integ. | 2 | send, socket, 409/503, claim contents, token reuse, tombstone, edit, download | `ModuleNotFoundError: No module named 'contracts.assets'` (setup of `asset_stub`) | yes |
| `…::test_eleven_ids_are_400` / `test_a_duplicate_id_is_400` | integ. | 2 | R2, decision 26 | `assert 201 == 400` | yes |
| `…::test_token_endpoint_down_is_503` | integ. | 2 | R7 | `assert 201 == 503` | yes |
| `…::test_download_url_for_an_invisible_channel_is_404` | integ. | 2 | R10 | `KeyError: 'detail'` (404 with no route; no `detail`) | yes |
| `messaging/tests/integration/test_schema.py` (+2) | integ. | 2 | decisions 5, 8 | `assert set() == {'asset_id', …}` and `assert 'attachments' not in {…}` | yes |
| Vitest: `rules`, `xhrPut`, `uploads`, `useAttachmentUrl`, `AttachmentList`, `stores/attachments`, `MessageComposer.attachments`, `useSendMessage.restore`, `ChatLayout.attachments` | Vitest | 3 | R2–R6, R9, R11, R13, R15, decisions 27–37 | `Failed to resolve import "./rules"` / `"../../stores/attachments"` / `"./AttachmentList"` / `"./xhrPut"` / `"./useAttachmentUrl"` / `"../attachments/uploads"` | yes |
| `useMessages.test.ts` — "shows the message at once…" | Vitest | 3 | R13 variables | `AssertionError: expected { …(11) } to match object { body: 'lunch is at one', …(2) }` | yes |
| `useMessages.test.ts` — "rolls back within five seconds…" | Vitest | 3 | R13 wording | `Expected: "The server did not confirm that message — it may still arrive."` / `Received: "…Nothing was sent."` | yes |
| `ChannelView.test.tsx` — "a send error stays in its channel" | Vitest | 3 | R14 | `expected document not to contain element, found <p …` (the error shown in #random) | yes |
| `ChannelView.test.tsx` — "attachments on a message" | Vitest | 3 | R9 wiring | `TestingLibraryElementError: Unable to find role="img" and name "diagram.png"` | extra test |

**Differences explained.** (1) `test_rules.py` imports `asset.models` (for `Asset`) before `asset.rules`, so
it stops there; both are missing, so every test needs the missing modules. (2) `test_attachments.py`
(unit) imports `contracts.assets` for `ClaimRefusal` (a GREEN file by plan), same reasoning.
(3) **Garage answers a preflight with `access-control-allow-origin: *` when a bucket has no CORS rules**,
not with no header: the plan's expected red ("no header") was wrong. The test is still right — the
allowed origin must get *its own* value, and the evil origin must get none — and it fails on the first half.
The plan's restore-file note: `useSendMessage.restore.test.ts`'s fourth test (send error clears) is red at load
too, and would be red as a test (`setSendError is not a function`).

## Types

`npm --prefix src/frontend run typecheck` — every error is a missing module or generated type:
`../lib/config` has no `ASSET_URL`; `../types/asset` and `../stores/attachments` not found;
`lib/api/messaging` has no `Attachment`; `./rules`, `./uploads`, `./xhrPut`, `./useAttachmentUrl`,
`./AttachmentList` not found; the `…/download-url` path is not in `PathsWith<"get">` (the generated
messaging types lack the route); `sendErrors`/`setSendError` missing on `ChatState`; `useSendMessage`'s
`mutate` takes a `string` (five reworked calls + the restore file). A few `TS7006 implicit any` follow
from the unresolved modules. Nothing else.

## BDD

`uv run pytest tests/bdd --collect-only -q` → 21 collected. `--generate-missing` prints no stub: the four
new steps are in `test_attachment_steps.py`, and the two reused ones now bind (see Departures).
Expected red of "Grace sees the image and the PDF Ada sends": `Ada attaches` stops at
`ChatPage.attach_files` — `get_by_test_id("attach-files")` finds no element (no paperclip input; times out).
Beyond it, in order: `attachment-chip` `data-status="ready"`, `message-attachment-image` /
`message-attachment-file` with `data-file-name`, `message-attachment-download`. It runs in Task 10.

## Departures from the plan

- **`MessageComposer.test.tsx` was not extended; its new tests are `MessageComposer.attachments.test.tsx`.**
  Adding the imports of missing modules made the whole file fail to load, hiding the 7 existing
  composer tests. The seven are unchanged and pass.
- **`messaging/tests/integration/conftest.py`: `TABLES` is unchanged** (no `message_attachments`). Listing a table
  that does not exist made every existing Messaging integration test error at setup. `truncate` runs
  `CASCADE` and `message_attachments` references `messages`, so it is emptied anyway. `tests/bdd` does list it.
- **`MessageItem.test.tsx` not modified.** The plan names it but gives `MessageItem` no new props; rendering is
  proven by `AttachmentList.test.tsx` plus one wiring test in `ChannelView.test.tsx` (extra), which doesn't pin props.
- **`test_plugin.py` modified** (not in the plan): `test_container_fixtures_names_every_root_fixture…` now also
  scans `testkit.garage`, since `garage_server` lives there.
- **Steps moved:** `Grace sees "{body}" in the channel without reloading` and `"{body}" appears in Ada's channel exactly once`
  moved from `test_realtime_steps.py` to `steps/conftest.py` (pytest-bdd cannot see steps in a sibling module).
  `steps/conftest.py` and the edit of `test_realtime_steps.py` are not in the plan's map. The four new phrases are as planned.
- **Tests added** beyond the plan: `test_the_checks_run_in_order`, `test_a_refused_grant_is_not_cached`,
  `test_the_claim_scope_cannot_download`, `test_each_reason_is_reported_against_its_asset`,
  `test_another_workspaces_asset_claims_as_not_found`, `test_confirm_does_not_re_judge_a_failed_asset`,
  `test_an_unknown_asset_reads_the_same_as_someone_elses`, `test_garage_down_is_503_and_changes_nothing`,
  `test_a_send_with_no_attachments_makes_no_claim`, `test_ten_attachments_are_accepted`, a failed-chip Send test,
  a "sends text and files together" test, the PDF-click freshness test, and the ChannelView wiring test.
- **Dropped / reshaped:** none dropped. `test_head_of_a_missing_key_is_none` and the "wrong host" test share the
  `build()` helper rather than the `store` fixture.
- **`ChannelView` R14 test** visits both channels first (`visitBoth`): on a first visit the composer unmounts for
  "Loading…", which hides a mis-kept error — the plan's red ("shown in B") only appears with both cached.

## Picked up from earlier reviews

- *Restore file's load-failure note* (plan-reviewer 2/3): done — the fourth test fails honestly (see above).
- *Whitespace body with attachments* (decision 38): `test_whitespace_passes_as_empty_when_allowed`.
- *`up --wait` with the one-shot bootstrap*, *`URL_STALE_MS` beside the TTL*: not test work; left for the code-writer.

## For the code-writer

Names the tests assume where the plan was silent:
- `S3ObjectStore(endpoint=, public_endpoint=, access_key=, secret_key=, bucket=, presign_ttl_seconds=)`; `asset.migrations.upgrade_to_head`;
  `asset.main.create_app(settings, key_source=…)`; `Asset` model attributes are the migration's column names.
- Asset `Settings`: `redis_cache_url`, `object_store_public_endpoint`; Messaging: `asset_internal_url`, `service_token_url`,
  `messaging_service_client_secret`.
- `contracts.assets`: `ClaimRefusal` (`NOT_FOUND`… values `not-found`, `not-yours`, `not-ready`, `already-attached`), `ClaimRequest`,
  `ClaimResponse`, `AttachmentMeta`, `DownloadUrlRequest`, `DownloadUrlResponse` — pydantic, snake_case attributes,
  camelCase aliases, `populate_by_name=True` (the stub builds them by attribute name and dumps `by_alias`).
- `AssetClient.claim(*, workspace_id, user_id, message_id, asset_ids)`, `.download_url(*, workspace_id, message_id, asset_id)`;
  `ClaimRefusedError.refusals: dict[UUID, ClaimRefusal]`. `refusal_detail` texts are Interfaces' four sentences.
- Messaging sends `attachmentIds` in `send_message` **only when non-empty** (the existing exact-payload tests still hold);
  the 409/503 are Problems with `detail` as planned; `errors.attachmentIds` on the 400s.
- SPA: `add(channelId, chip)`; `AttachmentList({ message, accessToken, workspaceId })`; `useAttachmentUrl(accessToken, workspaceId, messageId, assetId)`;
  `addFiles(channelId, files, getToken: () => string)`; the chip ✕ is a button named `Remove <file name>`, the picker input
  is labelled `Attach files`, the PDF control a button or link named /download/i, the image `alt` is the file name, the retry a
  button named /retry/i with the text "Couldn't load — retry"; images are `max-h-60 max-w-80`; `window.open('', '_blank')`,
  then `opener = null`, then the window's `location` (href, assign, replace or assignment all pass).
- Helpers I added: `test/api.ts` `asset`, `garage`, `GARAGE_URL`, `asset.acceptUploads(script)`; `Recorded.contentType`; `factories.ts`
  `anAttachment`, `aChip`. **The attachment store is reset in each test file**, not in `test/setup.ts` (importing a missing module
  there would fail every test): once `stores/attachments` exists, move `cancelAll()` + `reset()` into `setup.ts`'s `afterEach`.
- Garage `access-control-allow-origin: *` is what a bucket with no CORS rules answers; the bootstrap must set rules for the
  fixture's origin `http://spa.test` (`GARAGE_CORS_ORIGINS`).
- `messaging/tests/unit/conftest.py:39` still builds `Message(attachments=[])` and must drop it with the column (Task 6).

## Half-tests that pin something, and the wrong build each fails

`test_confirm_does_not_re_judge_a_failed_asset`: a confirm that re-HEADs a failed asset. `test_download_url_for_an_asset_not_on_the_message_is_404`:
a Messaging that forwards to Asset instead of using its own snapshot. `…deleted_message_is_404`: a Messaging that trusts Asset (which would mint a URL).
`test_a_send_with_no_attachments_makes_no_claim`: a Messaging that calls Asset on every send. `keeps a URL on screen past 780 s`: default
`refetchOnWindowFocus`. The `cancel` / `reset()` tests: a runner that checks no signal between steps; each has its released-without-cancel twin.
`cleans up the channel the send was for…`: a closure over the hook's `channelId`. `puts the refused send back…while a later send is in flight`:
a per-call `onError`.

## Review responses (round 2, to test-reviewer-1)

1. **Fixed (critical).** `useAttachmentUrl.test.ts`: the two boundary tests now read `dataUpdatedAt` from the query cache after the first fetch (`landedAt()`) and set the clock to that `+ 779_999` / `+ 780_001`, with no `waitFor` between `setSystemTime` and the mount. The header comment no longer claims `vi.waitFor` is clock-neutral. The 781 s tests keep `T0` (margins ≥ 1 s).
2. **Fixed (major).** `xhrPut.test.ts` and `uploads.test.ts` assert only that a non-empty body was PUT (`size > 0`), plus the signed Content-Type and method. The MSW XHR double reports a streamed `File` as ~9 bytes and can't see the real count; a comment says so. A build that sends no body or the wrong type still fails.
3. **Fixed (minor).** The abort test's comment tells the code-writer to reject directly from the signal's abort listener (and call `xhr.abort()`), since `xhr.onabort` never fires under MSW for a held request.

The three files still fail at load (`Failed to resolve import "./useAttachmentUrl"`, `./xhrPut`, `./uploads`), as in round 1. Typecheck on them shows only the missing modules, the missing generated route and the implicit `any`s that follow. The `useAttachmentUrl` fix is reasoned from the reviewer's sketch finding and was not re-run against a build.

## Review responses (round 3, to code-writer-sendback-3)

A1. **Fixed.** `messaging/tests/unit/conftest.py`: dropped `"attachments": []` from `a_message`.
A2. **Fixed.** `test_indexing.py`: every `_as_message(…, reactions=[])` now also passes `attachments=[]`.
A3. **Fixed.** `test_realtime_server.py` passes `assets=None`; `test_read_markers.py` passes `assets=app.state.assets`.
A4. **Fixed.** `asset/tests/unit/test_health.py::_settings` adds `redis_cache_url` and `object_store_public_endpoint`.
B5. **Fixed, with one more cause.** `test_schema.py` selects `contype::text`. That alone did not pass: Postgres prints the key as
   `PRIMARY KEY (message_id, "position")` (`position` is a keyword), so the test strips `"` from definitions before comparing.
B6. **Fixed.** `test_garage.py::test_cors_preflight…`: `preflight` returns `(status, headers)`. The allowed origin gets a status below 300
   and its own `access-control-allow-origin`; the evil origin gets a non-2xx status and a header that is not `http://evil.test`.
   Wrong builds it fails: no CORS rules (first half, header `*` is not `http://spa.test`); allow-all rules (the evil origin gets a 2xx).
C. Optional items left alone (the `setup.ts` reset, stale docstrings). They don't block anything.

**Run:** `uv run pytest` on messaging unit, asset unit, `test_garage.py` and `test_schema.py` gave 173 passed, 1 failed (the
`"position"` quoting, since fixed). After the quote fix Docker began refusing container removal (`read-only file system`), so
`test_schema.py` could not be rerun. That fix is reasoned from the printed constraint set and is **unverified**: rerun
`test_schema.py` first.
