#!/usr/bin/env bash
# Take one issue to a tested feature ready for review, with the delivery agents in
# .claude/agents/ doing the work. The runner commits and pushes its branch after
# every stage; no agent commits.
#
#   scripts/deliver.sh issue-8                   start, or carry on from where it stopped
#   scripts/deliver.sh issue-8 --restart         forget progress and start at plan-writer
#   scripts/deliver.sh --backend github --url https://github.com/OWNER/REPO gh-3
#
# The issue is named by its key, and fetched through its backend — `delivery` in
# tools/delivery, the same library the issue-writer posts with. This script only
# runs it from the repo root; the workflow is the Python package delivery.run,
# whose docstring is the reference: stages, rounds, send-backs, every DELIVER_*
# setting, and the exit status (0 done · 1 error · 2 needs a human, or bad
# configuration · 3 paused at an unbuilt stage · 4 out of time — run it again).
set -euo pipefail
# shellcheck source=lib/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

# `delivery` takes the backend before its command and the rest after it.
backend=() rest=()
while [ $# -gt 0 ]; do
    case "$1" in
        -h | --help)
            usage
            exit 0
            ;;
        --backend | --url)
            [ $# -ge 2 ] || die "$1 needs a value"
            backend+=("$1" "$2")
            shift
            ;;
        --backend=* | --url=*) backend+=("$1") ;;
        *) rest+=("$1") ;;
    esac
    shift
done
require_cmd uv

# Local issues are read from the checkout that runs this, so it runs from its root.
cd "$REPO_ROOT"
exec uv run --quiet --frozen --project "$REPO_ROOT" delivery ${backend[@]+"${backend[@]}"} deliver ${rest[@]+"${rest[@]}"}
