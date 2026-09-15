# Test gaps backfill — implementation plan

2026-09-15. Follows a coverage review of `main` at `b2b52ca`. On that commit, unit and integration
tests together cover 83% of Python, and Vitest covers 88.6%. That Vitest figure leaves out files no
test imports. Branch `feature/test-gaps-backfill`, worktree `caw-test-gaps`.

Scope, as Elton agreed it: fix the seven bugs the review confirmed, and add the P1 tests it found
missing. P2 and P3 gaps stay out of scope. Decisions taken in the review:

| # | Question | Answer |
|---|---|---|
| 1 | May a workspace admin grant or remove `owner`? | **Yes.** Recorded as register **D36** and in doc 01 |
| 2 | `GET /users/{id}` answers for anyone the caller shares *any* workspace with | Acceptable for now; no change |
| 3 | The readiness 503 body carries exception text | Acceptable; no change |
| 4 | A frozen job-contract wire sample | Not needed: services and the Worker deploy in step |

Decisions taken at red review, before the fixes:

| # | Question | Answer |
|---|---|---|
| 5 | B3: does the string `"true"` count as verified? | No. Only a JSON boolean `true` counts, as the OIDC spec says |
| 6 | B4: what does logout do when R1 is unreachable? | Returns 204, revokes the refresh token, clears the cookie, and logs a warning. The access token lives until it expires |
| 7 | B2: what does a JWKS fetch failure do? | A failed hourly refresh keeps serving cached keys. With no usable key, **503** |
| 8 | B1: what happens to `typing` for a channel the sender can't see? | Dropped silently, at the cost of one visibility query per typing event |
| 9 | B6: where are cursor parts validated? | Once, in `shared.pagination` |
| 10 | "Stream recovers" takes about 47s, waiting on the Socket.IO heartbeat | Ping interval and timeout become env vars, set short on the test stack only |
| 11 | What does the SPA do with a 401 from Messaging, or a network error during renewal? | Not built. Recorded as register **D37** and **D38**, both 🔴 |

Found at red: search accepts a cursor with a part that isn't a UUID and returns a page. Within a
tab, renewal is now single-flight. Across tabs it still isn't, and that needs its own design.

The approach is TDD, and it **stops at red** for review (D32). A test for a bug must fail for the
reason the bug gives. A backfill test pins behaviour that already works, so it passes on arrival.
Each one is proven able to fail by temporarily breaking the line it pins, and that break is
reverted.

## Bugs — the red tests

| # | Bug | Code | Test, layer |
|---|---|---|---|
| B1 | `typing` fans out with no channel visibility check, across workspaces and into private channels | `messaging/realtime_writes.py:325` | integration, `test_realtime_writes.py` |
| B2 | A failed JWKS refresh raises out of `key_for`. Once the cache is an hour old, every request is a 500 while Auth is down | `shared/keys.py:124` | unit, `test_keys.py` |
| B3 | `email_verified` is read with `bool()`, so the string `"false"` counts as verified | `auth/oidc.py:236` | unit, `test_oidc.py` |
| B4 | Logout with R1 unreachable returns 500, the refresh token isn't revoked and the cookie isn't cleared | `auth/routers/auth.py:188` | integration |
| B5 | Framework `HTTPException` detail is never suppressed: the check compares a `str` with the `TITLES` tuple | `shared/problems.py:192` | unit, `test_problems.py` |
| B6 | A cursor that decodes but has the wrong number of parts, or a part that is not a UUID, returns 500 instead of 400 | `messaging/messages.py:186`, `channels.py:272,424`, search | integration |
| B7 | SPA session renewal isn't single-flight, so concurrent calls spend the rotating refresh token twice | `frontend/src/lib/auth/session.ts:102` | Vitest |
| B8 | A token response that isn't JSON raises `ValueError` (a 500) instead of `ProviderError` | `auth/oidc.py:190` | unit, `test_oidc.py` |

## P1 gaps — backfill

