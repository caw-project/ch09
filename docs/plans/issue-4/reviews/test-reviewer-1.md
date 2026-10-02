# Test review — issue 4, round 1: changes_requested

The red is real almost everywhere: 100+ new tests fail at load or setup for the reasons the plan gives, and the
Python, BDD and typecheck claims in the red report match what I ran. But a sketch of a *correct* build found
two tests no correct build can pass: the 780 001 ms freshness test (critical) and the PUT byte-count
assertions (major). Both need a test fix before the code-writer starts, or the code pair will be sent back for them.

## Expectations

Written from the issue, the plan and plan-reviewer-3 before the red report or any test was opened.

**Rules (Asset `test_rules.py`, shared `test_service_tokens.py`, Messaging unit).** Today: `ModuleNotFoundError` for `asset.rules`, `shared.service_tokens`, `messaging.attachments`, `messaging.assets`; `TypeError … allow_empty` for the body tests. Vacuous: size bound pinned one side only (50 MiB passes but 50 MiB+1 not tested, or 0 vs 1); 255/256 chars; allow-list tested only with SVG (a build using `startswith("image/")` passes); `image/png; x=1` is the exact-match probe. `claim_refusal` precedence: each fixture must fail exactly one check, else a reordered build passes. "claimed by this message → None" is the idempotency half. Token cache: clock at `expiresIn-61` vs `-59` (both sides of the 60 s margin); single flight must really overlap (held by Event, two callers started before release). Wrong build: a cache that never expires; a refetch per call; no lock. `refusal_detail`: second-listed refusal first in dict, so dict order ≠ attach order. `visible()` needs a live-row positive beside the tombstone.

**Garage / Asset / Messaging integration.** Today: Asset tests error on `asset.migrations`/`asset.object_store` import; Messaging stub tests error with `contracts.assets` missing; no-stub tests (`eleven_ids`, `duplicate`, `token_endpoint_down`, `invisible_channel`) fail on behaviour (201 / "Not Found"). Vacuous: `404` for download tests with no `detail` assertion (a missing route 404s); claim all-or-nothing that doesn't re-check the ready asset is still unclaimed; the race test run in one order; `test_a_user_token_cannot_claim` passing as a missing-route 404 (must be 401); tenancy tests asserting only 404, not `"No such asset."`. Wrong builds: partial claim; claim without lock; workspace from body trusted for user tokens; message_id not the one the response carries (claim-then-insert order); token fetched per send; deleted message still showing attachments in history OR `message_deleted` payload; asset-down returning 201 with empty attachments. CORS test must have both origins in one test. Garage harness test passes at red by design (plan says so) — that is the only green-by-design test.

**Vitest.** Today: `Failed to resolve import` for new modules (load failure is right only where every test needs the module); modified `useMessages.test.ts` fails on object-as-body; ChannelView R14 fails on shared error. Vacuous: timeline tests under fake timers with `NaN` from missing constants (use literals 779_999/780_001); focus/reconnect refetch test with no positive (780_001 remount does request); `cancel` held-step tests with no positive release; restore tests keyed on hook channel not `variables.channelId` (needs re-render to B mid-send); paste uses `user.paste` on focused box. Wrong builds: refetch on focus; closure over hook channelId; restore overwriting draft; batch partial attach (10 + 1 attaches the first); failed chip not counting; send enabled with an uploading chip; chips in wrong order in `attachmentIds`.

**BDD.** `--collect-only` parses; `--generate-missing` lists exactly the four new steps and no more (reused phrases verbatim, `@bdd` on the Feature line only); selectors only in page objects; last Then reused (reload/server-side, once). Existing step files changed in the tree (`steps/conftest.py`, `test_realtime_steps.py`) are suspect: the plan names only `conftest.py` (bdd), `chat_page.py` and the new steps — any other edit is a file-map departure to check.

**Existing tests.** `test_images.py`/`test_plugin.py` (testkit) modified — plan names only `test_images.py`; `test_plugin.py` is a departure to check for weakened assertions. `test_schema.py`, `test_message_body.py` and `useMessages.test.ts` edits must not loosen any baseline assertion.

## What ran

- `uv run pytest` over the four new Python unit files: all four fail at collection — `asset.models` (before `asset.rules`),
  `shared.service_tokens`, `messaging.assets`, `contracts.assets` missing. Every test in each file needs the missing module, so
  nothing is hidden. `test_message_body.py`: the four new tests fail with the `allow_empty` TypeError (per the report; not re-run in isolation).
- `uv run pytest src/services/testkit/tests/integration/test_garage.py`: 1 passed (harness, green by design), 1 failed
  `assert '*' == 'http://spa.test'` — as the report says; the plan's "no header" expectation was wrong (Garage answers `*` with no rules).
