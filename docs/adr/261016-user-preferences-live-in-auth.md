# User preferences live in Auth, per user, validated by key

- **Status:** Accepted
- **Date:** 2026-10-16

## Context

Register D28 asked where per-user preferences live. Until now nothing stored a per-user choice, which is why the SPA was light-only and every time was written in the browser's locale. Issue gh-3 adds the first preference, a 12-hour or 24-hour clock, so the decision is forced. Auth already owns `users`, the token's `sub` identifies the caller, and a preference follows a person across workspaces rather than belonging to one.

## Decision

We will store preferences in Auth, in a `user_preferences` table: `user_id` (a real foreign key to `users`), `prefs jsonb`, `version` and `updated_at`. A row exists only after the first write. `GET` and `PATCH /api/v1/users/me/preferences` read and change the caller's own row, keyed on the token's `sub`, with no id in the path or body. The server validates keys by name and value and refuses unknown ones (`extra="forbid"`); `null` removes a key and an absent key is left alone.

A write is a single `INSERT … ON CONFLICT DO UPDATE SET prefs = (prefs || new) - removed`. Two writers of different keys both land, because neither reads and then overwrites. The SPA keeps preferences in TanStack Query under `['preferences']`, never in the store. Both routes stay on `require_user`, so they fail open when R1 is down.

## Consequences

A theme, a locale or notification settings now have a place to go, but each still needs its own key, validation and decision; the SPA stays light-only because of D26, not for want of a store. Preferences are not in the access token, so a change shows at the next fetch, not the next renewal. Two writers of the *same* key race and the last write wins. Unknown keys cannot be stored, so adding a preference is a code change in Auth and in the SPA.

## Alternatives Considered

### A `preferences` column on `users`

Simpler, but it would put every preference write on the hot `users` row, bump its `version` and mix settings with identity. A separate row also leaves `users` unchanged for the response shapes other clients read.

### A claim in the access token

Free to read, but stale until renewal and a larger token on every request. A clock choice that does not apply for fifteen minutes would look broken.

### A separate preferences service, or cache in R1

A new service for one JSON object is far more than needed, and nothing here needs a cache: the SPA fetches once per shell mount.

### Read-modify-write in application code

Loses a concurrent write of a different key. The single merge statement closes that without locks.
