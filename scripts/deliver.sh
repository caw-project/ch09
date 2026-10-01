#!/usr/bin/env bash
# Take one issue from a text file to a tested feature ready for review, with the
# delivery agents in .claude/agents/ doing the work. Nothing is committed.
#
#   scripts/deliver.sh issues/42.md             start, or carry on from where it stopped
#   scripts/deliver.sh issues/42.md --restart   forget progress and start at plan-writer
#
# The issue file must name its number near the top — `Issue: 42`, `Issue #42`
# or `# Issue 42 — Pin a message`. The work happens in the worktree
# ../caw-issue-<N>, on branch feature/issue-<N>, created from main if missing.
#
# Six stages, a writer and a reviewer for each of plan, tests and code. What
# every agent needs to know about this workflow — the context block, rounds, the
# final round, escalation — is in .claude/delivery/agent-context.md; keep it in
# step with this script.
#
#   plan-writer -> plan-reviewer -> test-writer -> test-reviewer -> code-writer -> code-reviewer -> done
#
#   a writer returns    done               on to its reviewer
#   a reviewer returns  approved           on to the next writer, or done
#                       changes_requested  back to its writer, with the review
#   a later stage       send_back          back to the writer of the pair before
#     returns                                its own, with why in a send-back file
#   any agent returns   needs_human        stop; questions in needs-human.md
#
# A send-back is for work an earlier pair owns and a later stage finds wrong — a
# test the code-writer can't pass because the test is broken, a plan the tests
# can't be written to. The stage writes why to the send-back file its context
# block names, and stops. The earlier pair takes a new round: its writer answers
# the file as it answers a review, its reviewer gates the fix, and the workflow
# comes forward from there as usual. The stage that sent it back is told, when
# it runs again, what it is resuming after. Test stages send back to the
# plan-writer, code stages to the test-writer; the plan pair can't send back.
#
# A writer and its reviewer get DELIVER_MAX_ROUNDS reviews (default 3). The last
# is the final round, and it is cut down so a disagreement cannot run on: both
# agents get fewer turns and less effort, and are told so. The final reviewer
# may only approve — leaving minor findings to the stages after it — or stop for
# a human over something critical or a deadlock; `changes_requested` there stops
# for a human too. A stage that runs out of turns stops for a human as well.
#
# Answer the questions under each **Answer:** in
# docs/plans/issue-<N>/needs-human.md, then run the same command again: it
# resumes at the stage that stopped, and every agent reads the answers. Rounds
# past the limit stay final rounds, so every one comes back through a human.
#
# A stage whose agent is not written yet pauses the workflow the same way; run
# it again once the agent exists.
#
#   DELIVER_MAX_ROUNDS       reviews per writer/reviewer pair. Default: 3
#   DELIVER_MAX_TURNS        turns for a stage before the final round — a guard
#                            against a runaway, not a budget. Default: 150
#   DELIVER_FINAL_MAX_TURNS  turns for a stage in the final round. Default: 40
#   DELIVER_FINAL_EFFORT     effort for a stage in the final round. Default: medium
#   DELIVER_BASE             the branch a new worktree starts from. Default: main
#   DELIVER_MODEL            overrides every agent's model, e.g. for a cheap dry run
#   DELIVER_PERMISSION_MODE  default: dontAsk — anything a stage is not allowed
#                            below is refused, never prompted for
#
# Exit status: 0 done · 1 error · 2 needs a human · 3 paused at an unbuilt stage.
# Progress and every agent's full JSON result are in build/delivery/ in the
# worktree.
#
set -euo pipefail
# shellcheck source=lib/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

STAGES=(plan-writer plan-reviewer test-writer test-reviewer code-writer code-reviewer)

