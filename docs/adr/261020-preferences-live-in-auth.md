# Per-user preferences live in Auth, one validated JSON map per user

- **Status:** Accepted
- **Date:** 2026-10-20

## Context

Register D28 asked where per-user preferences live, and stayed open while six messaging
slices shipped a light-only palette and the browser's own time format. Issue gh-3 adds the
first preference, a 12/24-hour clock, and so has to answer it: the choice must follow the
user to another browser and apply to every message, thread-summary and search-result time.

## Decision

Auth owns them. A `user_preferences` table holds one row per user: `user_id` (primary key and
a foreign key to `users`), `prefs jsonb`, `version` and `updated_at`. Preferences are per
user and global, never per workspace. The server decides which keys exist (`auth.preferences.KEYS`
maps each to a validator), so a client cannot store what the service does not understand;
`clock` (`"12h"` or `"24h"`, absent for Automatic) is the first.

`GET /api/v1/users/me/preferences` returns the map, `{}` when the user has none, and never
creates a row. `PATCH` merges the keys sent, and `null` removes one, in a single
`INSERT … ON CONFLICT DO UPDATE` that takes the row lock and merges into the latest committed
value, so two tabs changing different keys keep both. An unknown key or a bad value is a 400
with `errors.<key>` and nothing is written. Both routes use `require_user` and fail open when
R1 is down. The display name stays on `users`: it is profile, not a preference.

The SPA holds them in TanStack Query under `['preferences','me']`, never Zustand (D24). A
choice shows at once and saves serially in click order, so the server's last write is the
user's last choice.

## Consequences

The next preference is one validator in `KEYS`, with no migration. The map is not in the
token and not cached in R1, so every screen fetches it once and a change in another tab
arrives on the next window focus. A bad key cannot be stored, but a removed key's old value
in a row stays harmless.

## Alternatives Considered

### A `preferences` column on `users`, exposed on `/users/me`

Every profile read and every profile write would carry preferences, and a rename and a clock
choice in two tabs would contend on one row's `version`.

### Preferences in the token or in R1

A change would wait for the next token renewal, or add a second source of truth to keep in
step, for a value read once per page.

### A separate preferences service

A service, a database and a deploy unit to store a handful of keys per user.
