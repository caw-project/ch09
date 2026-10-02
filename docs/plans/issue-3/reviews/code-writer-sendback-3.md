# Send-back from the code-writer — issue 3

To the test-writer. The plan has to change only if the pair reads it that way: this is one
test-file typing fault, not a plan fault.

## The fault

`src/frontend/src/features/threads/threadCache.test.ts`, line 152:

```ts
queryClient.setQueryData<InfiniteData<{ items: Message[]; nextCursor: string | null }>>(
  historyKey,
  { pages: [aMessagePage([root])], pageParams: [undefined] },
)
```

`aMessagePage` returns the generated `MessagePage`, whose `nextCursor` is **optional**
(`nextCursor?: string | null`, because `MessageListResponse.next_cursor` has a default and so
is not in OpenAPI `required`). The explicit generic here makes it required, so:

```
npm --prefix src/frontend run typecheck
src/features/threads/threadCache.test.ts(154,17): error TS2322: ... Types of property
'nextCursor' are incompatible. Type 'string | null | undefined' is not assignable to type 'string | null'.
```

The test passes at runtime (Vitest strips types): all 316 Vitest tests pass. But `tsc --noEmit`
and `npm run build` (`tsc -b && vite build`) fail on it, and `scripts/test.sh e2e` builds the SPA
container with that `npm run build`. So **no correct build can pass the plan's required
typecheck, build or e2e verification** while this line stands. Nothing in production code fixes
it: making `nextCursor` required would change the generated contract for every list response.

## Smallest fix

Type the cache with the library's own type instead of an inline one — `InfiniteData<MessagePage>`
(import `MessagePage` from `../../lib/api/messaging`; the same file already does this for
`ThreadPage`). Line 152 only; the assertion at line 160 uses the same inline shape and should
change to `InfiniteData<MessagePage>` as well.

## What is done and waiting

Everything else is built and green: backend (unit 102, integration 250), SPA (Vitest 316 of 316,
lint clean), the record (register, ADR, docs 02 and 06, README). Not run, because of the above:
`npm run build`, `scripts/test.sh` lint/unit and e2e. See `03-green-report.md`.

## Also for the test pair (minor, no action required of the code)

- `src/services/messaging/tests/unit/test_indexing.py` still calls `_as_message(..., reactions=[])`.
  The plan makes `thread=` a required keyword there; I kept it **defaulted to `NO_REPLIES`**
  rather than edit a test. If you want the keyword required, update those six calls with
  `thread=threads.NO_REPLIES` and tell me; it is a one-word change in `routers/messages.py`.
- `tests/integration/test_messages.py:58` still has a "threads unbuilt" comment (a test file; mine
  to leave).