DELIVER_MAX_ROUNDS="${DELIVER_MAX_ROUNDS:-3}"
DELIVER_MAX_TURNS="${DELIVER_MAX_TURNS:-150}"
DELIVER_FINAL_MAX_TURNS="${DELIVER_FINAL_MAX_TURNS:-40}"
DELIVER_FINAL_EFFORT="${DELIVER_FINAL_EFFORT:-medium}"
DELIVER_BASE="${DELIVER_BASE:-main}"
DELIVER_MODEL="${DELIVER_MODEL:-}"
DELIVER_PERMISSION_MODE="${DELIVER_PERMISSION_MODE:-dontAsk}"

# What every agent returns. The status a stage may use depends on its role, and
# is checked below, not here, so one schema serves all six. --json-schema works
# through a StructuredOutput tool, and an agent's `tools:` line is an allowlist that
# drops it — so every agent in .claude/agents/ must list StructuredOutput, or it
# writes its JSON as text and the stage fails with "no structured result".
RESULT_SCHEMA='{
  "type": "object",
  "properties": {
    "status":    {"type": "string", "enum": ["done", "approved", "changes_requested", "send_back", "needs_human"]},
    "summary":   {"type": "string"},
    "files":     {"type": "array", "items": {"type": "string"}},
    "questions": {"type": "array", "items": {"type": "string"}}
  },
  "required": ["status", "summary", "files", "questions"],
  "additionalProperties": false
}'

issue_file=""
restart=false
while [ $# -gt 0 ]; do
    case "$1" in
        --restart) restart=true ;;
        -h | --help)
            usage
            exit 0
            ;;
        -*) die "unknown option '$1'" ;;
        *)
            [ -z "$issue_file" ] || die "one issue file at a time"
            issue_file="$1"
            ;;
    esac
    shift
done
[ -n "$issue_file" ] || die "usage: scripts/deliver.sh <issue-file> [--restart]"
[ -f "$issue_file" ] || die "no such issue file: $issue_file"
for setting in DELIVER_MAX_ROUNDS DELIVER_MAX_TURNS DELIVER_FINAL_MAX_TURNS; do
    case "${!setting}" in
        '' | *[!0-9]* | 0) die "$setting must be a positive number" ;;
    esac
done
case "$DELIVER_FINAL_EFFORT" in
    low | medium | high | xhigh | max) ;;
    *) die "DELIVER_FINAL_EFFORT must be low, medium, high, xhigh or max" ;;
esac

