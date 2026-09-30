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
# Six stages, a writer and a reviewer for each of plan, tests and code:
#
#   plan-writer -> plan-reviewer -> test-writer -> test-reviewer -> code-writer -> code-reviewer -> done
#
#   a writer returns    done               on to its reviewer
#   a reviewer returns  approved           on to the next writer, or done
#                       changes_requested  back to its writer, with the review
#   any agent returns   needs_human        stop; questions in needs-human.md
#
# A writer and its reviewer get DELIVER_MAX_ROUNDS reviews (default 3) before
# the workflow stops for a human instead. Answer the questions under each
# **Answer:** in docs/plans/issue-<N>/needs-human.md, then run the same command
# again: it resumes at the stage that stopped, and every agent reads the answers.
#
# A stage whose agent is not written yet pauses the workflow the same way; run
# it again once the agent exists.
#
#   DELIVER_MAX_ROUNDS       reviews per writer/reviewer pair. Default: 3
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
    "status":    {"type": "string", "enum": ["done", "approved", "changes_requested", "needs_human"]},
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
case "$DELIVER_MAX_ROUNDS" in
    '' | *[!0-9]* | 0) die "DELIVER_MAX_ROUNDS must be a positive number" ;;
esac
require_cmd claude git jq

issue_file="$(cd "$(dirname "$issue_file")" && pwd)/$(basename "$issue_file")"
ISSUE="$(head -n 20 "$issue_file" | grep -m1 -oiE 'issue[[:space:]:#]*[0-9]+' | grep -oE '[0-9]+' || true)"
[ -n "$ISSUE" ] || die "$issue_file names no issue number in its first 20 lines (e.g. 'Issue: 42')"

BRANCH="feature/issue-$ISSUE"
WORKTREE="$(dirname "$REPO_ROOT")/caw-issue-$ISSUE"

# Paths the agents see are relative to the worktree root.
PLAN_DIR="docs/plans/issue-$ISSUE"
ISSUE_COPY="$PLAN_DIR/00-issue.md"
PLAN="$PLAN_DIR/01-implementation-plan.md"
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
    } >"$STATE"
}

pair_of() { printf '%s' "${1%-*}"; }  # plan-writer -> plan
role_of() { printf '%s' "${1##*-}"; } # plan-writer -> writer

rounds_of() { eval "printf '%s' \"\$ROUNDS_$1\""; }
set_rounds() { eval "ROUNDS_$1=$2"; }

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

# --- what each stage may do ---------------------------------------------------
#
# In dontAsk mode a tool not listed here is refused, so this list is the stage's
# whole reach. Each stage's entry is added with its agent.

allowed_tools() {
    case "$1" in
        plan-writer)
            printf '%s\n' Read Grep Glob Write Edit Skill \
                'Bash(git log *)' 'Bash(git show *)' 'Bash(git diff *)' \
                'Bash(git status *)' 'Bash(git worktree list*)' 'Bash(git branch *)' \
                'Bash(ls *)' 'Bash(wc *)'
            ;;
        *) die "no tools are allowed for $1 yet — add its entry to allowed_tools" ;;
    esac
}

# Where a stage may write. Checked after it runs; unset means the stage is not
# confined to one directory.
write_scope() {
    case "$1" in
        plan-writer) printf '%s/' "$PLAN_DIR" ;;
        plan-reviewer) printf '%s/reviews/' "$PLAN_DIR" ;;
    esac
}

# The file a writer must leave behind when it says `done`.
writer_output() {
    case "$1" in
        plan-writer) printf '%s' "$PLAN" ;;
    esac
}

# --- running one stage --------------------------------------------------------