**Auth**
- Deleted accounts: refresh, callback, `/users/me` and the member lists.
- `PATCH` members: a plain member and a token for another workspace get 403. Add the missing
  cross-workspace case for `DELETE`.
- The member write routes return 503 when R1 is unreachable.
- Refresh picks up a role change, and keeps the switched workspace.
- A `state` issued for one provider is refused on another provider's callback.
- A new identity with an existing account's email is linked when verified, and refused when not.
- D36: an admin grants and removes `owner`, and a guest may not manage.

**Messaging**
- `test_read_state.py` (new) covers `POST /channels/{id}/read`:
  - 404 for another workspace, a private non-member, and a message from another channel;
  - the marker only moves forward;
  - the unread count;
  - the receipt goes only to the reader's own room.
- Socket `edit_message`, `delete_message` and `mark_read` sent from another workspace, or by a
  private-channel non-member, ack a 404.

**shared / Worker / testkit**
- `alg` of `none` or HS256 is refused.
- A token missing `sub`, `jti` or `exp` is refused.
- An internal-audience token with a non-service subject is refused.
- Worker `main.py`: a stream with no handlers, a consumer crash, a drain on SIGTERM.
- Consumer logs carry no job content.
- `CONTAINER_FIXTURES` lists every container fixture.

**SPA**
- `App.tsx` route guards.
- Switching workspace replaces the socket and the channel cache.
- Member panel controls and cache invalidation.
- A 401 on an API call, and a network failure during renewal: tested only where doc 06 specifies
  the behaviour. Otherwise they are raised as questions.
- The `ChannelList` archive test is flaky: wait on the path.
- `coverage.include`, so untested files count.

**End-to-end**
- Tighten these scenarios:
  - "sends and sees": wait for the confirmed row;
  - "exactly once": count after the confirmed row arrives;
  - "stream recovers": assert the socket dropped first;
  - edit: the edit persists after a reload.
- Replace fixed waits with retrying assertions.
- New journeys:
  - sign out;
  - a signed-out deep link lands on sign-in;
  - switching workspace.

## Outcome

- **B1 `realtime_writes.typing`:** checks visibility with `authorized_channel` and drops the event
  silently otherwise.
- **B2 `shared.keys`:**
  - A failed fetch keeps the cached keys, logs a warning, and retries after the kid-miss floor.
  - `KeySourceUnavailableError` (a subclass of `UnknownKeyError`) becomes 503 in `decode_claims`.
    A kid that a successful fetch did not produce is still 401.
  - Conventions §5.1 is updated.
- **B3 `oidc._identity_from`:** `claims.get("email_verified") is True`.
- **B4 `routers/auth.logout`:**
  - `RedisError` on the denylist write is caught and logs a warning.
  - The refresh token is still revoked and the cookie cleared.
  - Doc 01 and Conventions §5.2 are updated.
- **B5 `shared.problems`:** `detail` is dropped when it equals `HTTPStatus(code).phrase`.
- **B6 `shared.pagination`:**
  - `decode_cursor(parts=…)` and `page_request_for(*parts)` return typed parts. A wrong shape is
    the same 400 with `errors.cursor` as bad base64.
  - Adopted by Messaging history, the channel list, channel members and search.
  - Also by **Auth's workspace members list**, which had the same 500. That was found during the
    fix and test-driven in `test_members.py`.
  - Conventions §4.1 is updated.
- **B7 `session.ts`:**
  - One in-flight cookie spend per tab.
  - **`changeWorkspace` had the same race**: a switch overlapping a renewal replays the cookie.
    It now waits its turn, test-driven with two new tests.
  - Doc 06 §4 is updated.
- **B8 `oidc.exchange`:** a non-JSON body, or JSON that isn't an object, raises `ProviderError`.
- **Ping settings:**
  - New env vars `MESSAGING_SOCKET_PING_INTERVAL_SECONDS` and
    `MESSAGING_SOCKET_PING_TIMEOUT_SECONDS`, defaults 25 and 20.
  - Set to 2 and 2 in `docker-compose.test.yml` only; added to `.env.example` and the chart values.
  - "Stream recovers" now takes 7.7s instead of about 47s.