# --- pre-flight -----------------------------------------------------------------
#
# Everything a run needs from this machine, checked before the first stage. The
# stages that need most of it come last: the test pair installs and runs Vitest
# and pytest, and the code-writer's verification runs scripts/test.sh, whose e2e
# layer builds the Compose test stack. A missing tool found there costs every
# stage before it. Lists every problem at once, so one fix-and-rerun is enough.
preflight() {
    local problems=() cmd
    # The workflow itself; what stages run (tests, lint, the scripts' layers).
    for cmd in claude git jq uv node npm python3 helm docker; do
        command -v "$cmd" >/dev/null 2>&1 || problems+=("'$cmd' is not on PATH")
    done
    if command -v docker >/dev/null 2>&1; then
        docker info >/dev/null 2>&1 ||
            problems+=("the Docker daemon is not reachable — the code-writer's e2e run needs it")
        docker compose version >/dev/null 2>&1 ||
            problems+=("'docker compose' (v2) is not available — the e2e layer brings its stack up with it")
    fi
    [ -f "$REPO_ROOT/.env.example" ] ||
        problems+=(".env.example is missing — a worktree's .env is made from it for the e2e layer")
    if [ ${#problems[@]} -gt 0 ]; then
        log "Pre-flight failed — fix these, then run this again:"
        printf '  - %s\n' "${problems[@]}" >&2
        exit 1
    fi
}
preflight

issue_file="$(cd "$(dirname "$issue_file")" && pwd)/$(basename "$issue_file")"
ISSUE="$(head -n 20 "$issue_file" | grep -m1 -oiE 'issue[[:space:]:#]*[0-9]+' | grep -oE '[0-9]+' || true)"
[ -n "$ISSUE" ] || die "$issue_file names no issue number in its first 20 lines (e.g. 'Issue: 42')"

BRANCH="feature/issue-$ISSUE"
WORKTREE="$(dirname "$REPO_ROOT")/caw-issue-$ISSUE"

# Paths the agents see are relative to the worktree root.
PLAN_DIR="docs/plans/issue-$ISSUE"
ISSUE_COPY="$PLAN_DIR/00-issue.md"
PLAN="$PLAN_DIR/01-implementation-plan.md"
RED_REPORT="$PLAN_DIR/02-red-tests.md"
GREEN_REPORT="$PLAN_DIR/03-green-report.md"
ANSWERS="$PLAN_DIR/needs-human.md"

RUN_DIR="$WORKTREE/build/delivery"
STATE="$RUN_DIR/state"

# --- the worktree -------------------------------------------------------------

if [ ! -d "$WORKTREE" ]; then
    if git -C "$REPO_ROOT" show-ref --verify --quiet "refs/heads/$BRANCH"; then
        log "Worktree $WORKTREE on the existing $BRANCH"
        git -C "$REPO_ROOT" worktree add "$WORKTREE" "$BRANCH" >&2
    else
        log "Worktree $WORKTREE on a new $BRANCH from $DELIVER_BASE"
        git -C "$REPO_ROOT" worktree add -b "$BRANCH" "$WORKTREE" "$DELIVER_BASE" >&2
    fi
fi
[ "$(git -C "$WORKTREE" branch --show-current)" = "$BRANCH" ] ||
    die "$WORKTREE is not on $BRANCH — move it or remove it"

mkdir -p "$RUN_DIR" "$WORKTREE/$PLAN_DIR"
# The e2e layer's Compose files read .env, which git ignores, so a new worktree
# has none. The example is the full contract with local values — what a
# developer starts from too.
[ -f "$WORKTREE/.env" ] || cp "$WORKTREE/.env.example" "$WORKTREE/.env"
# The issue travels with its plan, as a design doc does. Copied every run, so an
# issue edited to answer a question reaches the agents that read it.
cp "$issue_file" "$WORKTREE/$ISSUE_COPY"

# --- state --------------------------------------------------------------------
#
# A sourced file of plain assignments — bash 3.2 has no associative arrays, so
# the round count for each pair is its own variable.

STAGE=plan-writer
STATUS=running
STEP=0
REVIEW=""
ROUNDS_plan=1 ROUNDS_test=1 ROUNDS_code=1
# The stage waiting on a send-back, and the file that says why.
SENT_BACK_BY="" SENT_BACK_FILE=""

if $restart; then
    rm -f "$STATE"
elif [ -f "$STATE" ]; then
    # shellcheck source=/dev/null
    source "$STATE"
fi

save_state() {
    {
        printf 'STAGE=%q\nSTATUS=%q\nSTEP=%q\nREVIEW=%q\n' "$STAGE" "$STATUS" "$STEP" "$REVIEW"
        printf 'ROUNDS_plan=%q ROUNDS_test=%q ROUNDS_code=%q\n' "$ROUNDS_plan" "$ROUNDS_test" "$ROUNDS_code"
        printf 'SENT_BACK_BY=%q SENT_BACK_FILE=%q\n' "$SENT_BACK_BY" "$SENT_BACK_FILE"
    } >"$STATE"
}

pair_of() { printf '%s' "${1%-*}"; }  # plan-writer -> plan
role_of() { printf '%s' "${1##*-}"; } # plan-writer -> writer

rounds_of() { eval "printf '%s' \"\$ROUNDS_$1\""; }
set_rounds() { eval "ROUNDS_$1=$2"; }

# The pair's last permitted review — and every round after it, which only a
# human's answers can reach.
is_final_round() { [ "$(rounds_of "$(pair_of "$1")")" -ge "$DELIVER_MAX_ROUNDS" ]; }

turns_for() {
    if is_final_round "$1"; then printf '%s' "$DELIVER_FINAL_MAX_TURNS"; else printf '%s' "$DELIVER_MAX_TURNS"; fi
}

# The stage after this one, or `done`.
next_stage() {
    local i
    for i in "${!STAGES[@]}"; do
        if [ "${STAGES[$i]}" = "$1" ]; then
            printf '%s' "${STAGES[$((i + 1))]:-done}"
            return
        fi
    done
    die "unknown stage '$1'"
}

# A reviewer's review, one file per round so the writer's history survives.
review_path() { printf '%s/reviews/%s-%s.md' "$PLAN_DIR" "$1" "$(rounds_of "$(pair_of "$1")")"; }

# The pair a stage sends back to, or nothing for the plan pair.
earlier_pair() {
    case "$(pair_of "$1")" in
        test) printf plan ;;
        code) printf test ;;
    esac
}

