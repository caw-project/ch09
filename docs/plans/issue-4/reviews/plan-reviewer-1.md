# Plan review — issue 4, round 1: changes_requested

The design is sound and well argued: every requirement is mapped, the hard calls (claim in Asset,
download through Messaging, hook-level `onError`, the popup opened synchronously) are decision rows,
and the library claims I checked hold. It goes back for ten major findings, none of them a redesign.
Four are expected reds the runtime wouldn't produce, tests green at red, or a test with no client. The rest are R11's
"nothing refetches" clause, the restore and chip-store races, a missing socket fixture, one ripple
file, and the stale worktree `.env` the e2e run would read.

## Expectations

Written from the issue, docs 00/02/04/06, the register (D13–D16, D25, D34) and the code, before
the plan was opened.

### Decisions any plan must make

- **E1 Asset status vs claim.** The claim needs a "claimed by message X" fact on the asset. A
  column on `assets` (`message_id`) or a separate claim table? Is "claimed" a status
  (`ready`→`attached`) or a column beside `ready`? Does the claim check workspace from the
  request body (Messaging passes the caller's `wsp` and `sub`) — and how is that not CH001
  (tenancy id from the request)? The internal route has no `wsp` claim, so the workspace *must*
  come from the body: who is trusted to send it?
- **E2 Claim atomicity.** One request claiming N assets: all-or-nothing in one transaction? What
  locks the rows (`SELECT … FOR UPDATE`, conditional `UPDATE … WHERE message_id IS NULL`)?
  Idempotent for the same `(assetId, messageId)` — what is returned on a repeat?
- **E3 Claim refusal shape.** Which status codes for not-ready / other workspace / other
  uploader / already claimed / unknown id? Does Messaging map an asset in another workspace or
  unknown to the same refusal (no probing)? What does the SPA show for each? What is "Asset
  unreachable" — connection error only, or also 5xx and timeout? Timeout value?
- **E4 Order of operations in send.** Validate body/attachment count → visibility → claim →
  insert? Is the visibility check done before the claim (so a send to an invisible channel
  doesn't claim assets)? Is the empty-body rule changed only when `attachmentIds` is non-empty,
  and does whitespace-only body with attachments count as empty?
- **E5 Duplicates in `attachmentIds`.** The same id twice in one send: refused, or deduplicated?
  Over 10 at the server: which error, which key?
- **E6 "In the order attached."** Order = the order of `attachmentIds` in the request? Stored by
  position in the new table — what is the PK, and is position 0- or 1-based?
- **E7 Service token client.** Where it lives (shared?), cache-until-near-expiry margin,
  single-flight under concurrent sends, what happens when Auth is down (503 like Asset down?).
  Which scope names, and does Auth's client registration config change (Auth's config is in
  "Services touched")?
- **E8 Download URL route.** Visibility first, then message deleted, then asset-on-message —
  all three 404 with the same body? Does Messaging call Asset with the asset id only, or the
  workspace too? Does Asset re-check anything (status ready, workspace)? Content-Disposition
  for PDF `attachment` — and for images: `inline`, or none? File name in the disposition —
  encoding of non-ASCII and quotes (RFC 6266 `filename*`)?
- **E9 "Stale at 780 s".** Is the TTL/staleness carried by the response (`expiresAt`) or a client
  constant? Is the URL cached in TanStack Query (staleTime 780 s) keyed by workspace, message,
  asset? "Not stale on click" — how is a click that opens a new tab done after an async refetch
  without a popup blocker (window.open after await is blocked)?
- **E10 `<img>` refetch once then placeholder.** Per mount or per URL? Does "retry" refetch and
  reset the once-counter?
- **E11 Paste rule.** "has `text/plain`" — `clipboardData.types.includes('text/plain')`? Paste of
  non-image files (allowed: PDF)? The name format `yyyy-mm-dd hh.mm.ss` — 24-hour? Two pastes in
  the same second → same name — acceptable?
- **E12 The batch message.** "3 attached, 12 added" — "attached" counts chips already there
  including failed ones; "added" is the batch size. Rejected-type files in the same batch: is
  the whole batch refused, or only the bad file? (R2 says "says which rule refused" — per file
  or per batch?)
- **E13 Draft model.** Where pending chips live: Zustand (client state) — but chips hold an
  upload in progress (XHR) whose lifetime outlasts the composer mount. Who owns the XHR? A
  module-level registry keyed by channel? Workspace switch clears it — and aborts the XHRs?
  Sign-out clears? Draft keyed by channel only, or workspace+channel?
- **E14 R13 restore.** Restore in the mutation's own `onError` (hook-level, not per-call), keyed
  by the send's own channelId. Restore when the composer already has new text/chips — merge,
  overwrite, or append? Restored chips are `ready` assets (already claimed, if the send actually
  succeeded) — the timeline says the retry is refused: what does the composer show then?
- **E15 R14 error per channel.** Keying the composer by channel (like `MessageList`) — does
  that drop the in-flight mutation's state, and does that break R13 (the error then belongs to
  an unmounted composer)? Where is the error held — Zustand per channel?
