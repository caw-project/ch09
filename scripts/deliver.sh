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
# DELIVER_RUN=<name> builds the same issue again beside it, in
# ../caw-issue-<N>-<name> on feature/issue-<N>-<name>.
#
# Seven stages: a writer and a reviewer for each of plan, tests and code, then
# the acceptance-reviewer, which deploys the branch's preview and proves it
# there. What every agent needs to know about this workflow — the context
# block, rounds, the final round, escalation — is in
# .claude/delivery/agent-context.md; keep it in step with this script.
#
#   plan-writer -> plan-reviewer -> test-writer -> test-reviewer -> code-writer -> code-reviewer
#     -> acceptance-reviewer -> done
#
#   a writer returns    done               on to its reviewer
#   a reviewer returns  approved           on to the next writer, or done
#                       changes_requested  back to its writer, with the review
#   a later stage       send_back          back to the writer of the pair before
#     returns                                its own, with why in a send-back file
#   any agent returns   needs_human        stop; questions in needs-human.md
#
# The acceptance-reviewer has no writer: it approves (with its proof in
# docs/plans/issue-<N>/04-proof.md), sends back to the code-writer, or stops.
# Before each of its passes the workflow deploys the branch's preview itself —
# a build and a deploy can outlast any tool call an agent makes — retries a
# failure once, and tells the agent how it went. The preview is left running
# for the human. Two deliveries at once are unsupported — both `preview up`s
# upgrade KEDA.
#
# A send-back is for work an earlier pair owns and a later stage finds wrong — a
# test the code-writer can't pass because the test is broken, a plan the tests
# can't be written to. The stage writes why to the send-back file its context
# block names, and stops. The earlier pair takes a new round: its writer answers
# the file as it answers a review, its reviewer gates the fix, and the workflow
# comes forward from there as usual. Every stage on the way is told what changed
# since the send-back, and the stage that sent it back what it is resuming
# after. Test stages send back to the plan-writer, code stages to the
# test-writer; the plan pair can't send back. A reviewer that sends back has
# reviewed too: its pair's round advances, so its next review is a new file, and
# its own writer gets the review to answer when the flow comes forward to it.
#
# A writer and its reviewer get DELIVER_MAX_ROUNDS reviews (default 3). The last
# is the final round, and it is cut down so a disagreement cannot run on: both
# agents get fewer turns and less effort, and are told so. The final reviewer
# may only approve — leaving minor findings to the stages after it — or stop for
# a human over something critical or a deadlock; `changes_requested` there stops
# for a human too. A send-back is not a disagreement inside the pair, so it
# never lands in a final round: the pair it reaches, and the pair of a reviewer
# that sent it, always have one ordinary review and a final one ahead. What
# bounds it instead is DELIVER_MAX_SENDBACKS, the send-backs one pair will take.
#
# A stage that runs out of turns is resumed once, in the same session, and told
# to finish; one that dies without a result is run once more. Only when that
# fails too does the run stop.
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
#   DELIVER_MAX_SENDBACKS    send-backs one pair takes before a human sees the
#                            next. Default: 3
#   DELIVER_MAX_TURNS        turns for a stage's first pass — a guard against a
#                            runaway, not a budget. Default: by stage, 150–250
#                            (first_pass_turns)
#   DELIVER_REWORK_MAX_TURNS turns for a pass that answers a review or follows a
#                            send-back. Default: 100
#   DELIVER_FINAL_MAX_TURNS  turns for a stage in the final round. Default: 60
#   DELIVER_FINAL_EFFORT     effort for a stage in the final round. Default: medium
#   DELIVER_BASE             the branch a new worktree starts from. Default: main
#   DELIVER_RUN              a name for a second build of the same issue (above)
#   DELIVER_MODEL            one model for every stage, e.g. for a cheap dry run.
#                            Default: by stage — Sonnet for the test pair, the
#                            code-writer and the acceptance-reviewer, Opus for the
#                            plan pair and the code-reviewer (default_model)
#   DELIVER_MODEL_<STAGE>    one stage's model, over DELIVER_MODEL and the
#                            default — DELIVER_MODEL_TEST_WRITER=opus
#   DELIVER_REWORK_MODEL     the model for a pass that answers a review or follows
#                            a send-back, over both of those
#   DELIVER_EFFORT           effort for every stage's first pass. Default: the
#                            model's own
#   DELIVER_EFFORT_<STAGE>   one stage's effort, over DELIVER_EFFORT
#   DELIVER_REWORK_EFFORT    effort for a rework pass, over both of those. The
#                            final round keeps DELIVER_FINAL_EFFORT
#   DELIVER_PERMISSION_MODE  default: dontAsk — anything a stage is not allowed
#                            below is refused, never prompted for
#
# Exit status: 0 done · 1 error · 2 needs a human · 3 paused at an unbuilt stage.
# Progress and every agent's full JSON result are in build/delivery/ in the
# worktree; history.log there has each stage's verdict, time, turns and cost.
# The proof is in docs/plans/issue-<N>/04-proof.md, its evidence in
# build/acceptance/.
#
set -euo pipefail
# shellcheck source=lib/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