# Where a stage writes why it sends work back — numbered by the round the
# earlier pair will take it in, so each send-back keeps its own file.
sendback_path() {
    local earlier
    earlier="$(earlier_pair "$1")"
    printf '%s/reviews/%s-sendback-%s.md' "$PLAN_DIR" "$1" "$(($(rounds_of "$earlier") + 1))"
}

# --- what each stage may do ---------------------------------------------------
#
# In dontAsk mode a tool not listed here is refused, so this list is the stage's
# whole reach. Each stage's entry is added with its agent.

# Looking around the repo and its history — every stage has these.
read_only_bash() {
    printf '%s\n' \
        'Bash(git log *)' 'Bash(git show *)' 'Bash(git diff *)' \
        'Bash(git status *)' 'Bash(git worktree list*)' 'Bash(git branch *)' \
        'Bash(git merge-base *)' 'Bash(ls *)' 'Bash(wc *)'
}

# Running tests one file at a time. Never scripts/test.sh: it rewrites the
# committed docs/test-report.md, and runs every layer when a stage needs one
# file. Nothing here can reach the e2e stack.
test_bash() {
    printf '%s\n' \
        'Bash(npm --prefix src/frontend test*)' \
        'Bash(npm --prefix src/frontend run typecheck*)' \
        'Bash(npm --prefix src/frontend run lint*)' \
        'Bash(uv run pytest *)' 'Bash(uv sync*)'
}

allowed_tools() {
    case "$1" in
        plan-writer)
            printf '%s\n' Read Grep Glob Write Edit Skill
            read_only_bash
            ;;
        # Writes only its review, so no Edit: it never touches the plan.
        plan-reviewer)
            printf '%s\n' Read Grep Glob Write Skill
            read_only_bash
            ;;
        # The first stage that runs anything, so the first that installs: a
        # worktree has no node_modules/ or .venv/ until it does (both ignored,
        # so the write check never sees them). `npm ci`, never `npm install`,
        # which rewrites the lockfile.
        test-writer)
            printf '%s\n' Read Grep Glob Write Edit Skill \
                'Bash(npm --prefix src/frontend ci*)' 'Bash(uv run ruff *)'
            read_only_bash
            test_bash
            ;;
        # Runs the tests to see them fail, and writes only its review. Edit and
        # the sketch are for a throwaway implementation under build/sketch/,
        # which is ignored — the write check still holds it to its review.
        test-reviewer)
            printf '%s\n' Read Grep Glob Write Edit Skill 'Bash(.claude/delivery/sketch.sh *)'
            read_only_bash
            test_bash
            ;;
        # Builds until the tests pass, then verifies the whole branch: the only
        # stage that runs scripts/test.sh, because its final run writes the
        # committed docs/test-report.md that goes with the code. e2e brings up
        # the Compose test stack, one run per machine at a time. The contract
        # regeneration is here for an issue that changes an API.
        code-writer)
            printf '%s\n' Read Grep Glob Write Edit Skill \
                'Bash(npm --prefix src/frontend ci*)' \
                'Bash(npm --prefix src/frontend run build*)' \
                'Bash(npm --prefix src/frontend run generate:api*)' \
                'Bash(uv run ruff *)' 'Bash(uv run alembic *)' 'Bash(uv run python -m *)' \
                'Bash(scripts/test.sh *)' \
                'Bash(python3 .claude/hooks/checks/conventions.py*)' \
                'Bash(.claude/hooks/security.sh*)'
            read_only_bash
            test_bash
            ;;
        # Runs every check but scripts/test.sh, whose layers it reads from the
        # report the code-writer left, and writes only its review. The sketch is
        # the real code copied under build/sketch/, broken on purpose to see
        # which mistakes the tests would catch.
        code-reviewer)
            printf '%s\n' Read Grep Glob Write Edit Skill 'Bash(.claude/delivery/sketch.sh *)' \
                'Bash(npm --prefix src/frontend run build*)' \
                'Bash(python3 .claude/hooks/checks/conventions.py*)'
            read_only_bash
            test_bash
            ;;
        *) die "no tools are allowed for $1 yet — add its entry to allowed_tools" ;;
    esac
}