- **E16 Timeout wording.** The existing message "Nothing was sent." becomes the new wording —
  any test currently pinning the old text?
- **E17 Remove ✕ on an uploading chip.** Aborts the XHR? On a `ready` chip — the asset stays
  pending/ready unclaimed (no DELETE route; accepted under D16)?
- **E18 Inline size cap** and how a PDF chip shows size (units, rounding).
- **E19 DTO shape** `attachments: [{assetId, fileName, contentType, sizeBytes}]` — a breaking
  change from `list[UUID]`; the generated types and every factory/test using `attachments: []`.
- **E20 Garage public endpoint.** One boto3 client per endpoint; settings names; how the k3d
  `s3.<host>` Ingress is added (which chart — deps owns Garage); does it go on the app chart's
  allow-list template or the deps chart? Compose: `localhost:3900` published — conflicts with the
  test stack's port republishing (`docker-compose.test.yml` publishes only five ports today; the
  BDD browser must reach Garage, so a sixth port).
- **E21 Bootstrap.** Compose has none today — a one-shot service? Reuse
  `garage-bootstrap.py`? CORS via admin `UpdateBucket corsRules`. Does the test stack's
  `APP_ORIGIN` (5183) differ from dev's — each needs its own CORS origin.

### Conflicts to name

- **C1** R10 "Asset's public routes are upload-url and confirm only" (Decided 3) vs doc 04 §3
  listing `GET /assets/{id}`, `download-url` etc. as public — the doc must be corrected.
- **C2** Decided 4 key `{workspaceId}/attachment/{assetId}` vs doc 04 §4/§4.1
  `{workspace}/{purpose}/{assetId}/{fileName}`.
- **C3** Doc 04 §5 step 4 / §4.2 enqueue `jobs:thumbnail` on confirm vs *Not in this issue*
  (thumbnails) — confirm must not enqueue.
- **C4** Doc 06 §8 "do not pre-check limits client-side … attachment count and size stay as
  written" + R2 SPA pre-check: consistent, but the composer's "server owns the rules" comment
  must be squared with the duplicate limit constants — where do the SPA's limits come from?
- **C5** Doc 02 §3.1.3 "body must not be empty" vs R6 empty body allowed with an attachment.
- **C6** Register D15 🔴 vs Decided 2 closing it — the plan must update the register, not build
  on a 🔴. D13 🔴 vs "one bucket" — the plan must not decide D13.
- **C7** R12 "an edit never changes attachments" vs the edit route: does `EditMessageRequest`
  reject `attachmentIds`, or ignore extra keys (CamelRequest ignores)?
- **C8** R8 "the sender sees it once" + "The response and the echo" vs the optimistic row —
  the `temp:` row must carry attachments (from the chips) or render none until reconciled.
- **C9** R15 "a reload loses them" vs R13 restoring chips into a draft that persists in Zustand
  only — consistent, but check nothing persists drafts.
- **C10** "Asset down while viewing: chips render from stored metadata" vs R11's per-message URL
  fetch: a failing download-url must not replace the message list with an error view.

### Tests that must exist

