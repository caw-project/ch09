#!/usr/bin/env bash
# Proves scripts/deliver.sh's state machine with a fake `claude`: no model, no
# cost, a few seconds a scenario. Run it after any change to the script's
# rounds, send-backs, turn caps or context block.
#
#   .claude/delivery/loop-test.sh             every scenario
#   .claude/delivery/loop-test.sh sendback    the scenarios whose name matches
#
# Each scenario gives the fake a script — one verdict per stage run, in order —
# and then checks the exit status, the stages that ran, and what each was told in
# its context block. The verdicts: done, approved, changes_requested, send_back,
# needs_human, and two that aren't an agent's: max_turns (the turn cap) and
# crash (no result at all).
#
# It builds issue 999 in ../caw-issue-999-loop on feature/issue-999-loop, from
# HEAD, and removes both after every scenario. Nothing is committed.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK="$(mktemp -d)"
WORKTREE="$(dirname "$ROOT")/caw-issue-999-loop"
BRANCH=feature/issue-999-loop
trap 'cleanup; rm -rf "$WORK"' EXIT

mkdir -p "$WORK/bin"
printf 'Issue: 999\n\n# Issue 999 — the loop test\n' >"$WORK/issue.md"

# The fake. It takes the next verdict from $FAKE_SCRIPT, records the prompt it
# was given, and writes the file the workflow expects that verdict to leave.
cat >"$WORK/bin/claude" <<'FAKE'
#!/usr/bin/env bash
prompt="" agent="" resumed=""
while [ $# -gt 0 ]; do
    case "$1" in
        -p) prompt="$2"; shift ;;
        --agent) agent="$2"; shift ;;
        --resume) resumed=" resumed"; shift ;;
    esac
    shift
done
verdict="$(head -n 1 "$FAKE_SCRIPT")"
sed -i '' 1d "$FAKE_SCRIPT"
n=$(($(ls "$FAKE_LOG" | wc -l) + 1))
printf '%s\n' "$prompt" >"$FAKE_LOG/$(printf '%02d' "$n")-$agent-$verdict${resumed:+-resumed}.txt"
printf '%s%s %s\n' "$agent" "$resumed" "$verdict" >>"$FAKE_LOG.calls"

