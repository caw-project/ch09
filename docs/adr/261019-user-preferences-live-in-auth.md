# User preferences live in Auth, per user, with validated keys

- **Status:** Accepted
- **Date:** 2026-10-19

## Context

Register D28 asked where per-user preferences live, and stayed open while the SPA shipped a light-only palette and the browser's own locale for every time. The first preference — a 12/24-hour clock (issue gh-3) — forces the question. Display name and avatar are *profile* and already live on `users`; a preference is a choice about how the app behaves for one person, the same in every workspace.

## Decision

Auth owns preferences, in a `user_preferences` table: `user_id` (a real foreign key to `users.id`, both ends being Auth's), `prefs jsonb`, `version`, `updated_at`. They are per user, not per workspace. `GET /api/v1/users/me/preferences` returns the stored object, `{}` for a user with none, and never creates a row. `PATCH` takes a flat object and merges it in one SQL upsert (`prefs || new`, then `- removed keys`), so two tabs saving different keys cannot lose each other's write; on one key the last commit wins. `null` removes a key. The keys are validated on the server — an unknown key or a bad value is a 400 naming the key, and the whole patch is refused. The only key today is `clock`: `"12h"` or `"24h"`, absent meaning Automatic. In the SPA they are TanStack Query server state under `['preferences']`, never Zustand (D24).

## Consequences

Adding a preference is a server change (one entry in `parse_patch`) plus a client reader; nothing in the schema moves. The validation means the column never holds a value the SPA cannot read. Both routes are plain `require_user` — they are not in Conventions §5.2's fail-closed set.

Preferences are not in the access token, so a change reaches another tab on its next refetch (five minutes, a focus or a reconnect), not at once. Reading costs one request per session start. jsonb's flexibility is bounded by the validator; whoever adds a key must also decide its default.

## Alternatives Considered

### A `preferences jsonb` column on `users`

Fewer tables, but every profile write and every preference write would contend on the same row and bump the same `version`, and a merge would be a read-modify-write.

### A separate preferences service

Nothing here justifies a deployable of its own, and it would need its own copy of identity.

### Preferences in the token

Fast to read, but stale for the token's lifetime and a growing claim on every request on the platform.