- Unit (pure): limits (each rule alone, both sides: 0/1 byte, 50 MB / 50 MB+1, 255/256 chars,
  each content type and one refused e.g. `image/svg+xml`); confirm size check (equal / ±1);
  claim decision (each of four conditions flipped alone, plus idempotent repeat); object key;
  Content-Disposition (PDF attachment, image, a name with quotes / non-ASCII); paste naming
  (fixed clock, local time — test the TZ isn't UTC); batch count (9+1 ok, 9+2 refused, with a
  failed chip counted, removing makes room).
- Integration (Asset, real Garage): presign PUT works; a PUT with a different Content-Type is
  refused (signed header); confirm HEAD size mismatch → failed; GET with
  `response-content-disposition`; CORS preflight from `APP_ORIGIN` allowed and another origin
  refused; internal claim (all four refusals, all-or-nothing, idempotent, concurrent claim of
  the same asset by two messages → one wins); internal download-url; workspace from claim on
  public routes.
- Integration (Messaging, Asset stubbed with contracts models): send with attachments over REST
  and socket; refused claim → no message row; Asset unreachable → 503, no row; tombstone
  `attachments: []` on DELETE, history and `message_deleted`; edit leaves attachments; history
  order; download-url 404 ×3 with the same detail, and positive case; migration drops the column.
- Vitest: upload helper progress / failure; chips and Send enabled only when all ready; paste
  with/without text/plain; drop; R4 message; R13 with two sends in flight in different channels;
  R14 error stays in channel; R15 switch and back; workspace switch clears; image refetch once
  then retry; stale URL refetched on click and on remount (fake time 779/781 s).
- BDD: the one journey, ending with Grace's view and the download bytes compared.

### Risks

- **R-a** TanStack v5 per-call `onError` only for the latest `mutate` (the issue says so) — the
  plan must move restore to hook level or a per-call closure that doesn't depend on it.
- **R-b** Window.open after an await is popup-blocked — "fresh on click" can't open a new tab
  after an async fetch without a pre-opened window or a link with a fresh href.
- **R-c** Race: claim succeeds, insert fails → assets claimed to no message (accepted); claim
  for a message id whose insert later succeeds on retry? Messaging chooses a new id per send,
  so a retry is refused — the issue accepts.
- **R-d** Two concurrent sends with the same asset ids (double click, two tabs) — the claim's
  row locking must make one lose.
- **R-e** Per-message download-url fetch on render: a channel with 50 image messages = 50 calls
  to Messaging → 50 internal calls to Asset → each needs the service token: single-flight token
  fetch, and the load on Asset per history page.
- **R-f** Service-token cache: tokens fetched concurrently at startup (stampede); token expiry
  mid-request; Auth down.
- **R-g** Garage CORS only on success (issue assumption) — XHR `onerror` path is the only
  failure signal; the plan must not rely on reading a status.
- **R-h** Signed host: presigning with the public endpoint from inside the container; the test
  stack's public endpoint must be reachable from the Playwright browser (host port) *and*
  Asset's HEAD must use the internal one.
- **R-i** Library behaviour to verify in installed source: boto3 `generate_presigned_url` with
  `ContentType` in Params signs it; Garage `response-content-disposition`; TanStack per-call
  `onError`; MSW's handling of an XHR PUT with progress events in jsdom (does jsdom's XHR emit
  `upload.onprogress`?).
- **R-j** The `uuid[]` drop is a data-dropping migration — the column is always `[]`, so
  harmless, but downgrade must be stated.
- **R-k** BDD truncation must include Asset's tables and the new Messaging table; the harness
  must probe Asset readiness.
- **R-l** Issues 2 and 3 share files; issue 2 has landed on main (`02e1c03`) — the plan's base
  must include it.

## Coverage

