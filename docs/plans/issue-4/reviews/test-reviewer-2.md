# Test review — issue 4, round 2: approved

All three round-1 findings are fixed. I re-ran the critical one against a sketch: the 780 001 ms test now goes green with a correct `staleTime: 780_000`, and goes red with a wrong one. Nothing else changed.

## Responses checked

| Earlier finding | Writer's response | Outcome |
|---|---|---|
| 1 (critical) freshness boundary drifts with `vi.waitFor` | `landedAt()` reads `dataUpdatedAt` from the cache; clock set to that +779_999 / +780_001; no `waitFor` between `setSystemTime` and mount; header corrected | **Resolved.** Sketched, see below. |
| 2 (major) PUT byte count over-pins the double | `xhrPut.test.ts` and `uploads.test.ts` assert `size > 0`, the signed Content-Type and the method, with a comment on what the double can't see | **Resolved** (read: lines 36–38 and 70–71). A build that sends no body or the wrong type still fails. |
| 3 (minor) abort needs rejection from the signal listener | Comment added at `xhrPut.test.ts:96–97` | **Resolved** |

## What ran

- Sketch (`sketch.sh frontend`, since cleaned): a minimal `useAttachmentUrl` with `staleTime` 780 000, window-focus and reconnect refetch off, and `url` null while a stale entry refetches. `useAttachmentUrl.test.ts`: **7 passed of 7**. This includes both boundary tests that failed in round 1.
- Wrong build, `staleTime` 781 000: "requests a fresh URL first when a mount finds it stale" fails, 6 passed. The 780 001 side is pinned.
- Not re-run: the 779 999 side against a build with a short constant. Round 1 showed that side is the one a too-short constant fails, and the fix puts it on the same `dataUpdatedAt` anchor as the other.
- `xhrPut` and `uploads` were not re-sketched. The change loosens an assertion down to what round 1 showed the double reports, and the round-1 sketch passed with the real byte count, so it passes `size > 0` too.
- `git status --short` shows no files outside the plan's tests, helpers and report.

## Findings

None.

## Left for later stages

Carried from round 1, unchanged:
- **Code-writer:** `useSendMessage` sends `attachmentIds` only when non-empty; move `cancelAll()` + `reset()` into `test/setup.ts`'s `afterEach` once the store exists.
- **Code-writer:** the composer tests expect the control names, `max-h-60 max-w-80`, and the other names listed in the red report's *For the code-writer*.
- **Code-writer:** `up --build --wait` with the one-shot bootstrap; `URL_STALE_MS` beside the TTL.
- **Code-writer:** `putFile` rejects directly from the signal's abort listener, calling `xhr.abort()`; keep `refetchOnWindowFocus` and `refetchOnReconnect` off for the URL query. My sketch needed both.
- The Asset and testkit integration tests assume `asset.main.create_app(settings, key_source=…)` and the `S3ObjectStore(...)` keyword names given in the report.

## Checked and sound

- Everything in round 1's *Checked and sound* stands; nothing it covers has changed.
- `useAttachmentUrl.test.ts`: `gcTime: Infinity` in `createTestQueryClient` keeps the entry across the unmount, so `landedAt()` reads a real entry.
- The 779 999 test checks for no request and that the URL is on the first render. The 780 001 test checks that the URL is null at first, then that a second request lands.