## Duplicate removal

Elton asked for this once the backfill was green: remove integration tests that only restate what
another test already proves, and lose no behaviour under test. A test was removed only when both
checks below passed:

1. **Assertion by assertion:** every assertion it made is made by a surviving test. Each route
   keeps one integration test proving it applies the rule and returns the right status and
   Problem Details shape.
2. **Mechanically:**
   - Unit and integration ran with `--cov-context=test` and branch coverage.
   - A script over the coverage database listed every branch that only the removed tests reached.
   - The result had to be **zero**.
   - The script was first shown to detect a loss: removing the Worker's SIGTERM test flags 5
     branches.

| Removed | Its assertions are made by |
|---|---|
| auth `test_federation::test_a_new_user_gets_their_own_workspace_and_the_demo_one` | `test_api::test_the_workspace_list_uses_the_standard_envelope`, the same two assertions and more |
| auth `test_federation::test_the_token_is_issued_by_collabhub_not_dex` | `test_api::test_an_issued_token_verifies_against_the_published_jwks` (issuer and audience); unit `test_tokens::test_an_access_token_carries_the_claims_every_service_reads` |
| auth `test_refresh_cookie::test_refreshing_rotates_the_cookie` | `test_api::test_refresh_returns_a_new_pair` |
| auth `test_refresh_cookie::test_switching_workspace_rotates_the_cookie` | `test_api::test_switching_workspace_rotates_the_refresh_token` |
| auth `test_refresh_cookie::test_signing_out_revokes_the_session_the_cookie_named` | `test_api::test_logout_revokes_the_refresh_token_it_is_given`, which makes the same requests |
| auth `test_members::test_a_malformed_cursor_is_a_400` | unit `test_pagination::test_a_malformed_cursor_is_a_validation_error`; the route's wiring is `test_members::test_a_cursor_that_decodes_but_is_not_ours_is_a_400` (3 cases) |
| shared `test_security::test_verify_user_token_refuses_a_bad_token[expired]`, `[issuer]` | `test_an_expired_token_is_rejected` and `test_a_token_from_another_issuer_is_rejected`, which exercise the same function over HTTP. The `[malformed]` case stays, as `test_verify_user_token_refuses_a_malformed_token` |
| messaging `test_channels::test_valid_names_are_accepted` | unit `test_channel_rules::test_a_typeable_name_is_accepted_as_typed[team-42]`; the 201 is in `test_create_returns_the_channel_with_the_caller_as_admin` |
| messaging `test_channels::test_created_channel_is_readable_by_id` | `test_a_public_channel_is_visible_to_a_non_member` (the 200); `test_tenancy::test_a_write_from_another_workspace_changes_nothing` (the returned id) |
| messaging `test_messages::test_a_message_over_the_limit_is_rejected` | unit `test_message_body` (the limit, including off-by-one); `test_the_configured_limit_reports_before_the_static_field_bound` (the 400 and field error). "History stays empty" **moved into** that test. The 8000 default is in `test_an_edit_is_held_to_the_same_body_rules_as_a_send` and `test_realtime_writes::test_an_over_long_body_acks_a_400_with_the_field_error` |
| messaging `test_messages::test_history_is_newest_first` | `test_pagination::test_the_walk_sees_every_message_exactly_once_newest_first` and `::test_the_first_page_is_the_default_limit_and_the_last_is_short` |

Few tests qualified, because plans 04 and 05 had already cut the integration layer to one example
per rule per route. Most remaining integration tests prove something no unit test can, and each
review agent listed every candidate it rejected, with the reason.

## Order

1. Write every red test and backfill test above, in parallel by area. **Stop for review.**
2. Fix B1–B8 until each red test is green.
3. Run `scripts/test.sh all`.