STAGES=(plan-writer plan-reviewer test-writer test-reviewer code-writer code-reviewer acceptance-reviewer)

DELIVER_MAX_ROUNDS="${DELIVER_MAX_ROUNDS:-3}"
DELIVER_MAX_SENDBACKS="${DELIVER_MAX_SENDBACKS:-3}"
DELIVER_MAX_TURNS="${DELIVER_MAX_TURNS:-}"
DELIVER_REWORK_MAX_TURNS="${DELIVER_REWORK_MAX_TURNS:-100}"
DELIVER_FINAL_MAX_TURNS="${DELIVER_FINAL_MAX_TURNS:-60}"
DELIVER_RUN="${DELIVER_RUN:-}"
DELIVER_FINAL_EFFORT="${DELIVER_FINAL_EFFORT:-medium}"
DELIVER_BASE="${DELIVER_BASE:-main}"
DELIVER_MODEL="${DELIVER_MODEL:-}"
DELIVER_REWORK_MODEL="${DELIVER_REWORK_MODEL:-}"
DELIVER_EFFORT="${DELIVER_EFFORT:-}"
DELIVER_REWORK_EFFORT="${DELIVER_REWORK_EFFORT:-}"
DELIVER_PERMISSION_MODE="${DELIVER_PERMISSION_MODE:-dontAsk}"

# What every agent returns. The status a stage may use depends on its role, and
# is checked below, not here, so one schema serves all seven. --json-schema works
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
for setting in DELIVER_MAX_ROUNDS DELIVER_MAX_SENDBACKS DELIVER_REWORK_MAX_TURNS DELIVER_FINAL_MAX_TURNS; do
    case "${!setting}" in
        '' | *[!0-9]* | 0) die "$setting must be a positive number" ;;
    esac
done
case "$DELIVER_MAX_TURNS" in
    *[!0-9]* | 0) die "DELIVER_MAX_TURNS must be a positive number" ;;
esac
case "$DELIVER_RUN" in
    *[!a-zA-Z0-9_-]*) die "DELIVER_RUN may hold letters, digits, - and _ only" ;;
esac
case "$DELIVER_FINAL_EFFORT" in
    low | medium | high | xhigh | max) ;;
    *) die "DELIVER_FINAL_EFFORT must be low, medium, high, xhigh or max" ;;
esac