# Where a stage may write, as an extended regex over paths relative to the
# worktree root. Checked after it runs; unset means the stage is not confined.
write_scope() {
    case "$1" in
        plan-writer) printf '^%s/' "$PLAN_DIR" ;;
        plan-reviewer) printf '^%s/reviews/' "$PLAN_DIR" ;;
        # Tests wherever each layer keeps them, the helpers they share, and the
        # red report — never production code, config or docs.
        test-writer)
            printf '^(%s|%s|%s|%s|%s|%s)' \
                'src/frontend/src/.*\.test\.tsx?$' 'src/frontend/src/test/' \
                'src/services/[^/]+/tests/' 'src/services/testkit/' 'tests/bdd/' \
                "$RED_REPORT\$|$PLAN_DIR/reviews/test-writer-sendback-"
            ;;
        test-reviewer) printf '^%s/reviews/' "$PLAN_DIR" ;;
        # Production code, config and docs anywhere — then write_denied takes
        # the tests back out. The plan only for its *Found while building*.
        code-reviewer) printf '^%s/reviews/' "$PLAN_DIR" ;;
        code-writer) printf '^(src/|docs/|charts/|docker/|scripts/|\.env\.example$|docker-compose)' ;;
    esac
}

# Paths a stage may never write, even inside its scope. The code-writer builds
# to the approved red set: a test changed after the gate undoes the gate.
write_denied() {
    case "$1" in
        code-writer)
            printf '^(%s|%s|%s|%s|%s|%s|%s)' \
                'src/frontend/src/.*\.test\.tsx?$' 'src/frontend/src/test/' \
                'src/services/[^/]+/tests/' 'src/services/testkit/' 'tests/' \
                "$RED_REPORT\$" "$PLAN_DIR/reviews/[a-z]+-reviewer-"
            ;;
    esac
}

# The file a writer must leave behind when it says `done`.
writer_output() {
    case "$1" in
        plan-writer) printf '%s' "$PLAN" ;;
        test-writer) printf '%s' "$RED_REPORT" ;;
        code-writer) printf '%s' "$GREEN_REPORT" ;;
    esac
}

# --- running one stage --------------------------------------------------------

