# Send-back from the code-reviewer — issue 4

This carries finding 1 of `reviews/code-reviewer-1.md`, a **major** finding. It is a behaviour that
no approved test covers, and a probe shows the real code gets it wrong. Per D32 the red test comes
first: the test-writer writes it, the test-reviewer gates it, and the code-writer then fixes the
code. The plan does not need to change: Task 8 already says the token is read per step, and R15
already says uploads carry on across a channel switch. The review's other findings are for the
code-writer when the work comes back (finding 2, the README; finding 3, minor).

## What is wrong

An upload keeps running after a channel switch (R15), but its `confirm` uses the token the upload
started with, not the current one.

- `MessageComposer.tsx:91-96` keeps the token in a `useRef`, updated by an effect in that
  composer. `:107` passes `() => token.current` to `addFiles`.
- `uploads.ts:94,112` calls `getToken()` before upload-url and before confirm.
- The composer is keyed by channel (`ChannelView.tsx`, `composer-<id>`), so a channel switch
  unmounts it. Its effect never runs again, and the ref stays frozen.
- `session.ts:96-99` renews 60 s before expiry. So an upload whose PUT ends more than 60 s after a
  renewal, with the user in another channel, confirms with an expired token. That is a 401 from
  Asset, and the chip reads failed. This is the issue's acceptance case: "Ada starts a large
  upload, switches channel and back".

## What ran

The probe, written in the sketch at `src/features/channels/probe.token.test.tsx`:
- It renders `MessageComposer` keyed by channel, for channel `a` with `accessToken="T1"`, attaches
  `big.png` with `asset.acceptUploads({ hold: { put } })`, and records each confirm's
  `Authorization` through `server.events.on('request:start')`.
- (i) It re-renders the same channel with `T2`, then releases the PUT. Confirm carries
  `Bearer T2`: **passes**.
- (ii) It re-renders channel `b` with `T2`, which unmounts `a`'s composer, then releases the PUT.
  This **fails**: `AssertionError: expected [ 'Bearer T1' ] to deeply equal [ 'Bearer T2' ]`.

## Why the code stage can't fix it alone

The fix is a behaviour change with no test, and this repo fixes bugs test-first (CLAUDE.md, D32).
The code-writer may not write tests.

## The smallest fix I'd expect

- **Test (test-writer):** the probe's two cases, in `MessageComposer.attachments.test.tsx` or a file
  beside it. Mount, attach with the PUT held, then switch channel *and* token, then release. Assert
  that confirm carries the new token. Keep the same-channel case as the positive half. The probe
  above can be used as written. It needs no new helper, because `server` is already exported from
  `test/api.ts`.
- **Expected red:** case (ii) fails with `Bearer T1`.
- **Code (code-writer, after the gate):** read the session's current access token at each step
  (`session.snapshot()` in `lib/auth/session.ts`) rather than a component's ref, or keep the getter
  somewhere that outlives the composer.
- **Optional, while you're there:** pin "a bad body never claims". Send an over-long body with one
  ready asset through REST and the socket, then assert 400 and that `asset_stub` recorded no claim.
  The order is right today (read), but a mutant moving the claim first survived all 56 Messaging
  integration tests.