# --- pre-flight -----------------------------------------------------------------
#
# Everything a run needs from this machine, checked before the first stage. The
# stages that need most of it come last: the test pair installs and runs Vitest
# and pytest, the code-writer's verification runs scripts/test.sh, whose e2e
# layer builds the Compose test stack, and the acceptance-reviewer deploys a
# preview (cloudflared, k3d, kubectl, curl). A missing tool found there costs
# every stage before it. Lists every problem at once, so one fix-and-rerun is
# enough.
preflight() {
    local problems=() cmd
    # The workflow itself; what stages run (tests, lint, the scripts' layers).
    for cmd in claude git jq uv node npm python3 helm docker cloudflared k3d kubectl curl; do
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

BRANCH="feature/issue-$ISSUE${DELIVER_RUN:+-$DELIVER_RUN}"
WORKTREE="$(dirname "$REPO_ROOT")/caw-issue-$ISSUE${DELIVER_RUN:+-$DELIVER_RUN}"

# Paths the agents see are relative to the worktree root.
PLAN_DIR="docs/plans/issue-$ISSUE"
ISSUE_COPY="$PLAN_DIR/00-issue.md"
PLAN="$PLAN_DIR/01-implementation-plan.md"
RED_REPORT="$PLAN_DIR/02-red-tests.md"
GREEN_REPORT="$PLAN_DIR/03-green-report.md"
PROOF="$PLAN_DIR/04-proof.md"
# The acceptance-reviewer's screenshots, smoke packs and results: disposable, so
# under the ignored build/, outside every snapshot.
EVIDENCE=build/acceptance
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
ROUNDS_plan=1 ROUNDS_test=1 ROUNDS_code=1 ROUNDS_acceptance=1
# The round that is each pair's final one. A send-back moves it out (see the
# send_back case), so it is state, not a setting.
FINAL_plan="$DELIVER_MAX_ROUNDS" FINAL_test="$DELIVER_MAX_ROUNDS" FINAL_code="$DELIVER_MAX_ROUNDS"
FINAL_acceptance="$DELIVER_MAX_ROUNDS"
# Send-backs each pair has taken.
SENDBACKS_plan=0 SENDBACKS_test=0 SENDBACKS_code=0
# A send-back still open, by the stage that sent it: the file that says why.
# Open until that stage runs again. More than one can be open — a code stage
# sends back to the test pair, whose reviewer then sends back to the plan pair.
SB_test_writer="" SB_test_reviewer="" SB_code_writer="" SB_code_reviewer="" SB_acceptance_reviewer=""
# A reviewer's review, written as it sent work back, waiting for its own writer.
PENDING_test="" PENDING_code=""

if $restart; then
    rm -f "$STATE"
elif [ -f "$STATE" ]; then
    # shellcheck source=/dev/null
    source "$STATE"
fi

save_state() {
    {
        printf 'STAGE=%q\nSTATUS=%q\nSTEP=%q\nREVIEW=%q\n' "$STAGE" "$STATUS" "$STEP" "$REVIEW"
        printf 'ROUNDS_plan=%q ROUNDS_test=%q ROUNDS_code=%q ROUNDS_acceptance=%q\n' \
            "$ROUNDS_plan" "$ROUNDS_test" "$ROUNDS_code" "$ROUNDS_acceptance"
        printf 'FINAL_plan=%q FINAL_test=%q FINAL_code=%q FINAL_acceptance=%q\n' \
            "$FINAL_plan" "$FINAL_test" "$FINAL_code" "$FINAL_acceptance"
        printf 'SENDBACKS_plan=%q SENDBACKS_test=%q SENDBACKS_code=%q\n' \
            "$SENDBACKS_plan" "$SENDBACKS_test" "$SENDBACKS_code"
        printf 'SB_test_writer=%q SB_test_reviewer=%q SB_code_writer=%q SB_code_reviewer=%q SB_acceptance_reviewer=%q\n' \
            "$SB_test_writer" "$SB_test_reviewer" "$SB_code_writer" "$SB_code_reviewer" "$SB_acceptance_reviewer"
        printf 'PENDING_test=%q PENDING_code=%q\n' "$PENDING_test" "$PENDING_code"
    } >"$STATE"
}

pair_of() { printf '%s' "${1%-*}"; }  # plan-writer -> plan
role_of() { printf '%s' "${1##*-}"; } # plan-writer -> writer

# Per-pair and per-stage variables, read and written by name.
get_var() { eval "printf '%s' \"\${$1:-}\""; }
set_var() { eval "$1=\$2"; }
rounds_of() { get_var "ROUNDS_$1"; }
set_rounds() { set_var "ROUNDS_$1" "$2"; }
final_of() { get_var "FINAL_$1"; }
# The variable that holds a stage's open send-back: test-writer -> SB_test_writer.
sb_var() { printf 'SB_%s' "${1//-/_}"; }

SENDERS=(test-writer test-reviewer code-writer code-reviewer acceptance-reviewer)

# Every pair but acceptance has a writer. The acceptance-reviewer's findings are
# the code pair's to fix, so it sends back rather than asking for changes.
has_writer() { [ "$(pair_of "$1")" != acceptance ]; }

# The pair's last permitted review — and every round after it, which only a
# human's answers can reach.
is_final_round() {
    local pair
    pair="$(pair_of "$1")"
    [ "$(rounds_of "$pair")" -ge "$(final_of "$pair")" ]
}

# A pass that answers a review or follows a send-back: the work exists, and the
# stage changes or rechecks part of it.
is_rework() {
    local sender
    [ "$(rounds_of "$(pair_of "$1")")" -gt 1 ] && return 0
    [ "$(role_of "$1")" = writer ] && [ -n "$REVIEW" ] && return 0
    for sender in "${SENDERS[@]}"; do
        # A writer coming back to its own send-back carries on with a first
        # pass it could not finish.
        [ "$sender" != "$1" ] || [ "$(role_of "$1")" != writer ] || continue
        [ -z "$(get_var "$(sb_var "$sender")")" ] || return 0
    done
    return 1
}

# A first pass's cap by stage: the stages that run tests and builds take more
# turns than the ones that read and write. Measured on issue 1: plan pair 58–71,
# test-writer 93–103, test-reviewer 64–146, code-writer 108–128, code-reviewer
# 78–103.
first_pass_turns() {
    if [ -n "$DELIVER_MAX_TURNS" ]; then
        printf '%s' "$DELIVER_MAX_TURNS"
        return
    fi
    case "$1" in
        plan-*) printf 150 ;;
        test-writer | acceptance-reviewer) printf 200 ;;
        *) printf 250 ;;
    esac
}

