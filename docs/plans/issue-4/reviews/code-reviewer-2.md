# Code review — issue 4, round 2: approved

Both major findings from round 1 are fixed. An upload now reads the session's current access token at each
step, so a channel switch no longer freezes it. The test pair's new test holds that, and a mutant
restoring the old behaviour fails it. The README describes the per-worktree e2e stack as `test.sh` runs
it. Every layer the plan names is green, and no critical or major finding is open.

## Responses checked

| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1. Upload confirms with a stale token after its composer unmounts (major) | `attach` passes a getter that reads `session.snapshot()` and falls back to the prop ref only when the session is not signed in | **Resolved.** Code at `MessageComposer.tsx` `attach()`. The switch-channel test passes, and the mutant below fails it. |
| 2. README says the e2e volumes are shared by every worktree (major) | Paragraph rewritten | **Resolved.** `README.md:213-216` now says the project name is per worktree and that `down -v` runs before every `up`. This matches `test.sh` as read in round 1. |
| 3. A 409 with an empty `errors` map becomes a 500 (minor) | Left for a later stage | **Let go.** It is minor, and Asset never sends that shape. Moved to *Left for the human*. |

## What ran

- `npm --prefix src/frontend test`: **331 passed** (36 files), up from 329 because of the test pair's two new tests.
  `typecheck`, `lint` and `build` are all clean.
- `docs/test-report.md` is at `950e66a2d292-dirty`, and HEAD is `950e66a2d292`. Lint ✅, Unit ✅ 722, Integration ✅ 443,
  End-to-end ✅ 21. The Unit count went from 720 to 722 with the two new Vitest tests.
  `build/test-results/e2e.xml` has "Grace sees the image…" and no `<failure`.
- `git diff HEAD -- MessageComposer.tsx`: since round 1, only the token getter and its comment have changed.
- **Mutant** (sketch), in `MessageComposer.tsx` `attach()`: the getter returns `token.current` even when the session is
  signed in, which is round 1's behaviour. Ran `MessageComposer.attachments.test.tsx`. **Caught**: 1 failed and 12
  passed, with `confirms with the renewed token when the user has switched channel during the PUT`,
  `expected [ 'Bearer T1' ] to deeply equal [ 'Bearer T2' ]`.
- No Python mutants or sketches: this pass changed no Python file.
- `sketch.sh clean` run.

## Findings

None open.

## Unpinned

- **The fallback to the prop ref** applies only when the session is not `signedIn`. After a sign-out mid-upload,
  confirm goes out with the last token the composer saw and gets a 401, so the chip fails. That is the right end
  for a signed-out user. No test pins it.
- **The workspace of the token.** `session.snapshot()` gives the current workspace's token. A workspace switch
  mid-upload would confirm under the new workspace. But `ChatLayout` calls `cancelAll()` on a workspace change
  (round 1: deps `[workspaceId]`, mutant-checked), so that upload is aborted first.
- Round 1's unpinned items still stand, and this change does not reach them: the claim runs after the body check,
  there is no double restore, a token refresh doesn't clear chips, and the optimistic row carries its attachments.

## Left for the human

- **Minor, round 1 finding 3:** in `messaging/attachments.py:94`, a 409 from Asset with `errors: {}` raises
  `StopIteration`, which becomes a 500. Asset never sends that today. Treating `{}` as `AssetUnavailableError`
  would close it.
- **Optional, from the test pair:** an integration test that "a bad body never claims". The order is right today,
  but a mutant moving the claim first survived (round 1, mutant 6).
- `README.md:190-196`, the by-hand block: it runs `down` under the default project name `collabhub-test`, not the
  per-worktree one `test.sh` uses. That is fine for someone running Compose by hand, but it is not "what the script
  does" word for word.
- From the green report: remove the old `collabhub-test_*` volumes. Update CLAUDE.md's "five ports" and fixed
  project name. Do the first real two-browser run and the k3d upload/download. Renumber `0005` if issue 3 lands
  first.
- Round 1's carry-overs: compare the OpenAPI files with `python -m …openapi`. Watch the bootstrap's
  exit-on-4xx on an existing volume. Check that the PDF download does not navigate away from the SPA.

## Checked and sound

- Token fix present. Mutant reverting it caught by the switch-channel test.
- README e2e paragraph matches the per-worktree project and `down -v` behaviour.
- Vitest, typecheck, lint, build green. The committed report shows every layer passed at this tree, and the journey passed.
- The only test file changed since the send-back is `MessageComposer.attachments.test.tsx`, which is the test pair's.
  The test-reviewer gated it in round 5.
