# Plan review — issue 4, round 2: changes_requested

All ten round-1 findings are fixed, and each fix holds against the repo and the installed
libraries. One new major comes out of the fix for finding 3. The paste test is now dictated as
`fireEvent.paste`, and that never inserts text in jsdom. So its first half ("inserts the text")
fails at red before the stated red, and it fails again on a correct green build. It's a
one-line fix, so I'm sending it back rather than leaving it for the test pair to trip over.

## Responses checked

| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1 Seam reds | Decision 25: `contracts` stays GREEN, `asset_stub` imports it inside the fixture; stub rows red at setup; *no stub* rows named with their own reds | resolved — `messaging/settings.py:7` is `extra="ignore"`, so `build_settings`' new keys build today's app; `client_for` (`conftest.py:105-111`) takes overrides, so `test_token_endpoint_down_is_503` builds without the stub |
| 2 Load failures in existing files | New `useSendMessage.restore.test.ts` and `ChatLayout.attachments.test.tsx`; the five `mutate` calls rewritten with reds | resolved — checked `useMessages.test.ts:134-214`. An object body fails `:139`/`:141`, `:204` fails on the wording, and `:157`, `:181`, `:214` don't read the body. One wording point is left below |
| 3 Guards green at red | CORS allow and refuse in one test; paste with text and file-only paste in one test | CORS resolved; paste **still open, in a new form** — F1 |
| 4 testkit S3 client | Admin `GetBucketInfo` via stdlib, plus an unsigned GET expecting an S3 XML error | resolved — `garage-bootstrap.py:43-44, 93` uses that exact call shape |
| 5 R11 "nothing refetches" | Decision 36; focus, reconnect and re-render at 781 s | resolved — `focusManager.ts:59-72`: `setFocused(false)` then `true` fires the listeners with `true`, so the test fails a build that leaves focus refetch on |
| 6 Restore into a non-empty draft | Decisions 33–35, four restore tests | resolved |
| 7 Late chip-store writes | Decision 37; held upload-url and held confirm, each with its positive | resolved |
| 8 Socket can't reach the stub | `realtime_url_for(**overrides)` over `serve(build_asgi_app(build_settings(…)))` | resolved — `build_asgi_app(settings, *, key_source)` at `main.py:137`, `serve` at `testkit/apps.py:44` |
| 9 `realtime.py` | Mapped in Task 6; only `publish_message_received` left unchanged | resolved |
| 10 Stale `.env` | Task 10 starts with `cp .env.example .env` | resolved |
| Minors | four new steps, sweep, vocabulary, decision 38, doc 04 §4.2/§5, CH001 waiver taken; 780 s kept a literal "as the issue states it" | resolved; the literal is a defensible reading, let go |

## Findings

### 1. The paste test can't pass on a correct build, and its red is wrong — major
**Where:** Task 3, `MessageComposer.test.tsx` paste row ("`fireEvent.paste` with a `clipboardData`
stub … inserts the text") · **Checked:** `@testing-library/user-event` 14.6.7 (`package.json:31`).
Its `event/behavior/paste.js:6-15` and `clipboard/paste.js:5-15`, in the primary checkout's
`node_modules`, are where the default insert lives. `MessageComposer.test.tsx:75-76` already pastes
through `user.paste`.
In jsdom, a paste's default action, putting the text in the box, is something user-event does. jsdom
doesn't do it, and neither does `fireEvent`. `user.paste(data)` inserts `clipboardData.getData('text')`
into the focused field unless the handler called `preventDefault`. `fireEvent.paste` only dispatches
the event. Decision 27's `filesFromPaste → null` means "let the browser paste", so a correct composer
leaves the default alone. Under `fireEvent`, nothing then inserts the text. The first half fails at
red (not the stated "second half times out"), and it fails at green too. The test-writer will either
write a test the code can't pass, or make the handler insert text itself, against the plan.
Settle it in the row. Drive both pastes through `user.paste(stub)` after focusing the box (the stub
answers `getData('text')`, not only `'text/plain'`), or assert that the text paste was not
default-prevented instead of asserting the inserted text. Then restate the red to match. With
`user.paste`, the first half passes at red and the second half is the red, as the plan already says.

## Left for later stages

- **Minor — restore file's load-failure note.** `useSendMessage.restore.test.ts` says "every test
  asserts on chips". The fourth test ("the next send for A clears `sendErrors[A]`") needn't. It can't
  pass today either (`stores/chat.ts` has no `sendErrors`), so the load failure hides nothing, but the
  test-writer should give its red honestly.
- **Minor — carried from round 1, unverified.** Whether `up --build --wait` accepts the one-shot
  `garage-bootstrap` exiting 0. Task 10 will show it.
- **Minor — staleness constant.** `URL_STALE_MS` is a literal beside a configurable presign TTL. The
  writer keeps it because the issue states 780 s. Defensible. If the TTL setting ever changes, the
  two drift.

## Checked and sound

- Base `950e66a` matches `git log -1`.
- `asset_stub` imports `contracts.assets` inside the fixture body, so only stub tests error at setup.
- TanStack `mutationObserver.ts` line references (`:85-93`, `:132-142`, `:164-208`) point at the
  same code checked in round 1.
- `onlineManager` reset alongside `focusManager`. Fake time is `Date` only, which is what TanStack's
  staleness reads.
- The plan is 600 lines, at the limit. RED 1–4 still precede GREEN. *Found while building* is
  empty, and no task commits.