turns_for() {
    if is_final_round "$1"; then
        printf '%s' "$DELIVER_FINAL_MAX_TURNS"
    elif is_rework "$1"; then
        printf '%s' "$DELIVER_REWORK_MAX_TURNS"
    else
        first_pass_turns "$1"
    fi
}

# A stage's own setting: stage_setting MODEL test-writer -> $DELIVER_MODEL_TEST_WRITER.
stage_setting() {
    get_var "DELIVER_$1_$(printf '%s' "$2" | tr 'a-z-' 'A-Z_')"
}

# The model each stage runs on when nothing is set, or nothing for its agent's
# own. Measured on issue 1 (docs/plans/ch08/05-model-effort-handoff.md): Sonnet
# for the test pair and the code-writer is a fifth faster and a third cheaper
# with no difference a blind judge could find; a Sonnet plan-writer builds a
# weaker design, and the code-reviewer is the last code gate. The
# acceptance-reviewer mostly runs and records, like the Sonnet stages — not yet
# measured. Hard-coded for now —
# it may come to depend on the issue. Keep the agents' `model:` lines in step.
default_model() {
    case "$1" in
        test-writer | test-reviewer | code-writer | acceptance-reviewer) printf sonnet ;;
    esac
}

# The model a stage runs on this pass, or nothing for its agent's own. A final
# round is a rework pass too, so the rework model reaches it.
model_for() {
    local model
    model="$(stage_setting MODEL "$1")"
    [ -n "$model" ] || model="$DELIVER_MODEL"
    [ -n "$model" ] || model="$(default_model "$1")"
    if [ -n "$DELIVER_REWORK_MODEL" ] && { is_rework "$1" || is_final_round "$1"; }; then
        model="$DELIVER_REWORK_MODEL"
    fi
    printf '%s' "$model"
}

# The effort a stage runs at this pass, or nothing for the model's own. The
# final round's is cut down whatever a rework pass would get.
effort_for() {
    local effort
    effort="$(stage_setting EFFORT "$1")"
    [ -n "$effort" ] || effort="$DELIVER_EFFORT"
    if is_final_round "$1"; then
        effort="$DELIVER_FINAL_EFFORT"
    elif [ -n "$DELIVER_REWORK_EFFORT" ] && is_rework "$1"; then
        effort="$DELIVER_REWORK_EFFORT"
    fi
    printf '%s' "$effort"
}

# What history.log says a stage ran with: the model passed, or the one its agent
# names, and the effort.
ran_with() {
    local model effort
    model="$(model_for "$1")"
    [ -n "$model" ] || model="$(sed -n 's/^model: *//p' "$WORKTREE/.claude/agents/$1.md" | head -n 1)"
    effort="$(effort_for "$1")"
    printf '%s · %s' "${model:-default}" "${effort:-default}"
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
        acceptance) printf code ;;
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

# The static checks scripts/test.sh's lint layer runs, one at a time, for a
# stage that changes or reviews Python, a chart or a script. `ruff format` only
# with --check for a reviewer: without it, it writes.
check_bash() {
    printf '%s\n' \
        'Bash(uv run ruff check *)' 'Bash(uv run ruff format --check *)' \
        'Bash(helm lint *)' 'Bash(helm template *)' 'Bash(bash -n *)' \
        'Bash(python3 .claude/hooks/checks/conventions.py*)'
}

# Taking a file out of the tree. The write check sees a deletion as it sees a
# write, so each writer can only remove what it could have written.
remove_bash() {
    printf '%s\n' 'Bash(rm src/*)' 'Bash(rm tests/*)' 'Bash(rm docs/*)' \
        'Bash(rm charts/*)' 'Bash(rm docker/*)' 'Bash(rm scripts/*)'
}

