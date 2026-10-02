# Code review — issue 4, round 1: send_back

The build matches the plan closely, and every layer the plan names is green: Vitest 329, typecheck,
lint, build, Python unit 311, and the journey passed in the committed report. One probe fails, and no
approved test covers it. An upload keeps running after a channel switch (R15), but once its composer
has unmounted it confirms with the token it started with. A refresh between the two turns that into
a failed chip. Per D32 the test pair writes that red test first, so this goes back to the
test-writer. The README also contradicts the new per-worktree e2e stack. That one is the
code-writer's to fix when the work comes back.

## Expectations                 (round 1 — written before the code was opened)

### Task 5 — shared, contracts, Asset
- **Unpinned:** `ServiceTokenSource` single flight under a lock *and* a failed fetch not cached
  (pinned); the 60 s margin measured from fetch time, not from expiry. Asset: `deleted_at IS NULL`
  on every `assets` select (CH009), the CH001 waiver wording on the internal routes, `install_cors`
  and a Denylist on R1 in `main.py`, the module docstring rewritten, the `ORDER BY id FOR UPDATE`
  (the race test can pass by luck without it), `confirm` on a non-pending asset not re-HEADing,
  Garage down on confirm → 503 with status unchanged, boto3 `head` on a thread (a blocking call on
  the loop passes every test).
- **Takes for granted:** that a claim of ids some of which don't exist sees them as `not-found`
  (missing rows never come back from `ANY(:ids)`; the code has to diff the requested set); that
  `require_service` checks audience `collabhub-internal`.
- **Could go wrong:** claim refusals computed but some rows updated anyway (all-or-nothing);
  claim re-claim for the same message updating `claimed_at` again (harmless); download-url not
  checking `status == ready` or the message id; upload-url accepting a purpose other than attachment.
- **Wrong build:** the claim's `FOR UPDATE` without `ORDER BY` (deadlock, untested); `head` called
  synchronously on the event loop (untested).

### Task 6 — Messaging
- **Unpinned:** order "visibility → ids check **and body check** → uuid7 → claim → insert". The
  body must be validated *before* the claim. If the body rule only runs inside `messages.create`
  (after the claim), an over-long body with attachments claims the assets to a message id that is
  never inserted, and every retry is then refused "already on another message". Those uploads are
  lost to the user. No planned test sends an over-long body with attachments. **First thing to check.**
- Every `_as_message` caller loading attachments page-wide: `reactions.py` (a reaction toggle's
  response), `search.py` (results), the socket edit and delete, the REST edit. A caller passing
  `attachments=[]` makes a reaction or an edit clear the images on screen (`upsertMessage`
  replaces the row). Tests: `test_an_edit_keeps_the_attachments` covers one transport at most.
  Reactions and search have no test.
- **Takes for granted:** the HTTP call to Asset happens inside an open DB session (visibility
  read). It is acceptable, but the claim must happen before any write in that transaction. The
  `httpx.AsyncClient` must be closed in the lifespan.
- **Could go wrong:** 401 retry loops more than once; token fetched per send (pinned); 503 detail
  leaking exception text (CH007); claim with no ids called anyway (pinned); download route
  trusting Asset rather than the snapshot (pinned); `message_deleted` payload carrying attachments
  (pinned).
- **Record:** schema docstrings saying "always empty" rewritten; `SendMessagePayload` docstring.

### Task 7 — Garage, Compose, charts
- **Unpinned (all of it, beyond `helm lint`/test.sh lint and the journey):** the Ingress allows
  `/api/v1/assets` and not `/api/v1/internal`; NetworkPolicies both directions; `asset`
  `depends_on` the bootstrap `service_completed_successfully`; `up --wait` with a one-shot service;
  the k3d `s3.<host>` Ingress and `deploy.sh`'s public endpoint, with the port kept; no credential
  default in `collabhub-deps` (D41); `.env.example` complete; the bootstrap's CORS idempotent.
- **Wrong build:** the k3d public endpoint derived without the port, or `https` hard-coded.