| Issue item or expectation | Plan | Outcome |
|---|---|---|
| R1 handshake, `attachment` only | Tasks 1, 2 (`test_uploads.py`), 5 | covered |
| R2 limits, SPA first, server at upload-url, size equal at confirm | Task 1 (both sides of each bound), `rules.test.ts`, `confirm_outcome` | covered; 50 MB = MiB is a correction row (4) |
| R3 picker, drop, paste; text/plain wins; paste name | Task 3 composer + `rules.test.ts`; decision 27 (assumed) | covered, but see F3 (paste-with-text green at red) |
| R4 all of a batch or none, exact sentence | `batchRefusal`, `uploads.test.ts` | covered |
| R5 chips: name, progress, ✕, reason; Send only when all ready | composer tests; decision 28 | covered; ✕ while uploading → F7 |
| R6 `attachmentIds` on both transports, empty body allowed | Tasks 1, 2, 6 | covered (whitespace-only with attachments: minor, below) |
| R7 strict claim, four conditions, 503 | `claim_refusal`, `test_internal.py`, seam tests; decisions 9, 11, 12 | covered |
| R8 attachments on REST, history, `message_received`, in order, seen once | socket and REST tests, journey | covered |
| R9 inline capped, new tab; PDF chip | `AttachmentList.test.tsx`, decisions 29, 31 | covered |
| R10 downloads through Messaging, three 404s, PDF `attachment` | Tasks 1, 2, 6; decision 13 | covered |
| R11 fresh on click; stale refetched first; `<img>` refetch once | `useAttachmentUrl.test.ts` | **misread** — the timeline's "t=780s nothing refetches; A stays on screen" (F5) |
| R12 tombstone `[]`, edit keeps | `visible()`, `test_a_deleted_message_shows_no_attachments`, `test_an_edit_keeps_the_attachments` | covered |
| R13 restore to its own channel with a later send in flight; timeout wording | hook-level `onError`, verified in TanStack source | covered for the empty draft; **missing** for a non-empty one (F6) |
| R14 errors stay in their channel | `sendErrors`, keyed composer, `ChannelView.test.tsx` | covered; clearing unsettled (F6) |
| R15 uploads survive switch; reload/sign-out lose; workspace switch clears | `uploads.ts` outside React, `ChatLayout` | covered; races in F7 |
| R16 public endpoint, CORS, bootstrap ×3, k3d `s3.` host | decisions 22–24, Task 7 | covered; testkit S3 check in F4 |
| Decided 1–7 | decision rows 1–7 | all covered |
| Tests: unit pure, Garage integration, seam via `contracts`, Vitest + `asset.json`, `record()`, one journey + harness | Test approach, Tasks 1–4 | covered; red reasons in F1–F3 |
| Record: docs 02/04/06, D15, D43, notes, ADR, env/Compose/charts | Tasks 7, 9 | covered (doc 04 §4.2/§5 thumbnail step: minor) |
| *Not in this issue* | *Not in this plan* | covered; confirm enqueues nothing |
| E1/E2 claim column, lock, idempotency | decision 9, `FOR UPDATE` in id order, both-orders race test | settled |
| E3 refusal codes and 503 | decisions 11, 12; 3 s timeout | settled |
| E4 order: visibility → validate → claim → insert | Task 6 | settled |
| E5 duplicates | decision 26 (assumed) | settled |
| E6 order | position 0-based, PK (message, position) | settled |
| E7 token client | decisions 20, 21 | settled |
| E8 download route, disposition, encoding | decision 13, `content_disposition` with `filename*` | settled |
| E9 staleness, popup blocker | `URL_STALE_MS`, decision 29 | settled (constant vs configurable TTL: minor) |
| E10 one refetch, then retry | `AttachmentList.test.tsx` | settled |
| E11 paste rule | decision 27 | settled |
| E12 per-file refusal inside a batch | decision 28 | settled |
| E13 who owns the XHR, workspace switch | `uploads.ts`, `cancelAll` + `reset` | settled |
| E14 restore into a non-empty composer | — | **missing** (F6) |
| E15 keyed composer vs in-flight mutation | hook-level options run without an observer (`mutation.ts:288`) | settled |
| E16 old timeout text pinned | `useMessages.test.ts:204` named | settled |
| E17 ✕ on an uploading chip | `cancel(localId)` exists, never tested from ✕ | **missing** (F7) |
| E18 inline cap | decision 31 | settled |
| E19 DTO ripple | Task 6, factories | settled |
| E20/E21 endpoints, ports, bootstrap, per-stack CORS origin | decisions 22–24, corrections 1–2 | settled |
| C1 doc 04's public GET routes | Task 9 says they're not built | settled |
| C2 key layout | correction 3 | settled |
| C3 thumbnail enqueue on confirm vs *Not in this issue* | not enqueued; doc 04 §4.2/§5 not named in Task 9 | settled (minor) |
| C4 doc 06 §8 vs SPA limits | the doc already keeps count and size client-side | settled |
| C5 empty body | decision 12, doc 02 in Task 9 | settled |
| C6 D15 🔴 vs Decided 2; D13 | decisions 2, 6, 32 | settled |
| C7 edit with `attachmentIds` | extra keys ignored; test that the edit keeps them | settled |
| C8 optimistic row | decision 30 | settled |
| C10 Asset down while viewing | per-image retry | settled |
| R-a…R-l | see F5–F10 for the open ones | mostly settled |