allowed_tools() {
    case "$1" in
        plan-writer)
            printf '%s\n' Read Grep Glob Write Edit Skill
            read_only_bash
            ;;
        # Edit is for its own review, written in two goes — expectations, then
        # the rest. The write check holds it to that file.
        plan-reviewer)
            printf '%s\n' Read Grep Glob Write Edit Skill
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
            remove_bash
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
        # regeneration is here for an issue that changes an API, and the
        # installs for one that adds a dependency.
        code-writer)
            printf '%s\n' Read Grep Glob Write Edit Skill \
                'Bash(npm --prefix src/frontend ci*)' \
                'Bash(npm --prefix src/frontend install *)' \
                'Bash(npm --prefix src/frontend run build*)' \
                'Bash(npm --prefix src/frontend run generate:api*)' \
                'Bash(uv run ruff *)' 'Bash(uv run alembic *)' 'Bash(uv run python -m *)' \
                'Bash(uv add *)' 'Bash(uv lock*)' \
                'Bash(scripts/test.sh *)' \
                'Bash(.claude/hooks/security.sh*)'
            read_only_bash
            test_bash
            check_bash
            remove_bash
            ;;
        # Runs every check but scripts/test.sh, whose layers it reads from the
        # report the code-writer left, and writes only its review. The sketch is
        # the real code copied under build/sketch/, broken on purpose to see
        # which mistakes the tests would catch.
        code-reviewer)
            printf '%s\n' Read Grep Glob Write Edit Skill 'Bash(.claude/delivery/sketch.sh *)' \
                'Bash(npm --prefix src/frontend run build*)'
            read_only_bash
            test_bash
            check_bash
            ;;
        # Runs the smoke packs against the preview the workflow deployed; its
        # feature pack and screenshots go under build/acceptance/, which the
        # write check never sees. `preview url` only — never up, which the
        # workflow runs, or down, which is the human's. No test runner: the
        # code-writer's report says what ran, and the packs are what it adds.
        acceptance-reviewer)
            printf '%s\n' Read Grep Glob Write Edit Skill \
                'Bash(scripts/deploy.sh preview url)' 'Bash(scripts/smoke.sh *)'
            read_only_bash
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
        # Its proof and a send-back on the branch; everything else under build/.
        acceptance-reviewer)
            printf '^%s/(04-proof\.md$|reviews/acceptance-reviewer-sendback-)' "$PLAN_DIR"
            ;;
        code-writer)
            printf '^(src/|docs/|charts/|docker/|scripts/|\.github/|\.env\.example$|docker-compose|%s)' \
                '(pyproject\.toml|uv\.lock|ruff\.toml|README\.md)$'
            ;;
    esac
}

# Paths a stage may never write, even inside its scope. The code-writer builds
# to the approved red set: a test changed after the gate undoes the gate.
write_denied() {
    case "$1" in
        code-writer)
            printf '^(%s|%s|%s|%s|%s|%s|%s|%s)' \
                'src/frontend/src/.*\.test\.tsx?$' 'src/frontend/src/test/' \
                'src/services/[^/]+/tests/' 'src/services/testkit/' 'tests/' \
                "$RED_REPORT\$" "$PLAN_DIR/reviews/[a-z]+-reviewer-" "$PROOF\$"
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

