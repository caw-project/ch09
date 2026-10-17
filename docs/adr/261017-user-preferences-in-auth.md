# Store per-user preferences in the Auth service

- **Status:** Accepted
- **Date:** 2026-10-17

## Context

Register D28 asked where per-user choices live. Nothing stored them: `users` held a name, an avatar reference and a status, and the SPA shipped a light-only palette and browser-locale times because there was nowhere to keep a choice. Issue gh-3 adds the first one, a 12/24-hour clock, and decided the question: the choice follows the person across devices and workspaces, so it has to be server-side, and the issue named Auth.

## Decision

Auth stores preferences in a `user_preferences` table: one row per user, `prefs jsonb`, a `version` and `updated_at`. It is global to the person, never to a workspace. The server owns the set of keys and the values each accepts (`auth.preferences.KNOWN`); a body with an unknown key or a bad value is a 400 with `errors.<key>` and nothing is applied. `GET` and `PATCH /api/v1/users/me/preferences` sit on `require_user`, with the row taken from the token's `sub`. A PATCH is merged by a single `INSERT … ON CONFLICT DO UPDATE` (`prefs || :set - :remove`), and `null` removes a key. The SPA reads them through one TanStack query keyed by user.

## Consequences

A new preference is one entry in `KNOWN`, with no migration. Two tabs setting different keys both land; the same key is last-write-wins. There is no row until the first choice, so reads are free of side effects.

The values are not in the access token, so a client must fetch them; the first render of a time shows the browser's format until the query lands. Because validation is by key allow-list in code, a typo in a key is caught by the server rather than stored. Anything that must be known by another service (notification settings, D18) will need an explicit decision on how it reaches that service, since services do not read Auth's tables.

## Alternatives Considered

### A `preferences` column on `users`

Simpler, but every preference write would bump the profile's `version` and `updated_at`, and a merge race on a shared row would contend with unrelated profile edits.

### A separate preferences service

More isolation than one jsonb table needs, and one more deployable for a handful of keys. It can be extracted later, since the API is already its own route.

### Client-only storage (`localStorage`)

Does not follow the person to another device, and the repo's rule is that a signed-in page keeps nothing in browser storage.
