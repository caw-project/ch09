# Send-back from the code-writer — gh-3

**To the test-writer.** One type error in a test file stops the build, so the journey cannot run.

## The fault

`src/frontend/src/features/settings/SettingsPage.test.tsx` line 262, inside `renderWithClock`:

```ts
auth.updatePreferencesBy(async (_call, body) => {
  stored = body.clock === null ? {} : { ...stored, ...body }
```

`body` is typed `PreferencesPatch` (`clock?: Clock | null`). Narrowing `body.clock` does not narrow
`body`, so the spread has `clock?: Clock | null | undefined` and is not assignable to
`Preferences` (`clock?: Clock`):

```
src/features/settings/SettingsPage.test.tsx(262,7): error TS2322: Type '{ clock?: Clock | null | undefined; }' is not assignable to type 'Preferences'.
```

Run: `npm --prefix src/frontend run typecheck` (also `run build`, which is `tsc -b && vite build`,
and `scripts/test.sh lint`). Every Vitest test passes (582/582); this is the only type error.

## Why nothing in the code stage fixes it

The plan fixes `Preferences { clock?: Clock }` and `PreferencesPatch { clock?: Clock | null }`.
Loosening `Preferences` to accept `null` would make the wire type wrong. The red report flagged
that this could appear once `Preferences` existed. `docker/frontend/Dockerfile` runs
`npm run build`, so the Compose test stack cannot build and the e2e layer has not run.

## Smallest fix

Build the value without spreading the patch, e.g.

```ts
stored = body.clock === null ? {} : { ...stored, ...(body.clock ? { clock: body.clock } : {}) }
```

Behaviour is unchanged (the test only ever sends `'12h'`, `'24h'` or `null`).

## State of the rest

All Auth tests pass (280), all Vitest pass, the record is written. After the fix: rerun
`npm --prefix src/frontend run typecheck`, `scripts/test.sh lint unit`, then `scripts/test.sh e2e`.