# --- the preview ---------------------------------------------------------------
#
# Deployed here, not by the agent: a cold build and three Helm waits can run past
# the longest command an agent's Bash tool allows, and a deploy killed half-way
# leaves Helm mid-operation. Retried once, as a stage is. The outcome reaches the
# agent as its `Preview:` line; it judges a failure — the branch's, or the
# environment's.
#
# DELIVER_DEPLOY_SH is for the loop test's fake; nothing else sets it.
PREVIEW=""
deploy_preview() {
    local log="$WORKTREE/$EVIDENCE/preview-up.log" deploy="${DELIVER_DEPLOY_SH:-scripts/deploy.sh}" try origin
    mkdir -p "$WORKTREE/$EVIDENCE"
    : >"$log"
    for try in 1 2; do
        log "deploying the preview of $BRANCH (try $try, log: $EVIDENCE/preview-up.log)"
        if (cd "$WORKTREE" && "$deploy" preview up) >>"$log" 2>&1; then
            origin="$(sed -n 's/^APP_ORIGIN=//p' "$log" | tail -n 1)"
            PREVIEW="up at $origin — log: $EVIDENCE/preview-up.log"
            return
        fi
        [ "$try" = 2 ] || sleep "${DELIVER_RETRY_WAIT:-30}"
    done
    PREVIEW="failed twice — log: $EVIDENCE/preview-up.log"
    log "the preview of $BRANCH failed twice — the acceptance-reviewer will judge why"
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
        test | code | acceptance) printf 'Red report: %s\n' "$RED_REPORT" ;;
    esac
    # From the code pair on: what was built, and what ran, as the code-writer
    # reports it.
    case "$pair" in
        code | acceptance) printf 'Green report: %s\n' "$GREEN_REPORT" ;;
    esac
    printf 'Worktree: %s (branch %s)\n' "$WORKTREE" "$BRANCH"
    printf 'Stage: %s, round %s of %s\n' "$stage" "$(rounds_of "$pair")" "$(final_of "$pair")"
    if is_final_round "$stage"; then
        printf 'Final round: yes — %s turns. Follow your *Final round* rules.\n' "$(turns_for "$stage")"
    elif is_rework "$stage"; then
        printf 'Rework pass: yes — %s turns. Follow *A rework pass*.\n' "$(turns_for "$stage")"
    else
        printf 'Turns: %s\n' "$(turns_for "$stage")"
    fi
    if [ "$(role_of "$stage")" = writer ] && [ -n "$REVIEW" ]; then
        printf 'Review to address: %s\n' "$REVIEW"
    fi
    if [ "$(role_of "$stage")" = reviewer ]; then
        if has_writer "$stage"; then
            printf 'Write your review to: %s\n' "$(review_path "$stage")"
        else
            printf 'Proof: %s\n' "$PROOF"
            printf 'Evidence: %s/\n' "$EVIDENCE"
            printf 'Preview: %s\n' "$PREVIEW"
        fi
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
    # work back — the work each takes over has changed since it last saw it, and
    # the list says where, so the pass can keep to that.
    local sender file changed
    for sender in "${SENDERS[@]}"; do
        file="$(get_var "$(sb_var "$sender")")"
        [ -n "$file" ] || continue
        [ "$REVIEW" = "$file" ] || printf 'After a send-back by %s: %s\n' "$sender" "$file"
        [ -f "$RUN_DIR/sendback-$sender.snapshot" ] || continue
        changed="$(touched_between "$(cat "$RUN_DIR/sendback-$sender.snapshot")" "$(snapshot)" |
            grep -v "^$PLAN_DIR/reviews/" | head -n 40 | tr '\n' ' ' || true)"
        [ -z "$changed" ] || printf 'Changed since the send-back by %s: %s\n' "$sender" "$changed"
    done
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

# One headless run of a stage's agent: its JSON result goes to the file named
# first; everything after is passed to claude. A stage that runs out of turns
# exits non-zero with a JSON result, so the result decides whether it failed,
# not the exit status.
invoke_agent() {
    local out="$1"
    shift
    (cd "$WORKTREE" && claude "$@" \
        --output-format json \
        --json-schema "$RESULT_SCHEMA" \
        --permission-mode "$DELIVER_PERMISSION_MODE") >"$out" || true
}