context_block() {
    local stage="$1" pair
    pair="$(pair_of "$stage")"
    printf 'Issue: #%s\n' "$ISSUE"
    printf 'Issue file: %s\n' "$ISSUE_COPY"
    printf 'Plan: %s\n' "$PLAN"
    # From the test pair on: the failing tests, as the test-writer reports them.
    case "$pair" in
        test | code) printf 'Red report: %s\n' "$RED_REPORT" ;;
    esac
    # The code pair: what was built, and what ran, as the code-writer reports it.
    [ "$pair" != code ] || printf 'Green report: %s\n' "$GREEN_REPORT"
    printf 'Worktree: %s (branch %s)\n' "$WORKTREE" "$BRANCH"
    printf 'Stage: %s, round %s of %s\n' "$stage" "$(rounds_of "$pair")" "$DELIVER_MAX_ROUNDS"
    if is_final_round "$stage"; then
        printf 'Final round: yes — %s turns. Follow your *Final round* rules.\n' "$(turns_for "$stage")"
    else
        printf 'Turns: %s\n' "$(turns_for "$stage")"
    fi
    if [ "$(role_of "$stage")" = writer ] && [ -n "$REVIEW" ]; then
        printf 'Review to address: %s\n' "$REVIEW"
    fi
    if [ "$(role_of "$stage")" = reviewer ]; then
        printf 'Write your review to: %s\n' "$(review_path "$stage")"
    fi
    # Every review so far, approvals included — a final reviewer's approval can
    # leave minor findings for the stages after it to pick up.
    if [ -n "$(ls "$WORKTREE/$PLAN_DIR/reviews" 2>/dev/null)" ]; then
        printf 'Earlier reviews: %s/reviews/\n' "$PLAN_DIR"
    fi
    if [ -s "$WORKTREE/$ANSWERS" ]; then
        printf 'Human answers: %s\n' "$ANSWERS"
    fi
    if [ -n "$(earlier_pair "$stage")" ]; then
        printf 'Send-back file, if you send work back: %s\n' "$(sendback_path "$stage")"
    fi
    # Every stage the flow passes through on its way back to the stage that sent
    # work back — the work each takes over has changed since it last saw it.
    if [ -n "$SENT_BACK_BY" ] && [ "$REVIEW" != "$SENT_BACK_FILE" ]; then
        printf 'After a send-back by %s: %s\n' "$SENT_BACK_BY" "$SENT_BACK_FILE"
    fi
}

# Every uncommitted path outside build/, tracked or not, with a hash of what is
# in it now. Two snapshots differ exactly where a stage wrote.
snapshot() {
    local path
    git -C "$WORKTREE" status --porcelain --untracked-files=all |
        sed 's/^...//; s/.* -> //' | grep -v '^build/' |
        while IFS= read -r path; do
            printf '%s %s\n' "$(git -C "$WORKTREE" hash-object "$path" 2>/dev/null || echo deleted)" "$path"
        done | sort || true
}

# The paths whose line differs between two snapshots.
touched_between() {
    comm -3 <(printf '%s\n' "$1") <(printf '%s\n' "$2") |
        sed 's/^[[:space:]]*[^ ]* //' | grep -v '^$' | sort -u || true
}

