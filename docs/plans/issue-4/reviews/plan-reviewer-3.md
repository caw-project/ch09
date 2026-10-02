# Plan review — issue 4, round 3: approved

This is the final round, and the one open major from round 2 is fixed. The paste test now uses
`user.paste` on the focused box with a stub that answers `getData('text')`. The installed user-event
inserts text that way, so the test's first half passes at red and its second half is the real red,
as the plan now says. No critical or major finding is open. The three minors carried from round 2
stay under *Left for later stages*.

## Responses checked

| Earlier finding | Writer's response | Outcome |
|---|---|---|
| R2-1 The paste test can't pass on a correct build, and its red is wrong (major) | Task 3, `MessageComposer.test.tsx` paste row (plan :348): focus the box, then `user.paste(stub)`, never `fireEvent.paste`. The stub has `types`, `files` and a `getData` that answers both `'text'` and `'text/plain'`. Red restated: the first half passes, the second half's `findByText(/Pasted image/)` times out | **resolved.** Checked in the primary checkout's `node_modules/@testing-library/user-event/dist/esm`. `clipboard/paste.js:5-14` passes a non-string `clipboardData` through as given and dispatches `paste` on `doc.activeElement`. `event/behavior/paste.js:6-15` inserts `event.clipboardData.getData('text')` into an editable target unless the event is default-prevented, and inserts nothing when that is `''`. So the text paste inserts at red and on a correct `null`-returning green build. The file-only paste inserts nothing and adds no chip at red, so it times out as stated. Focusing first matters because the target is `activeElement`, and the row says to |
| Minor: the restore file's load-failure note | Left for a later stage | let go — listed below |
| Minor: the bootstrap exit under `--wait` | Left for Task 10 | let go — listed below |
| Minor: `URL_STALE_MS` beside the TTL | Kept as a literal | let go — listed below |

## Findings

None.

## Left for later stages

- **Minor — the restore file's load-failure note (test pair).** `useSendMessage.restore.test.ts`
  says "every test asserts on chips". The fourth test ("the next send for A clears `sendErrors[A]`")
  doesn't need to. It can't pass today either (`stores/chat.ts` has no `sendErrors`), so the load
  failure hides nothing. The test-writer should still give that test's own red honestly in the red
  report.
- **Minor — unverified: `up --build --wait` with a one-shot `garage-bootstrap` (code-writer).**
  `asset` waits for the bootstrap to complete (decision 24). Whether `--wait` treats a service that
  exits 0 as healthy is for Task 10's first run to show. If it doesn't, record the fix under *Found
  while building*.
- **Minor — staleness constant (code pair).** `URL_STALE_MS = 780_000` is a literal next to a presign
  TTL that can be configured. The writer keeps it because the issue states 780 s, which is a
  defensible reading. If the TTL setting ever changes, the two drift apart.
- **Assumed decisions for the human to read** (all recorded and defensible; accepted in rounds 1–2):
  15 (confirm with a missing object → `failed`), 16 (allow-list is a code constant, the setting
  removed), 18 (Garage not a readiness check), 26 (duplicate id → 400), 27 (only `image.png`
  renamed), 28 (a rule-breaking file is a failed chip that counts), 29 (`window.open` before the
  fetch), 33 (restore merges text and chips, nothing dropped), 34 (send error clears on the next
  send for that channel), 38 (a whitespace body with attachments is stored as `""`).

## Checked and sound

- The base commit `950e66a` matches `git log -1` in the worktree.
- The only change since round 2 is the paste row (Task 3) and its Review responses line. Nothing
  next to it changed. The other Task 3 rows and the RED-before-GREEN order are as approved in round 2.
- *Found while building* is still empty. No task commits. The plan is 601 lines, which is still at
  the limit.