### Task 8 — the SPA
- **Unpinned:** the composer must not keep the old per-call `onError` beside the hook-level one,
  or a refusal restores twice ("old\nold" and duplicated chips). The composer's tests may not
  catch it, because the restore tests drive the hook alone. Submit has to *clear* the chips from
  the store without cancelling them. The error shown must come only from `sendErrors[channelId]`,
  never `send.error` as well. `attachmentIds` must be emitted only when non-empty. The optimistic
  row must carry chip metadata.
- `ChatLayout`: `cancelAll()` + `reset()` on a **workspace** change and on unmount only. If the
  effect depends on the session object or the access token, a token refresh (every ~15 min)
  wipes every draft's chips and aborts uploads. The tests switch workspace and unmount, and none
  refreshes a token. **Mutate and probe.**
- `uploads.ts`: the token read at each step via `getToken()`, not captured once, or an upload
  started at minute 14 confirms with an expired token. Each step checks the signal (pinned).
  `update` of a missing chip is a no-op (pinned).
- `useAttachmentUrl`: decision 36's options (pinned by the 781 s test); token not in the key.
- `AttachmentList`: one automatic refetch per failure episode. The counter must reset after a
  successful retry, or never. An `onError` loop refetching forever is the wrong build. Pending
  `temp:` rows fetch nothing (pinned).
- **Takes for granted:** the mutation's hook-level callbacks run for an earlier mutation after
  the observer re-renders or unmounts. A keyed composer unmounts on a channel switch, so this has
  to be checked in the installed `query-core`. Also takes for granted that the restore reads the
  current draft from the store at error time, not a render-time closure.