# Runs a stage and prints its structured result as compact JSON. Called in a
# subshell, so it changes no state: the caller counts $STEP. Bash 3.2 does not
# carry errexit into a command substitution, hence the set -e.
run_stage() {
    set -e
    local stage="$1" out head before scope strays prompt tool_list t turns subtype round
    out="$RUN_DIR/$(printf '%02d' "$STEP")-$stage.json"
    prompt="$(context_block "$stage")"
    tool_list="$(allowed_tools "$stage")"
    local tools=()
    while IFS= read -r t; do tools+=("$t"); done <<<"$tool_list"
    turns="$(turns_for "$stage")"
    round="$(rounds_of "$(pair_of "$stage")")"
    local extra_args=(--max-turns "$turns")
    [ -z "$DELIVER_MODEL" ] || extra_args+=(--model "$DELIVER_MODEL")
    ! is_final_round "$stage" || extra_args+=(--effort "$DELIVER_FINAL_EFFORT")

    log "$stage — round $round, $turns turns (log: ${out#"$WORKTREE"/})"
    head="$(git -C "$WORKTREE" rev-parse HEAD)"
    before="$(snapshot)"
    # A stage that runs out of turns exits non-zero with a JSON result, so the
    # result decides whether this failed, not the exit status.
    (cd "$WORKTREE" && claude -p "$prompt" \
        --agent "$stage" \
        --output-format json \
        --json-schema "$RESULT_SCHEMA" \
        --permission-mode "$DELIVER_PERMISSION_MODE" \
        --allowedTools "${tools[@]}" \
        "${extra_args[@]}") >"$out" || true
    subtype="$(jq -r '.subtype // empty' "$out" 2>/dev/null || true)"
    [ -n "$subtype" ] || die "$stage failed — see $out"

    # The rules no agent may break, checked rather than trusted — before anything
    # else, because a stage stopped mid-way may still have broken one.
    [ "$(git -C "$WORKTREE" rev-parse HEAD)" = "$head" ] ||
        die "$stage committed — the workflow never commits. Inspect $BRANCH before rerunning"
    scope="$(write_scope "$stage")"
    if [ -n "$scope" ]; then
        strays="$(touched_between "$before" "$(snapshot)" | grep -Ev "$scope" || true)"
        [ -z "$strays" ] || die "$stage wrote outside $scope:
$strays"
    fi
    scope="$(write_denied "$stage")"
    if [ -n "$scope" ]; then
        strays="$(touched_between "$before" "$(snapshot)" | grep -E "$scope" || true)"
        [ -z "$strays" ] || die "$stage wrote where it may not, $scope:
$strays"
    fi

    # Out of turns is the cap working, not a crash: hand it to a human as a
    # needs_human result, with its partial work left where it is.
    if [ "$subtype" = error_max_turns ]; then
        jq -nc --arg stage "$stage" --arg turns "$turns" --arg round "$round" --arg out "${out#"$WORKTREE"/}" '{
            status: "needs_human",
            summary: "\($stage) used all \($turns) turns in round \($round) without finishing. Its transcript is in \($out); anything it wrote is left in place.",
            files: [],
            questions: ["\($stage) ran out of turns. Rerun it as it is, rerun with a larger DELIVER_MAX_TURNS or DELIVER_FINAL_MAX_TURNS, or answer here what it was stuck on — which?"]
        }'
        return
    fi

    [ "$(jq -r '.is_error' "$out")" = false ] || die "$stage ended in error ($subtype) — see $out"
    jq -e '.structured_output.status' "$out" >/dev/null ||
        die "$stage returned no structured result — see $out"

    jq -c '.structured_output' "$out"
}

# Appends a stop to needs-human.md, with a space under each question to answer.
record_needs_human() {
    local stage="$1" summary="$2" questions="$3"
    {
        [ -s "$WORKTREE/$ANSWERS" ] || printf '# Issue #%s — questions for a human\n' "$ISSUE"
        printf '\n## %s stopped, round %s\n\n%s\n\n' "$stage" "$(rounds_of "$(pair_of "$stage")")" "$summary"
        printf '%s\n' "$questions" | jq -r 'to_entries[] | "\(.key + 1). \(.value)\n\n   **Answer:**\n"'
    } >>"$WORKTREE/$ANSWERS"
}

stop_for_human() {
    STATUS=needs_human
    save_state
    log "Needs a human: answer the questions in $WORKTREE/$ANSWERS, then run this again"
    exit 2
}

# --- the state machine --------------------------------------------------------

case "$STATUS" in
    done)
        log "Issue #$ISSUE is already done — see $WORKTREE. --restart to plan it again"
        exit 0
        ;;
    needs_human) log "Resuming at $STAGE with the answers in $ANSWERS" ;;
esac
STATUS=running
save_state

