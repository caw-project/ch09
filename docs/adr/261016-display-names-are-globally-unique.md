# Display names are unique across CollabHub, enforced by one index

- **Status:** Accepted
- **Date:** 2026-10-16

## Context

Display names were free text, so two people could share a name and a message author line could not tell them apart. Issue gh-3 lets a user rename themselves, which makes the question urgent. Tenancy is by workspace, but a name is shown in directories, search and mentions, and a person belongs to several workspaces. The decision is register D46.

## Decision

We will make display names unique across all of CollabHub: trimmed, compared case-insensitively, and counting deleted accounts. The only arbiter is a unique expression index, `uq_users_display_name ON users (lower(display_name))`. Every writer (the rename route, first-sign-in provisioning and migration `0002`) goes through `auth.names`, which trims, bounds the length to 100 code points and refuses control, invisible-format, surrogate, private-use, unassigned and separator characters. The index does not `btrim()`, because it trims only spaces while `str.strip()` trims all Unicode whitespace.

A rename onto a taken name is a `409` with fixed text naming nobody. A first sign-in whose provider name is taken walks `X`, `X 2`, `X 3`… inside savepoints until an insert holds, so a lost race is a retry, not a failed sign-in. Migration `0002` cleans stored names and renames existing duplicates, the oldest account keeping its name; it is one-way.

## Consequences

A `409` reveals that a name exists somewhere, in any workspace; we accept it, as it names no user or workspace. A deleted account keeps its name taken, so names are not recycled (D16, retention, is untouched). `lower()` does not do full case folding: `ß`/`SS`, final sigma and dotless `ı` stay distinct, and confusable lookalikes (Unicode TR39) are a known gap. Refusing `Cf` also refuses the zero-width joiner, so emoji ZWJ sequences cannot be names. Changing the folding later is one migration that recreates the index, after renaming any pair the new rule makes collide.

## Alternatives Considered

### Unique per workspace

Matches tenancy, but a person's name would differ by workspace and the sidebar, directory and one's own messages could disagree. It also needs a workspace column on a table that has none.

### A pre-check `SELECT` only

Cannot close the race between two writers; only the index can.

### `citext` or `btrim()` in the index

`citext` would change the column type; `btrim()` disagrees with Python's trimming. Both are worse than one rule applied by every writer.

### Allow duplicates and disambiguate in the UI

Leaves impersonation by identical name possible.