- **Could go wrong:** drag-over without `preventDefault` makes drop never fire in a browser (jsdom
  doesn't care); a paste with files has to `preventDefault`, or a browser also inserts the file
  name; the hidden input is not reset, so picking the same file twice does nothing.

### Record (Task 9)
Docs 02, 04 and 06 as Task 9 lists; register D15 🟢, D43 🟢, notes on D13, D16 and D34; an ADR; the
README with no manual Garage step and with the `.env` key change; vocabulary +4; the sweep
(`garage.toml`, `images.py`, `tests/bdd/conftest.py` docstrings, `messaging/README.md`).

## What ran

- `npm --prefix src/frontend test`: **36 files, 329 passed**. `typecheck`, `lint` and `build`:
  clean. `dist/` is ignored.
- `uv run pytest` over asset, messaging, shared and testkit unit: **311 passed**. `ruff check` on
  asset, messaging, shared, contracts, testkit and the bootstrap: clean.
- `conventions.py` on the 18 changed service files by name: no findings. `bash -n` on `test.sh`,
  `deploy.sh` and `lib/common.sh`: clean. I could not diff the OpenAPI documents against
  `python -m …openapi`, because Bash refused the pipe (see *Left for the human*).
- `docs/test-report.md` is at `950e66a2d292-dirty` = HEAD. It shows Lint ✅, Unit 720, Integration
  443 and End-to-end 21, all passed, matching the green report. `build/test-results/e2e.xml` has
  "Grace sees the image and the PDF Ada sends" and no `<failure`.
- Query-core check: `mutation.ts:246,288` runs `this.options.onSuccess/onError` on the mutation
  itself. An earlier send's hook-level callbacks therefore run after the composer re-renders or
  unmounts. `mutationObserver.ts:164-208` runs `#mutateOptions` only while the observer listens.
- **Mutants** (sketch, one at a time, each reverted):
  1. `MessageComposer.tsx`: per-call `onError` restoring the chips as well as the hook. Ran the
     composer, `ChannelView` and restore tests (34). **Survived.** A refusal would restore every chip twice.
  2. `ChatLayout.tsx`: cleanup deps `[workspaceId, current.accessToken]`. Ran both ChatLayout files.
     **Survived.** A token refresh would wipe every chip and abort uploads.
  3. `AttachmentList.tsx`: `onError` always refetches. **Caught** (2 tests).
  4. `useMessages.ts`: no `setSendError(channelId, null)` in `onMutate`. **Caught** (restore test 6).
  5. `useMessages.ts`: the optimistic row carries no attachments. Ran `features/channels` and
     `features/attachments` (257). **Survived.**
  6. `messaging/routers/messages.py`: the REST send claims before the body check, which then runs
     only inside `messages.create`. Ran `test_attachments.py` and `test_messages.py` (56, real
     Postgres). **Survived.**
- **Probe** `features/channels/probe.token.test.tsx` (sketch): render the composer for channel `a`
  with token `T1`, attach a file with the PUT held, then re-render.
  (i) Same channel, token `T2`: confirm carries `Bearer T2`. **Passed.**
  (ii) Channel `b`, token `T2`, so composer `a` unmounts: **failed**,
  `expected [ 'Bearer T1' ] to deeply equal [ 'Bearer T2' ]`.
- `sketch.sh clean` run.

## Conformance

| Plan task or decision | Code | Outcome |
|---|---|---|
| T5 `contracts.assets`, `ServiceTokenSource` (dec. 21) | lock with double-check, margin from fetch time, failures not cached, `invalidate` | as planned |
| T5 Asset settings, db, models, rules, object store, routes, main | two boto3 clients, `head` on a thread, claim `ORDER BY id FOR UPDATE`, all-or-none, `deleted_at` filters, Denylist on R1, CORS | as planned |
| dec. 14, 15, 16, 18 | confirm idempotent, missing object → failed, constant allow-list, no Garage readiness | as planned |
| CH001 waiver on internal routes | not needed: the checker did not fire. Comment on each line | departed (recorded) |
| T6 migration, model, `_as_message(…, attachments=)` at every caller | reactions, search, REST and socket edit all load them page-wide; delete passes `[]` behind `visible` | as planned |
| T6 send order: visibility → ids + body → uuid7 → claim → insert → commit → publish | both transports, shared `claim_for_send` | as planned |
| dec. 12, 13, 26, 38 | 400 `errors.attachmentIds`, 409 `refusal_detail`, 503 wording, download 404 wordings | as planned |
| dec. 20 settings | default empty → 503 on a send with files | departed (recorded, reason holds) |
| T6 `messages.create` returns `(Message, rows)` | — | departed (recorded) |
| T7 bootstrap CORS, Compose, test stack, charts, deploy.sh, test.sh | as listed. `/api/v1/assets` only on the Ingress; NetworkPolicies both ways; `s3.<host>` keeps the port | as planned (+ human-answered e2e change) |
| T7 `ASSET_INTERNAL_URL` an origin | — | departed (recorded, reason holds) |
| T8 composer, chips, paste, drop, picker reset, Send gating, `sendErrors`, keyed composer | as planned. The key is `composer-<id>` | as planned / departed (recorded) |
| T8 `useSendMessage` keyed on `variables.channelId`, hook-level restore | as planned | as planned |
| T8 `ChatLayout` cancel + reset on workspace change and unmount | deps `[workspaceId]` only | as planned |
| T8 `uploads.ts` token per step | `getToken()` per step, but the getter is the composer's ref | **as planned, premise false** (finding 1) |
| T8 `useAttachmentUrl` dec. 36, `AttachmentList` dec. 29, 30 | as planned. PDF via `location.assign` | as planned / departed (recorded) |
| T9 docs 02/04/06/07, ADR, vocabulary, sweep | present and match the code | as planned, except the README (finding 2) |

## Findings

### 1. An upload confirms with a stale token once its composer has unmounted — major
**Where:** `MessageComposer.tsx:91-96,107` with `uploads.ts:17-18,112` · **Checked:** probe (ii) above fails; probe (i) passes.
`addFiles` gets `() => token.current`, where `token` is a `useRef` that only an effect in *that*
composer updates. A channel switch unmounts the composer (it is keyed by channel), but the upload
carries on (R15) and still reads that ref. The ref is frozen at the token the upload started with.
`session.ts:96-99` renews 60 s before expiry. So an upload whose PUT finishes more than 60 s after
a renewal, with the user in another channel, sends `confirm` with an expired token. That is a 401,
and the chip fails. This is the issue's own acceptance case: "Ada starts a large upload, switches
channel and back". Both code comments claim the opposite ("a long upload can outlive the access
token it began with"). No approved test covers it. The fix is small: read the session's current
token, e.g. `session.snapshot()`, instead of a component's ref. Per D32 it needs its red test
first: **send-back**.

### 2. The README says the e2e stack's volumes are shared by every worktree — major
**Where:** `README.md:213-215` · **Checked:** read against `scripts/test.sh:227-234, 295-298`.
"The test stack's volumes are shared by every worktree on the machine — the project name is fixed".
This contradicts what `test.sh` now does: a per-worktree `-p collabhub-test-<dir>`, with `down -v`
before every `up`. Rewrite the paragraph to say what the script does. No test needed. This is for
the code-writer when the work comes back.

### 3. A 409 with an empty `errors` map becomes a 500 — minor
**Where:** `messaging/attachments.py:94` · **Checked:** read.
`next(iter(refusals.values()))` raises `StopIteration` when Asset's 409 carries `errors: {}`. That
is a 500 rather than a 409 or 503. Asset never sends that, so treating `{}` as
`AssetUnavailableError` in `_refusals` is tidier but optional.

## Unpinned

- **Claim after the body check** (mutant 6 survived). If the order flips, an over-long body with
  files claims them to a message that never exists, and every retry is then "already on another
  message". Reading shows `validate_body` runs before `claim_for_send` in both
  `routers/messages.py:258-262` and `realtime_writes.py:197-206`. The send-back suggests the test
  pair pin it.
- **No double restore** (mutant 1 survived): the composer calls `send.mutate(vars)` with no
  per-call callback (`MessageComposer.tsx:121`).
- **Token refresh doesn't clear chips** (mutant 2 survived): the effect deps are `[workspaceId]`
  only (`ChatLayout.tsx:48-55`).
- **Optimistic row's attachments** (mutant 5 survived): `optimistic()` maps the ready chips
  (`useMessages.ts:190-202`).
- **Attachments kept on reactions, search and the socket edit**: no test reads them there (grep),
  and each caller loads them with `for_messages` (read).
- **Asset claim's `ORDER BY id`** (no deadlock) and `head` off the event loop: read, not testable
  by the race test.
- **`onDragOver` preventDefault**, the paste `preventDefault`, and the picker's `value = ''`: present
  (read). jsdom can't tell.

## Left for the human

- The minor finding 3 above.
- I could not compare `openapi/{asset,messaging}.json` with `python -m …openapi`: Bash refused the
  pipe. The writer says it diffed them. A drift would show up as a `tsc` error only where a type is used.
- The bootstrap now exits at once on any admin-API 4xx, including in steps that existed before
  (`garage-bootstrap.py:61-66`). That is right for a refused CORS body. Watch the first `up` on an
  existing volume.
- A PDF download navigates the page to the presigned URL (`AttachmentList.tsx:155`). If that URL
  were ever refused, Garage's XML error would replace the SPA. In the first real run, check that it
  downloads and stays.
- The first real run's six acceptance checks and the k3d upload/download (green report, item 3).
- The CLAUDE.md "five ports" / fixed project name text (green report, item 2).

## Checked and sound

- Every hook-level callback in `useSendMessage` keys on `variables.channelId`. The restore reads the
  draft from the store at error time.
- The error shown comes only from `sendErrors[channelId]`. `attachmentIds` is sent only when non-empty.
- The image refetch limit (mutant 3) and the send-error clear (mutant 4) are both caught.
- Asset tenancy comes from the token on the public routes. Internal routes use `require_service`
  only, with no `require_user`. Every `assets` select filters `deleted_at`. No file name is logged.
- The token source is single flight and doesn't cache failures. The 401 is retried once and never loops.
- Ingress `/api/v1/assets` only. The internal prefix is never routed. NetworkPolicies Messaging→Asset
  in both directions. `messagingClientSecret` is required with no default. `origin_s3_endpoint` keeps
  the scheme and port.
- Register D15 🟢, D43 🟢, notes on D13, D16 and D34. ADR present. Doc 06 matches the code
  (780 s, restore, per-channel errors).
- The test files changed are the test pair's (send-back 3) and match its red report. No other test
  was touched.