- `uv run pytest …/messaging/tests/integration/test_attachments.py test_schema.py`: 6 failed, 13 passed, 20 errors. The 20 errors are the
  `asset_stub` setup (`contracts.assets`); the failures are `eleven_ids`, `duplicate_id`, `token_endpoint_down`, `invisible_channel`
  (404, no `detail`) and the two schema tests. Matches the report. Asset's integration directory not run (every file needs a missing module; read only).
- `npm --prefix src/frontend test`: 11 files failed, 4 tests failed, 241 passed. Nine files fail to load on missing modules; the four
  failures are the two reworked `useMessages` tests and the two `ChannelView` tests. Matches the report.
- `npm --prefix src/frontend run typecheck`: 41 errors, all missing module / missing generated type / `any` from an unresolved import, in test files
  and `test/api.ts`, `test/factories.ts`. Matches *Types*.
- `uv run pytest tests/bdd --collect-only -q`: 21 collected; `--generate-missing`: no stub printed.
- **Sketches** (`.claude/delivery/sketch.sh frontend`, since cleaned):
  - Correct: `stores/attachments`, `rules`, `uploads`, `xhrPut`, `useAttachmentUrl` (staleTime 780 000), and `useSendMessage` with variables
    keyed on `variables.channelId`, hook-level `onError` restore, `sendErrors`. Results: `rules`, `stores/attachments`, `uploads` (bar the body size),
    `useSendMessage.restore` and `useMessages` all green. **`useAttachmentUrl.test.ts` "requests a fresh URL first when a mount finds it stale" red** (Finding 1).
    **`xhrPut.test.ts` "sends the signed Content-Type and the bytes" and `uploads.test.ts` "runs a file through…" red** with `{ size: 9 }` (Finding 2).
    **`xhrPut.test.ts` "rejects when aborted" timed out** with `xhr.abort()` and the `abort` event (Finding 3).
  - Wrong build, cache writes in `onError` keyed on the hook's `channelId`: `restore` "cleans up the channel the send was for" fails, as designed.
  - Wrong build, `cancel`/`cancelAll` do nothing: the `cancel` held-step tests fail, as designed.
  - Probe: `vi.useFakeTimers({ toFake: ['Date'] })` then `vi.waitFor` retrying four times moved `Date.now()` by exactly 200 ms.
- Not sketched (read only): `AttachmentList`, `MessageComposer.attachments`, `ChatLayout.attachments`, `ChannelView`, and every Python rule. The Python
  rules are pure and each wrong build I could name is caught on the page; the components need the whole feature built to run.

## Coverage

| Plan test or expectation | Test as written | Outcome |
|---|---|---|
| Task 1 rules, token source, Messaging rules, client mapping, body | `test_rules.py`, `test_service_tokens.py`, `test_attachments.py`, `test_asset_client.py`, `test_message_body.py` | present (extra: order-of-checks, refused-grant-not-cached) |
| Task 2 Garage, object store, uploads, internal, Messaging seam, schema | `test_garage.py`, `test_object_store.py`, `test_uploads.py`, `test_internal.py`, `test_attachments.py`, `test_schema.py` | present; claim race in both orders; every guard has its positive |
| Task 3 rules, xhr, uploads, store, composer, paste, restore, layout, list, url | the ten SPA files | present; xhr and url have Findings 1–3 |
| `MessageComposer.test.tsx` extended; `MessageItem.test.tsx` modified | `MessageComposer.attachments.test.tsx`; `ChannelView.test.tsx` wiring test | departed, with reason; accepted |
| Task 4 journey and harness | `attachments.feature`, `test_attachment_steps.py`, `chat_page.py`, bdd `conftest.py` | present; four new phrases, rest reused |
| Expectation: boundary pinned both sides, each input alone | rules/uploads/composer | met, except Finding 1's boundary, which cannot be met as written |

## Findings

### 1. The "780 001 ms" remount test cannot pass with a correct staleTime — critical
**Where:** `useAttachmentUrl.test.ts`, "requests a fresh URL first when a mount finds it stale, and shows none until it lands" · **Checked:** sketch plus probe.
The file fakes only `Date` and its header says "`vi.waitFor` is safe here (no retry moves the fake clock)". That is wrong:
`vi.waitFor` calls `advanceTimersByTime` whenever any fake timer is installed, and a probe moved `Date.now()` by 200 ms over four retries. The first
mount's `waitFor` therefore lets the clock run 50–150 ms before the data lands, so `dataUpdatedAt` is T0+50k, not T0. The test then sets the time to
T0+780 001, which is only about 779 9xx ms after the data was fetched: inside 780 000, so *not* stale, and the hook correctly keeps the URL.
With a correct `staleTime: 780_000` the sketch fails at `expect(url).toBeNull()` (got `get/1`). Setting the sketch to `779_800` makes this test pass and the
779 999 ms test fail: the pair can only both pass for a value around 779 9xx, so the file pins a wrong constant and fails the right one. The same drift
means the 779 999 side proves nothing about the boundary. The code-writer cannot fix this; they would "fix" it by detuning the constant.
**Fix:** stop relying on the clock at landing: either seed the cache with a known `updatedAt` (`queryClient.setQueryData(key, url, { updatedAt: T0 })`)
for the stale-mount cases, or fetch under real `Date` and read `queryClient.getQueryState(key).dataUpdatedAt`, then set the two times to `+779_999` and
`+780_001` from *that*. Don't `vi.waitFor` between `setSystemTime` and the mount. Fix the header comment. The other `Date`-faking tests
(`AttachmentList.test.tsx` "fresh on click", the 781 s cases) have margins of 1 000 s or ≥ 1 s past the boundary, which survive the drift.