# Runs a stage and prints its structured result as compact JSON. Called in a
# subshell, so it changes no state: the caller counts $STEP. Bash 3.2 does not
# carry errexit into a command substitution, hence the set -e.
run_stage() {
    set -e
    local stage="$1" out base head before scope strays prompt tool_list t turns more subtype round session model effort
    base="$RUN_DIR/$(printf '%02d' "$STEP")-$stage"
    out="$base.json"
    prompt="$(context_block "$stage")"
    tool_list="$(allowed_tools "$stage")"
    local tools=()
    while IFS= read -r t; do tools+=("$t"); done <<<"$tool_list"
    turns="$(turns_for "$stage")"
    round="$(rounds_of "$(pair_of "$stage")")"
    local extra_args=()
    model="$(model_for "$stage")"
    effort="$(effort_for "$stage")"
    [ -z "$model" ] || extra_args+=(--model "$model")
    [ -z "$effort" ] || extra_args+=(--effort "$effort")

    log "$stage — round $round, $turns turns, $(ran_with "$stage") (log: ${out#"$WORKTREE"/})"
    head="$(git -C "$WORKTREE" rev-parse HEAD)"
    before="$(snapshot)"
    invoke_agent "$out" -p "$prompt" --agent "$stage" --max-turns "$turns" \
        --allowedTools "${tools[@]}" ${extra_args[@]+"${extra_args[@]}"}
    subtype="$(jq -r '.subtype // empty' "$out" 2>/dev/null || true)"

    # No result at all, or an error that isn't the turn cap: the API or the
    # network, not the agent. Run it once more from the top — a writer finds its
    # partial work in place and a reviewer its partial review.
    if [ -z "$subtype" ] || { [ "$subtype" != error_max_turns ] && [ "$(jq -r '.is_error' "$out")" != false ]; }; then
        log "$stage failed without a result (${subtype:-no output}) — running it once more"
        mv "$out" "$base.failed.json"
        sleep "${DELIVER_RETRY_WAIT:-30}"
        invoke_agent "$out" -p "$prompt" --agent "$stage" --max-turns "$turns" \
            --allowedTools "${tools[@]}" ${extra_args[@]+"${extra_args[@]}"}
        subtype="$(jq -r '.subtype // empty' "$out" 2>/dev/null || true)"
        [ -n "$subtype" ] || die "$stage failed twice — see $out"
    fi

    # Out of turns is the cap working, not a crash. Resume the same session once,
    # with half as many turns again and told to finish: everything it has read
    # is still in its context, so this costs far less than a rerun.
    if [ "$subtype" = error_max_turns ]; then
        session="$(jq -r '.session_id // empty' "$out")"
        more=$((turns / 2))
        [ "$more" -ge 30 ] || more=30
        if [ -n "$session" ]; then
            log "$stage used all $turns turns — resuming it with $more more to finish"
            mv "$out" "$base.out-of-turns.json"
            invoke_agent "$out" -p "You ran out of turns before you finished. Everything you wrote is in place, and this is the same session: don't start again, and don't reread what you have read. You have $more more turns. Finish what is left, most important first, write your output file, and return your result through StructuredOutput. If it can't all be done in that, say in the output file what is done and what is not, and return anyway." \
                --resume "$session" --agent "$stage" --max-turns "$more" \
                --allowedTools "${tools[@]}" ${extra_args[@]+"${extra_args[@]}"}
            subtype="$(jq -r '.subtype // empty' "$out" 2>/dev/null || true)"
            [ -n "$subtype" ] || die "$stage failed when resumed — see $out"
        fi
    fi

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

    # Still out of turns after the resume: hand it to a human as a needs_human
    # result, with its partial work left where it is.
    if [ "$subtype" = error_max_turns ]; then
        jq -nc --arg stage "$stage" --arg turns "$turns" --arg round "$round" --arg out "${out#"$WORKTREE"/}" '{
            status: "needs_human",
            summary: "\($stage) used all \($turns) turns in round \($round), and the turns it was resumed with, without finishing. Its transcript is in \($out); anything it wrote is left in place.",
            files: [],
            questions: ["\($stage) ran out of turns twice. Rerun it as it is, rerun with a larger DELIVER_MAX_TURNS, DELIVER_REWORK_MAX_TURNS or DELIVER_FINAL_MAX_TURNS, or answer here what it was stuck on — which?"]
        }'
        return
    fi

    [ "$(jq -r '.is_error' "$out")" = false ] || die "$stage ended in error ($subtype) — see $out"
    jq -e '.structured_output.status' "$out" >/dev/null ||
        die "$stage returned no structured result — see $out"

    jq -c '.structured_output' "$out"
}