context_block() {
    local stage="$1" pair
    pair="$(pair_of "$stage")"
    printf 'Issue: #%s\n' "$ISSUE"
    printf 'Issue file: %s\n' "$ISSUE_COPY"
    printf 'Plan: %s\n' "$PLAN"
    printf 'Worktree: %s (branch %s)\n' "$WORKTREE" "$BRANCH"
    printf 'Stage: %s, round %s of %s\n' "$stage" "$(rounds_of "$pair")" "$DELIVER_MAX_ROUNDS"
    if [ "$(role_of "$stage")" = writer ] && [ -n "$REVIEW" ]; then
        printf 'Review to address: %s\n' "$REVIEW"
    fi
    if [ "$(role_of "$stage")" = reviewer ]; then
        printf 'Write your review to: %s\n' "$(review_path "$stage")"
    fi
    if [ -s "$WORKTREE/$ANSWERS" ]; then
        printf 'Human answers: %s\n' "$ANSWERS"
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
    local stage="$1" out head before scope strays prompt tool_list t
    out="$RUN_DIR/$(printf '%02d' "$STEP")-$stage.json"
    prompt="$(context_block "$stage")"
    tool_list="$(allowed_tools "$stage")"
    local tools=()
    while IFS= read -r t; do tools+=("$t"); done <<<"$tool_list"
    local model_args=()
    [ -z "$DELIVER_MODEL" ] || model_args=(--model "$DELIVER_MODEL")

    log "$stage — round $(rounds_of "$(pair_of "$stage")") (log: ${out#"$WORKTREE"/})"
    head="$(git -C "$WORKTREE" rev-parse HEAD)"
    before="$(snapshot)"
    (cd "$WORKTREE" && claude -p "$prompt" \
        --agent "$stage" \
        --output-format json \
        --json-schema "$RESULT_SCHEMA" \
        --permission-mode "$DELIVER_PERMISSION_MODE" \
        --allowedTools "${tools[@]}" \
        ${model_args[@]+"${model_args[@]}"}) >"$out" ||
        die "$stage failed — see $out"

    [ "$(jq -r '.is_error' "$out")" = false ] || die "$stage ended in error — see $out"
    jq -e '.structured_output.status' "$out" >/dev/null ||
        die "$stage returned no structured result — see $out"

    # The rules no agent may break, checked rather than trusted.
    [ "$(git -C "$WORKTREE" rev-parse HEAD)" = "$head" ] ||
        die "$stage committed — the workflow never commits. Inspect $BRANCH before rerunning"
    scope="$(write_scope "$stage")"
    if [ -n "$scope" ]; then
        strays="$(touched_between "$before" "$(snapshot)" | grep -v "^$scope" || true)"
        [ -z "$strays" ] || die "$stage wrote outside $scope:
$strays"
    fi

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
    case "$(role_of "$STAGE"):$status" in
        writer:done)
            output="$(writer_output "$STAGE")"
            [ -z "$output" ] || [ -s "$WORKTREE/$output" ] ||
                die "$STAGE said done but wrote no $output"
            REVIEW=""
            STAGE="$(next_stage "$STAGE")"
            ;;
        reviewer:approved)
            REVIEW=""
            STAGE="$(next_stage "$STAGE")"
            ;;
        reviewer:changes_requested)
            REVIEW="$(review_path "$STAGE")"
            [ -s "$WORKTREE/$REVIEW" ] || die "$STAGE asked for changes but wrote no $REVIEW"
            rounds="$(rounds_of "$pair")"
            if [ "$rounds" -ge "$DELIVER_MAX_ROUNDS" ]; then
                record_needs_human "$STAGE" \
                    "The $pair writer and reviewer did not agree in $rounds rounds. The last review is $REVIEW." \
                    '["Settle the findings in the last review that are still open: which should the writer take, and which should the reviewer drop?"]'
            fi
            # The writer takes the review, and the answers too when there are
            # some — every round past the limit comes back through a human.
            set_rounds "$pair" $((rounds + 1))
            STAGE="$pair-writer"
            [ "$rounds" -lt "$DELIVER_MAX_ROUNDS" ] || stop_for_human
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