### 2. A natural `xhr.send(file)` cannot pass the PUT byte-count assertions — major
**Where:** `xhrPut.test.ts` "sends the signed Content-Type and the bytes…" (`body toEqual({ size: 2048 })`) and `uploads.test.ts` "runs a file through upload-url…" (`{ size: 100 }`) · **Checked:** sketch.
Under MSW's XHR interceptor in jsdom, `xhr.send(file)` and `xhr.send(file.slice())` reach `record()` as a 9-byte body (`"[object File]"`): `{ size: 9 }` in both tests.
Only `xhr.send(await file.arrayBuffer())` gave the real size, and the sketch passed both tests with it. So a correct, streaming `putFile` fails two tests, and the one build that passes reads a 50 MB
file into memory to satisfy a fake. That is a test over-pinning the double, and the code pair would hit it as a red they can't explain.
**Fix:** drop the byte count, or make `record()` count what it can (the `content-length` header, if the interceptor sets one) and assert only "a non-empty body was sent
with the signed type". The signed Content-Type and the method stay asserted. Say in the report what the double can't see.

### 3. The abort test needs the promise rejected from the signal listener — minor
**Where:** `xhrPut.test.ts` "rejects when aborted…" · **Checked:** sketch.
With `signal.addEventListener('abort', () => xhr.abort())` and rejection from `xhr.onabort`, the held request never fires `abort` under MSW and the test
times out. It passes once `putFile` rejects directly in the signal listener, which is sound code anyway. Add a line to the test comment so the code-writer
doesn't lose a pass finding out; no change to the assertions is needed.

## Left for later stages

- **Code-writer, minor:** `useSendMessage` must send `attachmentIds` only when non-empty (the baseline exact-payload tests at `useMessages.test.ts:141` hold only then); the report already says so.
  Move `cancelAll()` + `reset()` into `test/setup.ts`'s `afterEach` once the store exists, as the report asks.
- **Code-writer, minor:** the composer tests name controls `Attach files`, `Remove <file name>`, a button or link `/download/i`, and expect the
  `max-h-60 max-w-80` classes; the plan fixes only the last (decision 31). Listed in the report's *For the code-writer*.
- **Code-writer, minor, from plan-reviewer 3:** `up --build --wait` with the one-shot bootstrap; `URL_STALE_MS` beside the TTL.
- **Minor:** the Asset and testkit integration tests assume `asset.main.create_app(settings, key_source=…)` and `S3ObjectStore(...)` as named in the report.
- Accepted departures: `MessageComposer.attachments.test.tsx` as a separate file; `TABLES` not listing `message_attachments` (truncate is `CASCADE`); steps moved to `steps/conftest.py`
  (pure moves, verified in the diff); `test_plugin.py` widened to scan `testkit.garage` (a strengthening); the CORS red message.

## Checked and sound

- Every Python integration guard has its positive: all-or-nothing claim re-checks the ready asset is still claimable; the claim race runs in both orders; the 401/403 tests assert the
  status of a route that exists; tenancy 404s assert `detail`; `asset-not-on-message` and `deleted-message` stub a URL Asset *would* mint, so only Messaging's own check passes them.
- Order of attachments is pinned by a ten-id test (an id-sorted build passes with probability 1/10!).
- Token source: −61 s cached and −59 s refetched pins both sides of the margin; single flight is held on an `Event` with two tasks started first.
- `restore.test`: a closure-over-hook-channel build fails; the correct sketch passes all six, plus the reworked `useMessages` tests. A per-call-`onError` build is not exercised by these tests (they call `mutate` bare) but cannot pass test 1, which needs the hook-level restore.
- `uploads.test`: whole-batch refusal, ten accepted, failed chip counts and removing it makes room, per-channel counts, upload finishing into its own channel, each cancel/reset test with its twin.
- BDD: four new steps, reused phrases verbatim, `@bdd` on the Feature line, selectors only in `chat_page.py`, `naturalWidth > 0` and bytes compared with what the scenario built.
- Existing tests: no assertion removed or loosened; the reworked `useMessages` expectations are exactly the plan's.