# A step's minutes, turns and cost, over every run it took — a retry and a
# resume each leave a file of their own beside the result.
step_stats() {
    jq -rs '"\(map(.duration_ms // 0) | add / 60000 * 10 | round / 10)m \(map(.num_turns // 0) | add) turns $\(map(.total_cost_usd // 0) | add * 100 | round / 100)"' \
        "$RUN_DIR/$(printf '%02d' "$STEP")"-*.json 2>/dev/null || printf 'no stats'
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
    # The proof as it stood before this pass: an approval must leave its own.
    proof_before=""
    if ! has_writer "$STAGE"; then
        deploy_preview
        proof_before="$(git -C "$WORKTREE" hash-object "$PROOF" 2>/dev/null || true)"
    fi
    result="$(run_stage "$STAGE")"
    status="$(jq -r '.status' <<<"$result")"
    summary="$(jq -r '.summary' <<<"$result")"
    stats="$(step_stats) · $(ran_with "$STAGE")"
    printf '%02d %s %s [%s]: %s\n' "$STEP" "$STAGE" "$status" "$stats" "$summary" >>"$RUN_DIR/history.log"
    log "$STAGE: $status [$stats] — $summary"

    pair="$(pair_of "$STAGE")"
    # The stage a send-back was waiting on has now run with it in view.
    if [ "$pair" != plan ] && [ -n "$(get_var "$(sb_var "$STAGE")")" ]; then
        set_var "$(sb_var "$STAGE")" ""
        rm -f "$RUN_DIR/sendback-$STAGE.snapshot"
    fi
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
            if has_writer "$STAGE"; then
                [ -s "$WORKTREE/$(review_path "$STAGE")" ] ||
                    die "$STAGE approved but wrote no $(review_path "$STAGE")"
            else
                [ -s "$WORKTREE/$PROOF" ] || die "$STAGE approved but wrote no $PROOF"
                [ "$(git -C "$WORKTREE" hash-object "$PROOF")" != "$proof_before" ] ||
                    die "$STAGE approved but did not rewrite $PROOF — it is an earlier pass's"
            fi
            REVIEW=""
            STAGE="$(next_stage "$STAGE")"
            # Coming forward after a reviewer's send-back: its own writer now
            # gets the review that reviewer wrote as it sent the work back.
            if [ "$STAGE" != done ] && [ "$(role_of "$STAGE")" = writer ]; then
                REVIEW="$(get_var "PENDING_$(pair_of "$STAGE")")"
                set_var "PENDING_$(pair_of "$STAGE")" ""
            fi
            ;;
        reviewer:changes_requested)
            has_writer "$STAGE" || die "$STAGE has no writer to take changes — it sends back instead"
            REVIEW="$(review_path "$STAGE")"
            [ -s "$WORKTREE/$REVIEW" ] || die "$STAGE asked for changes but wrote no $REVIEW"
            rounds="$(rounds_of "$pair")"
            # The final reviewer is told to approve or escalate, never to send
            # the plan back — if it does anyway, a human settles it.
            if [ "$rounds" -ge "$(final_of "$pair")" ]; then
                record_needs_human "$STAGE" \
                    "The $pair reviewer asked for changes in the final round ($rounds of $(final_of "$pair")), where it may only approve or escalate. The last review is $REVIEW, and the writer's answers to it are in its Review responses." \
                    '["Settle the findings in the last review that are still open: which should the writer take, and which should the reviewer drop?"]'
            fi
            # The writer takes the review, and the answers too when there are
            # some — every round past the limit comes back through a human.
            set_rounds "$pair" $((rounds + 1))
            STAGE="$pair-writer"
            # Checked against the round the review was in: the limit can't have
            # moved since, so this is the same test as the one above.
            [ "$rounds" -lt "$(final_of "$pair")" ] || stop_for_human
            ;;
        *:send_back)
            earlier="$(earlier_pair "$STAGE")"
            [ -n "$earlier" ] || die "$STAGE may not send work back — there is no pair before it"
            file="$(sendback_path "$STAGE")"
            [ -s "$WORKTREE/$file" ] || die "$STAGE sent work back but wrote no $file"
            # The earlier pair takes a new round, with an ordinary review and a
            # final one ahead of it whatever it had used before.
            rounds=$(($(rounds_of "$earlier") + 1))
            set_rounds "$earlier" "$rounds"
            [ "$(final_of "$earlier")" -gt "$rounds" ] || set_var "FINAL_$earlier" $((rounds + 1))
            taken=$(($(get_var "SENDBACKS_$earlier") + 1))
            set_var "SENDBACKS_$earlier" "$taken"
            # A reviewer has reviewed as well as sent back. Its review waits for
            # its own writer, and its pair moves on a round, so its next review
            # is a new file and the writer's pass before it is a rework pass.
            if [ "$(role_of "$STAGE")" = reviewer ] && has_writer "$STAGE"; then
                review="$(review_path "$STAGE")"
                [ -s "$WORKTREE/$review" ] || die "$STAGE sent work back but wrote no $review"
                set_var "PENDING_$pair" "$review"
                rounds=$(($(rounds_of "$pair") + 1))
                set_rounds "$pair" "$rounds"
                [ "$(final_of "$pair")" -gt "$rounds" ] || set_var "FINAL_$pair" $((rounds + 1))
            elif [ "$(role_of "$STAGE")" = reviewer ]; then
                # No writer to hand a review to; its own round still moves on,
                # so its return is a rework pass with a final round ahead.
                rounds=$(($(rounds_of "$pair") + 1))
                set_rounds "$pair" "$rounds"
                [ "$(final_of "$pair")" -gt "$rounds" ] || set_var "FINAL_$pair" $((rounds + 1))
            fi
            set_var "$(sb_var "$STAGE")" "$file"
            snapshot >"$RUN_DIR/sendback-$STAGE.snapshot"
            sender="$STAGE"
            REVIEW="$file"
            STAGE="$earlier-writer"
            # Bounded by count, not by rounds: past it, a human sees it first.
            if [ "$taken" -gt "$DELIVER_MAX_SENDBACKS" ]; then
                record_needs_human "$sender" \
                    "$sender sent work back to the $earlier pair, which has already taken $DELIVER_MAX_SENDBACKS send-backs. Why is in $file." \
                    '["Should the '"$earlier"' pair take this send-back too? Answer, then rerun to send it."]'
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
log "Start with $PROOF. Its preview is still up: BRANCH=$BRANCH scripts/deploy.sh preview url, and preview down when you're done"
# What the run took, a line a step.
sed -E 's/^([0-9]+ [a-z-]+ [a-z_]+ \[[^]]*\]).*/  \1/' "$RUN_DIR/history.log" >&2