## Findings

### 1. Messaging's seam tests can't produce the reds the plan gives — major
**Where:** Task 2, the `asset_stub` fixture and the `messaging test_attachments.py` rows · **Checked:**
the file map puts `contracts/contracts/assets.py` in Task 5 (GREEN); the fixture "serves a FastAPI
app from `contracts.assets`".
At red, `contracts.assets` doesn't exist, so every test that requests `asset_stub` errors in setup
with `ModuleNotFoundError: No module named 'contracts.assets'`. It never reaches the "201 with
`attachments == []`", "201 (ignored)" or "stub records nothing" the table promises. The
test-reviewer will either reject correct tests or wave through a fixture error. Settle it one way:
move the contract module into RED (it is the seam both sides test against, as the issue's Tests
section says), or restate those reds as the fixture's import error. Either way, keep the tests that
need no stub (schema, the invisible-channel 404, the empty body without attachments) out of the
fixture's reach, so they still show their own reds.

### 2. Two existing Vitest files fail to load at red, and their stated reds are wrong — major
**Where:** Task 3, the `useMessages.test.ts` and `ChatLayout.test.tsx` rows · **Checked:**
`ChatLayout.test.tsx:10-20` and `useMessages.test.ts` imports; `stores/attachments.ts` doesn't exist
(Task 8 creates it).
To check "text and chips return" and "a workspace switch empties every channel's chips", these tests
have to read `useAttachmentStore`. A static import of a missing module is `Failed to resolve import`
for the whole file. That takes down the 2 existing ChatLayout tests and every existing
`useMessages` test, which the shared context's *Read the failure* forbids. The plan gives "chips
survive" and "restore lands nowhere" as the reds. Say where these tests live (a new file, or an
import that loads), and what each one really fails with. Also say what happens to the existing
`mutate('text')` calls at `useMessages.test.ts:134-214` at red. Rewritten to
`{channelId, body, attachments}`, they hand the old hook an object as `body` and fail for that
reason. Left alone, they break at GREEN. The plan names them as ripple but gives neither a task
nor a red.

### 3. Two guard tests are green at red — major
**Where:** Task 2, `test_cors_preflight_refuses_another_origin`; Task 3, the composer's "a paste with
text pastes the text and attaches nothing" · **Checked:** the plan itself says the first "passes at
red"; at red the composer has no paste handler, so its default is never prevented and nothing is
attached.
Both prove nothing at the gate. *Tests that prove something*: a guard proves its positive **in the
same test**. "Only counts once the first is green" is not something a gate can check. Fold the
allowed origin into the refusal test, and pair the text paste with a file-only paste in one test.
Or say how each fails at red. The composer row's red ("no paperclip control") doesn't apply to the
paste test.

### 4. testkit's "bootstrap serves S3" check has no S3 client — major
**Where:** Task 2, `test_garage.py::test_the_bootstrap_serves_s3` ("put and get an object with the
key", "passes at red") · **Checked:** `uv.lock` has no `boto3`/`botocore`;
`testkit/pyproject.toml:6-26` has no S3 client; the file map adds `boto3` to `asset/pyproject.toml`
in Task 5 only.
A signed PUT and GET need SigV4. As planned the test can't pass at red, and testkit would have to
import `asset` to sign. Say which client it uses (boto3 as a testkit dependency, added in RED) and
add that file to the map, or reduce the check to something unsigned (an anonymous request answered
403 rather than refused, proving S3 is served).

### 5. R11's "nothing refetches" is contradicted by the query defaults and untested — major
**Where:** Task 3 `useAttachmentUrl` interface ("`url` only while fresh") and its tests · **Checked:**
`main.tsx:15-28` sets no `refetchOnWindowFocus`, so TanStack's default `true` applies (only
`useChannels.ts:48` turns it off); the issue's timeline: "t=780s URL stale; nothing refetches; A
stays on screen".
A stale URL query refetches on every window focus and reconnect, which swaps every visible image's
`src`. With 50 images on a page that is 50 Messaging→Asset round trips per focus. And "`url` only
while fresh" reads as an image that blanks on its next re-render after 780 s. The tests cover only
remounts at 779 999 / 780 001 ms. Settle in the plan that a mounted image keeps its URL past
staleness (no focus, reconnect or interval refetch). Add a test at about 781 s: a re-render and a
focus event leave the `src` alone and request nothing.

