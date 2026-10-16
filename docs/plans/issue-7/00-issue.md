Issue: 7

# Issue 7 — A name for a member who joined after the directory loaded

## Summary

When someone joins a workspace after another user's tab loaded the member directory, that tab
shows the newcomer as an 8-character id — on their messages, in the DM list, everywhere a name
appears — for up to five minutes, or until a reload. Found on the first preview (issue 6):
Grace's first message showed on Ada's screen as `01a13ec0`. After this issue, an id the
directory doesn't know makes the SPA fetch the directory again, once, and the name appears.

## Services touched

**The SPA only.** Read `docs/design/06-frontend-spa.md` §5.1–§5.2 (reconnect, DMs, "`shortId`
when unknown") and :304-307 (names resolved through the directory). No service changes; Auth's
`GET /api/v1/workspaces/{id}/members` is used as it is.

## What exists already

- **One directory for the whole UI:** `useWorkspaceMembers(accessToken, workspaceId)` in
  `src/frontend/src/features/channels/useWorkspaceMembers.ts` — key
  `directoryKeys.members(workspaceId)` = `['workspace-members', workspaceId]`,
  `staleTime: 5 * 60 * 1000`, and `nameFor(id)` falling back to `shortId(id)` (first 8 chars).
  Its header says the fallback is for someone who has *left* the workspace.
- **Seven consumers**, each calling the hook: `MessageList.tsx:118` (authors), `ThreadPanel.tsx:68`
  (thread authors), `DirectMessageList.tsx:37` (DM names, sort, picker), `MemberPanel.tsx:33`,
  `MessageComposer.tsx:89` (typing indicator), `ChannelView.tsx:53` (DM header and composer
  title), `SearchPage.tsx:29` (result authors and DM channel names via `useChannelNames`).
- **Nothing invalidates or writes `directoryKeys`** anywhere in the SPA. `workspaceMembers`
  (`lib/auth/api.ts:124-142`) already fetches every page (`limit=200`, loops on the cursor).
- **The QueryClient** (`main.tsx:15-28`) leaves `refetchOnWindowFocus`/`refetchOnReconnect` at
  TanStack's defaults, which fire only once the 5 minutes are up.
- **The socket's `onConnect`** (`lib/realtime/useChannelSocket.ts:139-155`) invalidates the
  channel list, and history and threads for the open channel — not the directory.
- **Auth publishes no events**: joins (first-sign-in auto-join of the demo workspace locally,
  `identities.provision_user`; `POST /workspaces/{id}/members` elsewhere), role changes and
  renames all emit nothing, and no socket event carries a name (doc 02 :260-264, :797-799).
- **Tests:** no `useWorkspaceMembers` test exists. The MSW stub `auth.members(members)`
  (`src/test/api.ts:312-316`) serves one page.

## Requirements

1. **An unknown id fetches the directory again.** When any consumer asks for the name of an id
   the directory for that workspace does not hold, and the directory is not already being
   fetched, the SPA refetches it.
2. **One request at a time.** Unknown ids seen while a fetch is in flight — the first load, an
   R1 refetch, or any other — start nothing while it runs. If that fetch lands without them,
   they start **one** refetch then (it may have begun before they joined).
3. **Departed ids stay quiet.** An id is departed once a fetch that *started after the id was
   first seen* completes without it: it shows its short id and starts no further refetch, until
   the directory is fetched again for another reason (staleness, a reconnect, a workspace
   switch, a reload). That fetch clears the departed set.
4. **The short id until the name arrives.** While the refetch is in flight the id shows as its
   short id, as today; when it lands, every place that id appears shows the name without a
   reload.
5. **A reconnect refetches the directory**, as it refetches the channel list: messages missed
   while the socket was down may be from new members.
6. **Per workspace.** Each workspace has its own directory and its own departed set; a refetch
   started in one never writes the other's.

## Where the rules meet

- **R1 and the staleness refetch:** an unknown id seen just as the 5-minute refetch starts joins
  that fetch (R2) — one request, never two.
- **R1 and R5:** a reconnect's refetch and an unknown author arriving in the recovered history
  are one request.
- **R3 and a rejoin:** a departed id whose user rejoins resolves at the next fetch for another
  reason, not at once. Accepted.
- **R1 and a workspace switch (R6):** a refetch in flight for workspace A when the user switches
  to B lands in A's cache only; B's unknown ids follow B's own rules.

## Paths each rule holds on

| Path | What must be true |
|---|---|
| First load, directory still loading | ids are unknown but no extra fetch starts; ids still unknown when it lands start one refetch (R2), and are departed if that lands without them (R3) |
| A new member's first message arrives live | one refetch; their name replaces the short id in the message list |
| The same id in several places at once (message, DM list, typing) | one refetch; all of them update |
| A message from someone who left | one refetch at most, then the short id, quietly |
| Socket reconnect | the directory is refetched (R5) |
| Workspace switch while a refetch is in flight | the response lands in its own workspace's cache |
| A second tab | heals on its own, by the same rules |

## What this assumes — check before building on it

- **TanStack Query dedupes concurrent fetches of one key**, so `refetchQueries` or
  `invalidateQueries` while a fetch is in flight joins it rather than starting another. Check
  the installed version's behaviour for the call the plan picks (`cancelRefetch` defaults).
- **A render-time lookup can't start a fetch**: `nameFor` is called during render by seven
  components, so the trigger has to happen outside render (an effect, or a store the hook
  drains). How is the plan's; that it isn't in render is not.
- **A fetch that lands without an id proves it departed only if it started after the id was
  seen (R2, R3):** this assumes each fetch is a complete snapshot as of when it ran. It is —
  `workspaceMembers` reads every page — but a member who joins mid-loop can be missed, which the
  follow-up refetch in R2 covers.

## Timing

```
t0     Ada's tab holds the directory [ada]
t1     message_received from grace → nameFor(grace) unknown → refetch starts
t1+5   user_typing from grace → unknown, fetch in flight → nothing new starts
t2     refetch lands [ada, grace] → "grace" everywhere, in one render
       (had it landed without her, she would be departed: the fetch started at t1, when she
        was first seen. Contrast: an id first seen at t1+5, after that fetch started, starts one
        more refetch at t2 if it is missing — R2)
t3     message from alan, who left → unknown → one refetch → still unknown at t4
t4+    alan shows as his short id; more messages from alan start nothing
t5     socket reconnects → refetch (R5) → departed set cleared; alan unknown again after it
```

## Decided already

1. SPA only: no server event, no new route, no change to Auth or Messaging.
2. The short id shows while the refetch is in flight — no placeholder.
3. A departed id refetches at most once per fetch of the directory.
4. Renames are out of scope (below).
5. This depends on no 🔴 register entry. The nearest is **D28** (no user preferences):
   untouched — a display name is not a preference.

Left to the plan, on purpose: where the trigger and the departed set live, and which TanStack
call makes the refetch.

## Tests

- **Vitest** for the hook and one consumer: MSW serves a directory without Grace, then one with
  her; Grace's name replaces her short id; exactly one request for several unknown ids in one
  render; a departed id makes one request then none; no extra request while the first load is
  pending; a reconnect refetches; two workspaces don't share a departed set.
- **No BDD journey.** Dex's users are fixed and Auth's tables aren't truncated between runs, so
  the suite can't produce a first-time joiner cheaply. The acceptance run is the proof.

## Record in this slice

- Doc 06: a short section on how the directory stays fresh — the 5 minutes, an unknown id,
  a reconnect — and that renames are not covered.
- The hook's header comment: the short id is now also the in-flight label, not only "left".
- No register entry and no ADR: this is a fix inside an existing decision.

## Not in this issue

- A display name changed by its owner showing elsewhere before the 5 minutes are up.
- Any membership or profile event from Auth.
- Removing a departed member's messages, or marking them as departed in the UI.

## Acceptance — first real run, on a preview

`scripts/deploy.sh preview up` on the branch (a fresh deploy, so nobody has signed in yet):
- Ada signs in and opens #general. Grace signs in for the first time, in another browser, and
  posts. Ada sees "grace" on the message — briefly the short id at most — without reloading.
- Ada opens the DM list: Grace is listed by name.
- Ada's network drops and returns: nothing shows a short id that showed a name before.

## References

- `src/frontend/src/features/channels/useWorkspaceMembers.ts`
- `src/frontend/src/lib/realtime/useChannelSocket.ts` (`onConnect`)
- `docs/design/06-frontend-spa.md` §5.1, §5.2; `docs/design/02-messaging-service.md` :260-264
- Issue 6's preview run, where this was found