while [ "$STAGE" != done ]; do
    if [ ! -f "$WORKTREE/.claude/agents/$STAGE.md" ]; then
        save_state
        log "Paused: $STAGE has no agent in .claude/agents/ yet. Run this again once it has"
        exit 3
    fi

    STEP=$((STEP + 1))
    result="$(run_stage "$STAGE")"
    status="$(jq -r '.status' <<<"$result")"
    summary="$(jq -r '.summary' <<<"$result")"
    printf '%02d %s %s: %s\n' "$STEP" "$STAGE" "$status" "$summary" >>"$RUN_DIR/history.log"
    log "$STAGE: $status — $summary"

    pair="$(pair_of "$STAGE")"
    # The stage a send-back was waiting on has now run with it in view.
    [ "$SENT_BACK_BY" != "$STAGE" ] || SENT_BACK_BY="" SENT_BACK_FILE=""
    case "$(role_of "$STAGE"):$status" in
        writer:done)
            output="$(writer_output "$STAGE")"
            [ -z "$output" ] || [ -s "$WORKTREE/$output" ] ||
                die "$STAGE said done but wrote no $output"
            REVIEW=""
            STAGE="$(next_stage "$STAGE")"
            ;;
        reviewer:approved)
            # An approval writes its review too: it is the record of what was
            # checked, and of any minor findings left for later stages.
            [ -s "$WORKTREE/$(review_path "$STAGE")" ] ||
                die "$STAGE approved but wrote no $(review_path "$STAGE")"
            REVIEW=""
            STAGE="$(next_stage "$STAGE")"
            ;;
        reviewer:changes_requested)
            REVIEW="$(review_path "$STAGE")"
            [ -s "$WORKTREE/$REVIEW" ] || die "$STAGE asked for changes but wrote no $REVIEW"
            rounds="$(rounds_of "$pair")"
            # The final reviewer is told to approve or escalate, never to send
            # the plan back — if it does anyway, a human settles it.
            if [ "$rounds" -ge "$DELIVER_MAX_ROUNDS" ]; then
                record_needs_human "$STAGE" \
                    "The $pair reviewer asked for changes in the final round ($rounds of $DELIVER_MAX_ROUNDS), where it may only approve or escalate. The last review is $REVIEW, and the writer's answers to it are in its Review responses." \
                    '["Settle the findings in the last review that are still open: which should the writer take, and which should the reviewer drop?"]'
            fi
            # The writer takes the review, and the answers too when there are
            # some — every round past the limit comes back through a human.
            set_rounds "$pair" $((rounds + 1))
            STAGE="$pair-writer"
            [ "$rounds" -lt "$DELIVER_MAX_ROUNDS" ] || stop_for_human
            ;;
        *:send_back)
            earlier="$(earlier_pair "$STAGE")"
            [ -n "$earlier" ] || die "$STAGE may not send work back — there is no pair before it"
            file="$(sendback_path "$STAGE")"
            [ -s "$WORKTREE/$file" ] || die "$STAGE sent work back but wrote no $file"
            rounds=$(($(rounds_of "$earlier") + 1))
            set_rounds "$earlier" "$rounds"
            SENT_BACK_BY="$STAGE" SENT_BACK_FILE="$file"
            REVIEW="$file"
            STAGE="$earlier-writer"
            # A new round like any other: past the limit, a human sees it first.
            if [ "$rounds" -gt "$DELIVER_MAX_ROUNDS" ]; then
                record_needs_human "$SENT_BACK_BY" \
                    "$SENT_BACK_BY sent work back to the $earlier pair, which has used its $DELIVER_MAX_ROUNDS rounds. Why is in $file." \
                    '["Should the '"$earlier"' pair take this send-back as a further round? Answer, then rerun to send it."]'
                stop_for_human
            fi
            ;;
        *:needs_human)
            record_needs_human "$STAGE" "$summary" "$(jq -c '.questions' <<<"$result")"
            stop_for_human
            ;;
        *) die "$STAGE may not return '$status'" ;;
    esac
    save_state
done

STATUS=done
save_state
log "Issue #$ISSUE is ready for review: $WORKTREE, branch $BRANCH. Nothing is committed"