### 6. R13 restore into a composer that isn't empty is unsettled — major
**Where:** Task 3 `useSendMessage` / `restore(channelId, chips)`; Task 8 · **Checked:**
`MessageComposer.tsx:71-80` (today `setDraft` overwrites); `mutationObserver.ts:85-93` (a pending
mutation takes the observer's new options on re-render).
R13 says the restore happens "even when a later send is in flight", and R15 has chips accumulating
meanwhile. So when the refusal lands, the channel's composer may hold new text and new chips. Does
the restore overwrite the text or join it? Replace the chips, which orphans their in-flight
uploads, or append them, which can pass 10? The test-writer will otherwise choose silently in a
test. Also settle when `sendErrors[channelId]` clears (today `send.error` resets on the next
`mutate`). And say that every cache write in the hook (remove the `temp:` row, upsert) keys on
`variables.channelId`, not the hook's `channelId`. The keyed composer makes that true in the app
today, but a `renderHook` re-rendered with another channel would move the pending mutation's
options (`:91-92`) and leave a `temp:` row behind. An assumed row each is enough.

### 7. Late writes to the chip store have no answer — major
**Where:** Task 3 `stores/attachments.ts`, `uploads.ts` · **Checked:** the interfaces have `update`,
`remove`, `cancel`, `reset`; no test touches the orderings below.
`uploads.ts` runs three awaited steps outside React. A ✕ or a workspace `reset()` can land between
any two of them: after upload-url resolves but before the PUT starts, or with confirm in flight. The
plan doesn't say that `update` of a missing `localId` is a no-op, which stops a removed chip coming
back as `ready`. Nor does it say that `cancel` stops the steps after it, not only the XHR, or that
✕ on an uploading chip calls `cancel`. Settle it, and add a test with a held confirm (or a held
upload-url) and a ✕ or `reset()` before it resolves: the chip stays gone and nothing more is
requested.

### 8. The socket tests have no way to reach the Asset stub — major
**Where:** Task 2 fixtures; `test_socket_send_acks_attachments_and_broadcasts_them`, the socket half
of `test_asset_down_is_503…` · **Checked:** `messaging/tests/integration/conftest.py:114-123`
builds `realtime_url` from `app_settings`, which has no override; `client_for` (`:87-111`) is REST
only.
As described, the socket server can't be pointed at `asset_stub`, so these tests can't be built
against the fixtures the plan dictates. Name the fixture (a `realtime_url_for(**overrides)`, or the
stub's URLs folded into `app_settings` for this file).

### 9. `realtime.py` is listed as unchanged but must change — major
**Where:** File map, "Deliberately unchanged: `realtime.py`"; Task 6 "passes them into
`RealtimeContext`" · **Checked:** `RealtimeContext` is defined at `realtime.py:103-115` (fields
`settings, sessions, security, jobs`) and built at `main.py:152-157`.
The socket send needs the `AssetClient`, so `RealtimeContext` gains a field. Add `realtime.py` to the
map and drop it from the unchanged list.

### 10. The e2e run would read the worktree's stale `.env` — major
**Where:** Task 10 · **Checked:** `.env` exists in the worktree; `scripts/deliver.sh:231` copies it
from `.env.example` only when it is missing, so it holds today's values; Compose reads it
(`docker-compose.yml:16`); `scripts/test.sh:280`.
Task 10 runs `scripts/test.sh e2e` before "`cp .env.example .env` changes first", which comes with
the later manual run. The test stack would start with `OBJECT_STORE_ACCESS_KEY=collabhub-local` (the
bootstrap can't import it, as correction 2 says), no Messaging service client, and no
`GARAGE_CORS_ORIGINS`. The journey would fail for a reason that is not the code. Make refreshing
`.env` from the new `.env.example` the first step of Task 10.

## Left for later stages

- **Minor — new step count.** Task 4 says `--generate-missing` lists "exactly the five new steps",
  but `"{body}" appears in Ada's channel exactly once` is reused (`test_realtime_steps.py:77`). Four
  are new.
- **Minor — correction 1 is not a correction.** The issue described today's test stack accurately.
  Publishing two more ports makes CLAUDE.md's "republishes only the five ports" and
  `tests/bdd/conftest.py`'s docstrings stale. Add them, `docker/garage/garage.toml:4-6` ("one-off
  manual step") and `messaging/README.md:111` to Task 9's sweep.
- **Minor — whitespace-only body with attachments.** `allow_empty=bool(attachments)`. Whether
  `"   "` plus a file is accepted, and stored verbatim, isn't said. Either answer is fine; the
  code-writer should record it.
- **Minor — staleness is a constant, the TTL a setting.** `URL_STALE_MS = 780_000` and
  `OBJECT_STORE_PRESIGN_TTL_SECONDS` can drift. Deriving staleness from `expiresAt` minus 120 s
  would follow the setting.
- **Minor — doc 04 §4.2/§5** still say confirm enqueues `jobs:thumbnail`. Task 9 should say that
  step is not built.
- **Minor — CH001 on the internal routes.** `workspaceId` and `userId` come from the body by design,
  so expect the conventions checker to need a waiver there, with that reason.
- **Minor, unverified — `up --wait` with a one-shot service.** `scripts/test.sh e2e` runs
  `up --build --wait`, and `garage-bootstrap` exits. I haven't confirmed that the installed Compose
  treats an exit 0 behind `service_completed_successfully` as ready. Task 10 will show it.
- **Minor — siblings.** Issue 2 is already in the base (`02e1c03`). Only issue 3 can still land.
- **Minor — vocabulary.** The four new phrases should be added to
  `docs/plans/ch06/gherkin/00-scenario-vocabulary.md`.

## Checked and sound

- Base `950e66a` matches `git log -1`; no unmerged sibling branches (`git branch --no-merged main` is empty).
- TanStack v5: `mutate` replaces `#mutateOptions` and notifies only the current mutation
  (`mutationObserver.ts:128-143, 161-219`); hook-level `onError` runs on the `Mutation` itself
  (`mutation.ts:288`), so a keyed composer's unmount doesn't lose the restore.
- MSW fires upload `loadstart/progress/load/loadend` for a mocked XHR with a body
  (`XMLHttpRequestController.ts:308-330`). There is one progress event at 100%; nothing fires for
  `HttpResponse.error()`.
- `_as_message` callers: 4 + 1 + 1 + 3 in production, 6 in `test_indexing.py`, as stated.
- `ServiceTokenRequest` / `ServiceTokenResponse` shapes (`auth/schemas.py:70-85`); Worker settings mirror (`worker/settings.py:43-47`).
- Ingress already allows `/api/v1/messages` (`ingress.yaml:57`); `/api/v1/assets` doesn't reach `/api/v1/internal/`.
- `VITE_ASSET_URL` is already a frontend build arg (`docker/frontend/Dockerfile:22`).
- Garage key format (`values-k3d.yaml:21-24`). The bootstrap's steps (`garage-bootstrap.py:117-132`)
  match "only CORS is red", and it reads env at import, so the fixture's set-then-import order is right.
- Asset NetworkPolicy already has R1, Auth and object-store egress; Messaging already has Auth egress.
- `scripts/test.sh:80-89` lint credentials and `deploy.sh:160-166` are where the plan says.
- `test/api.ts:22` imports generated paths with `import type`, so an `asset` twin loads at red under
  `verbatimModuleSyntax`.
- No 🔴 built on: D13 and D16 are untouched and noted, and D15 is closed by the issue's *Decided already*.
- Workflow: header, sections, 552 lines, RED 1–4 before GREEN with the gate, *Found while building*
  empty, no commit step, record task, verification names lint, unit, integration and e2e.