# A resumed session still has its context block: the one its first run was given.
[ -z "$resumed" ] || prompt="$(cat "$(ls "$FAKE_LOG"/*-"$agent"-*.txt | grep -v -- '-resumed.txt$' | tail -n 1)")"
field() { printf '%s\n' "$prompt" | sed -n "s/^$1: //p" | head -n 1; }
leave() { mkdir -p "$(dirname "$1")" && printf '%s by %s\n' "$verdict" "$agent" >>"$1"; }
result() {
    printf '{"subtype":"%s","is_error":%s,"num_turns":3,"total_cost_usd":0.5,"duration_ms":60000,"session_id":"fake-session","structured_output":%s}\n' "$1" "$2" "$3"
}
out='{"status":"'"$verdict"'","summary":"fake","files":[],"questions":["what?"]}'
case "$verdict" in
    crash) exit 1 ;;
    max_turns) result error_max_turns true null; exit 1 ;;
    done)
        case "$agent" in
            plan-writer) leave "$(field Plan)" ;;
            test-writer) leave "$(field 'Red report')" ;;
            code-writer) leave "$(field 'Green report')" ;;
        esac
        ;;
    approved | changes_requested) leave "$(field 'Write your review to')" ;;
    send_back)
        leave "$(field 'Send-back file, if you send work back')"
        [ -z "$(field 'Write your review to')" ] || leave "$(field 'Write your review to')"
        ;;
esac
result success false "$out"
FAKE
chmod +x "$WORK/bin/claude"

cleanup() {
    git -C "$ROOT" worktree remove --force "$WORKTREE" >/dev/null 2>&1
    git -C "$ROOT" branch -D "$BRANCH" >/dev/null 2>&1
    return 0
}

failures=0
fail() {
    printf '    FAIL: %s\n' "$*"
    failures=$((failures + 1))
}

# scenario <name> <expected exit> <verdicts…>, then the checks below.
scenario() {
    NAME="$1" expected="$2"
    shift 2
    RAN=false
    case "$NAME" in *"$FILTER"*) ;; *) return 0 ;; esac
    RAN=true
    cleanup
    export FAKE_SCRIPT="$WORK/$NAME.script" FAKE_LOG="$WORK/$NAME.log"
    rm -rf "$FAKE_LOG" "$FAKE_LOG.calls" && mkdir -p "$FAKE_LOG"
    printf '%s\n' "$@" >"$FAKE_SCRIPT"
    printf '%s\n' "$NAME"
    PATH="$WORK/bin:$PATH" DELIVER_RUN=loop DELIVER_BASE=HEAD DELIVER_RETRY_WAIT=0 \
        "$ROOT/scripts/deliver.sh" "$WORK/issue.md" >"$FAKE_LOG.out" 2>&1
    status=$?
    [ "$status" = "$expected" ] || fail "exit $status, expected $expected — $(tail -n 3 "$FAKE_LOG.out" | tr '\n' ' ')"
    [ ! -s "$FAKE_SCRIPT" ] || fail "verdicts left unused: $(tr '\n' ' ' <"$FAKE_SCRIPT")"
}

# The context block the nth call was given.
block() { cat "$FAKE_LOG"/"$(printf '%02d' "$1")"-*.txt 2>/dev/null; }
# told <call> <text>, not_told <call> <text> — what a stage's context block held.
told() { ! $RAN || block "$1" | grep -qF -- "$2" || fail "call $1 was not told '$2': $(block "$1" | tr '\n' '|')"; }
not_told() { ! $RAN || ! block "$1" | grep -qF -- "$2" || fail "call $1 was told '$2'"; }
# ran <stages…> — the stages that ran, in order.
ran() { ! $RAN || [ "$(cut -d' ' -f1 "$FAKE_LOG.calls" | tr '\n' ' ')" = "$* " ] || fail "ran: $(cut -d' ' -f1 "$FAKE_LOG.calls" | tr '\n' ' ')"; }
exists() { ! $RAN || [ -s "$WORKTREE/docs/plans/issue-999/$1" ] || fail "no $1"; }
history_has() { ! $RAN || grep -qE -- "$1" "$WORKTREE/build/delivery/history.log" || fail "history.log has no '$1'"; }

FILTER="${1:-}"
REVIEWS=docs/plans/issue-999/reviews

scenario straight-through 0 done approved done approved done approved
ran plan-writer plan-reviewer test-writer test-reviewer code-writer code-reviewer
told 1 'Stage: plan-writer, round 1 of 3'
told 1 'Turns: 150'
told 3 'Turns: 200'
told 5 'Turns: 250'
not_told 5 'Rework pass'
history_has '^01 plan-writer done \[1m 3 turns \$0.5\]: fake'

scenario three-rounds-then-a-human 2 done changes_requested done changes_requested done changes_requested
told 3 "Review to address: $REVIEWS/plan-reviewer-1.md"
told 3 'Rework pass: yes — 100 turns'
told 5 'Final round: yes — 60 turns'
told 6 'Final round: yes'
exists reviews/plan-reviewer-3.md
exists needs-human.md

scenario approved-in-round-two 0 done changes_requested done approved done approved done approved
told 4 'Stage: plan-reviewer, round 2 of 3'
told 4 'Rework pass'
told 5 'Stage: test-writer, round 1 of 3'
told 5 'Turns: 200'

# A reviewer sends back: its pair's round advances, its review survives, and its
# own writer gets that review when the flow comes forward.
scenario reviewer-sendback 0 done approved done send_back done approved done approved done approved
ran plan-writer plan-reviewer test-writer test-reviewer plan-writer plan-reviewer test-writer test-reviewer code-writer code-reviewer
told 4 "Send-back file, if you send work back: $REVIEWS/test-reviewer-sendback-2.md"
told 5 'Stage: plan-writer, round 2 of 3'
told 5 "Review to address: $REVIEWS/test-reviewer-sendback-2.md"
not_told 5 'After a send-back'
told 6 "After a send-back by test-reviewer: $REVIEWS/test-reviewer-sendback-2.md"
told 6 'Changed since the send-back by test-reviewer: docs/plans/issue-999/01-implementation-plan.md'
told 7 "Review to address: $REVIEWS/test-reviewer-1.md"
told 7 'After a send-back by test-reviewer'
told 7 'Stage: test-writer, round 2 of 3'
told 7 'Rework pass'
told 8 "Write your review to: $REVIEWS/test-reviewer-2.md"
told 8 'After a send-back by test-reviewer'
not_told 8 'Final round'
not_told 9 'After a send-back'
told 9 'Turns: 250'
exists reviews/test-reviewer-1.md
exists reviews/test-reviewer-2.md

# A writer sends back: no review of its own, its round stays, and it comes back
# to a first pass's turns.
scenario writer-sendback 0 done approved done approved send_back done approved done approved
ran plan-writer plan-reviewer test-writer test-reviewer code-writer test-writer test-reviewer code-writer code-reviewer
told 6 "Review to address: $REVIEWS/code-writer-sendback-2.md"
told 6 'Stage: test-writer, round 2 of 3'
told 7 'After a send-back by code-writer'
told 8 'After a send-back by code-writer'
told 8 'Stage: code-writer, round 1 of 3'
told 8 'Turns: 250'
not_told 8 'Review to address'
not_told 9 'After a send-back'

scenario code-reviewer-sendback 0 done approved done approved done send_back done approved done approved
told 9 "Review to address: $REVIEWS/code-reviewer-1.md"
told 9 'After a send-back by code-reviewer'
told 9 'Stage: code-writer, round 2 of 3'
told 10 "Write your review to: $REVIEWS/code-reviewer-2.md"

# A send-back never lands in a final round: the plan pair has used its three,
# and still gets an ordinary review and a final one.
scenario sendback-after-three-rounds 0 done changes_requested done changes_requested done approved \
    done send_back done changes_requested done approved done approved done approved
told 9 'Stage: plan-writer, round 4 of 5'
not_told 9 'Final round'
told 11 'Stage: plan-writer, round 5 of 5'
told 11 'Final round: yes'

# Two send-backs open at once: the code-reviewer's, then the test-reviewer's.
scenario nested-sendbacks 0 done approved done approved done send_back \
    done send_back done approved done approved done approved
ran plan-writer plan-reviewer test-writer test-reviewer code-writer code-reviewer \
    test-writer test-reviewer plan-writer plan-reviewer test-writer test-reviewer code-writer code-reviewer
told 10 'After a send-back by test-reviewer'
told 10 'After a send-back by code-reviewer'
told 13 'After a send-back by code-reviewer'
not_told 13 'After a send-back by test-reviewer'
told 13 "Review to address: $REVIEWS/code-reviewer-1.md"

scenario too-many-sendbacks 2 done approved done send_back done approved done send_back \
    done approved done send_back done approved done send_back
exists needs-human.md

# Out of turns: resumed once in the same session; twice is a human's.
scenario out-of-turns-resumed 0 max_turns done approved done approved done approved
ran plan-writer plan-writer plan-reviewer test-writer test-reviewer code-writer code-reviewer
told 2 'You ran out of turns'
told 2 '75 more turns'
history_has '^01 plan-writer done \[2m 6 turns \$1\]'

scenario out-of-turns-twice 2 max_turns max_turns
exists needs-human.md

scenario crash-then-rerun 0 crash done approved done approved done approved
ran plan-writer plan-writer plan-reviewer test-writer test-reviewer code-writer code-reviewer
told 2 'Stage: plan-writer, round 1 of 3'

scenario crash-twice 1 crash crash

scenario asks-a-human 2 done needs_human
exists needs-human.md

echo
if [ "$failures" -gt 0 ]; then
    echo "$failures check(s) failed. Each scenario's output: $WORK/<name>.log.out"
    trap cleanup EXIT
    exit 1
fi
echo "Every scenario passed."
