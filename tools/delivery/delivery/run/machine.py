"""The state machine: the seven stages, their rounds, and what each verdict does to the run.

Pure over `State`: the loop runs a stage, then hands its result here with what is on disk,
and does what the returned `Advance` says — record a stop, take a snapshot, or carry on.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from delivery.errors import RunError
from delivery.run.keys import Paths
from delivery.run.settings import Settings
from delivery.run.state import State

STAGES = (
    "plan-writer",
    "plan-reviewer",
    "test-writer",
    "test-reviewer",
    "code-writer",
    "code-reviewer",
    "acceptance-reviewer",
)
#: Every stage that can send work back, in the order the context block lists them.
SENDERS = ("test-writer", "test-reviewer", "code-writer", "code-reviewer", "acceptance-reviewer")
EARLIER = {"test": "plan", "code": "test", "acceptance": "code"}


def pair_of(stage: str) -> str:
    """plan-writer -> plan"""
    return stage.rsplit("-", 1)[0]


def role_of(stage: str) -> str:
    """plan-writer -> writer"""
    return stage.rsplit("-", 1)[-1]


def has_writer(stage: str) -> bool:
    """Every pair but acceptance has a writer. The acceptance-reviewer's findings are the
    code pair's to fix, so it sends back rather than asking for changes."""
    return pair_of(stage) != "acceptance"


def next_stage(stage: str) -> str:
    if stage not in STAGES:
        raise RunError(f"unknown stage '{stage}'")
    i = STAGES.index(stage)
    return STAGES[i + 1] if i + 1 < len(STAGES) else "done"


def earlier_pair(stage: str) -> str | None:
    """The pair a stage sends back to, or None for the plan pair."""
    return EARLIER.get(pair_of(stage))


def is_final_round(stage: str, state: State) -> bool:
    """The pair's last permitted review — and every round after it, which only a human's
    answers can reach."""
    pair = pair_of(stage)
    return state.rounds[pair] >= state.final[pair]


def is_rework(stage: str, state: State) -> bool:
    """A pass that answers a review or follows a send-back: the work exists, and the stage
    changes or rechecks part of it."""
    if state.rounds[pair_of(stage)] > 1:
        return True
    if role_of(stage) == "writer" and state.review:
        return True
    for sender, file in state.open_sendbacks.items():
        # A writer coming back to its own send-back carries on with a first pass it
        # could not finish.
        if sender == stage and role_of(stage) == "writer":
            continue
        if file:
            return True
    return False


def review_path(stage: str, state: State, paths: Paths) -> str:
    """A reviewer's review, one file per round so the writer's history survives."""
    return f"{paths.reviews}/{stage}-{state.rounds[pair_of(stage)]}.md"


def sendback_path(stage: str, state: State, paths: Paths) -> str:
    """Where a stage writes why it sends work back — numbered by the round the earlier pair
    will take it in, so each send-back keeps its own file."""
    earlier = earlier_pair(stage)
    assert earlier is not None  # noqa: S101 — only asked of a stage with a pair before it.
    return f"{paths.reviews}/{stage}-sendback-{state.rounds[earlier] + 1}.md"


def writer_output(stage: str, paths: Paths) -> str | None:
    """The file a writer must leave behind when it says `done`."""
    return {
        "plan-writer": paths.plan,
        "test-writer": paths.red_report,
        "code-writer": paths.green_report,
    }.get(stage)


@dataclass(frozen=True)
class HumanStop:
    """A stop to append to `needs-human.md`."""

    stage: str
    round: int
    summary: str
    questions: list[str]


@dataclass
class Advance:
    """What the loop does after a stage's result."""

    #: Append this to `needs-human.md`.
    human: HumanStop | None = None
    #: Stop the run for a human (exit 2).
    stop: bool = False
    #: Take the snapshot a send-back's changes are measured from.
    snapshot: bool = False
    #: The stage's own send-back closed: its snapshot can go.
    cleared: bool = False


def advance(
    state: State,
    stage: str,
    result: Mapping[str, object],
    paths: Paths,
    settings: Settings,
    *,
    exists: Callable[[str], bool],
    proof_rewritten: bool,
) -> Advance:
    """Moves `state` on from `stage`'s result. `exists` says whether a worktree path holds
    anything; `proof_rewritten` whether this pass changed the proof."""
    status = str(result["status"])
    moved = Advance()
    # The stage a send-back was waiting on has now run with it in view.
    if pair_of(stage) != "plan" and state.open_sendbacks.get(stage):
        del state.open_sendbacks[stage]
        moved.cleared = True

    verdict = (role_of(stage), status)
    if verdict == ("writer", "done"):
        writer_done(state, stage, paths, exists)
    elif verdict == ("reviewer", "approved"):
        approved(state, stage, paths, exists, proof_rewritten)
    elif verdict == ("reviewer", "changes_requested"):
        changes_requested(state, stage, paths, exists, moved)
    elif status == "send_back":
        send_back(state, stage, paths, settings, exists, moved)
    elif status == "needs_human":
        questions = result.get("questions") or []
        assert isinstance(questions, list)  # noqa: S101 — the result schema makes it one.
        summary = str(result.get("summary", ""))
        moved.human = HumanStop(
            stage, state.rounds[pair_of(stage)], summary, [str(q) for q in questions]
        )
        moved.stop = True
    else:
        raise RunError(f"{stage} may not return '{status}'")
    return moved


def missing_outputs(
    state: State,
    stage: str,
    result: Mapping[str, object],
    paths: Paths,
    *,
    exists: Callable[[str], bool],
    proof_rewritten: bool,
) -> list[str]:
    """The files `stage`'s verdict owes that aren't there — asked before `advance`, which
    fails on the same, so the runner can ask the agent for them first. Changes nothing."""
    status = str(result["status"])
    owed: list[str] = []
    if (role_of(stage), status) == ("writer", "done"):
        owed = [o for o in [writer_output(stage, paths)] if o]
    elif status in ("approved", "changes_requested") and has_writer(stage):
        owed = [review_path(stage, state, paths)]
    elif status == "approved":
        if exists(paths.proof) and not proof_rewritten:
            return [paths.proof]
        owed = [paths.proof]
    elif status == "send_back" and earlier_pair(stage):
        owed = [sendback_path(stage, state, paths)]
        if role_of(stage) == "reviewer" and has_writer(stage):
            owed.append(review_path(stage, state, paths))
    return [path for path in owed if not exists(path)]


def writer_done(state: State, stage: str, paths: Paths, exists: Callable[[str], bool]) -> None:
    output = writer_output(stage, paths)
    if output and not exists(output):
        raise RunError(f"{stage} said done but wrote no {output}")
    state.review = ""
    state.stage = next_stage(stage)


def approved(
    state: State, stage: str, paths: Paths, exists: Callable[[str], bool], proof_rewritten: bool
) -> None:
    # An approval writes its review too: it is the record of what was checked, and of any
    # minor findings left for later stages.
    if has_writer(stage):
        review = review_path(stage, state, paths)
        if not exists(review):
            raise RunError(f"{stage} approved but wrote no {review}")
    elif not exists(paths.proof):
        raise RunError(f"{stage} approved but wrote no {paths.proof}")
    elif not proof_rewritten:
        raise RunError(
            f"{stage} approved but did not rewrite {paths.proof} — it is an earlier pass's"
        )
    state.review = ""
    state.stage = next_stage(stage)
    # Coming forward after a reviewer's send-back: its own writer now gets the review that
    # reviewer wrote as it sent the work back.
    if state.stage != "done" and role_of(state.stage) == "writer":
        writer_pair = pair_of(state.stage)
        state.review = state.pending.get(writer_pair, "")
        if writer_pair in state.pending:
            state.pending[writer_pair] = ""


def changes_requested(
    state: State, stage: str, paths: Paths, exists: Callable[[str], bool], moved: Advance
) -> None:
    if not has_writer(stage):
        raise RunError(f"{stage} has no writer to take changes — it sends back instead")
    pair = pair_of(stage)
    state.review = review_path(stage, state, paths)
    if not exists(state.review):
        raise RunError(f"{stage} asked for changes but wrote no {state.review}")
    rounds, final = state.rounds[pair], state.final[pair]
    # The final reviewer is told to approve or escalate, never to send the plan back — if
    # it does anyway, a human settles it.
    if rounds >= final:
        moved.human = HumanStop(
            stage,
            rounds,
            f"The {pair} reviewer asked for changes in the final round ({rounds} of {final}),"
            " where it may only approve or escalate."
            f" The last review is {state.review}, and the writer's answers to it are in its"
            " Review responses.",
            [
                (
                    "Settle the findings in the last review that are still open: which should"
                    " the writer take, and which should the reviewer drop?"
                )
            ],
        )
        moved.stop = True
    # The writer takes the review, and the answers too when there are some — every round
    # past the limit comes back through a human.
    state.rounds[pair] = rounds + 1
    state.stage = f"{pair}-writer"


def send_back(
    state: State,
    stage: str,
    paths: Paths,
    settings: Settings,
    exists: Callable[[str], bool],
    moved: Advance,
) -> None:
    earlier = earlier_pair(stage)
    if earlier is None:
        raise RunError(f"{stage} may not send work back — there is no pair before it")
    file = sendback_path(stage, state, paths)
    if not exists(file):
        raise RunError(f"{stage} sent work back but wrote no {file}")
    # The earlier pair takes a new round, with an ordinary review and a final one ahead of
    # it whatever it had used before.
    new_round(state, earlier)
    state.sendbacks[earlier] += 1
    pair = pair_of(stage)
    if role_of(stage) == "reviewer":
        # A reviewer has reviewed as well as sent back. Its review waits for its own
        # writer, and its pair moves on a round, so its next review is a new file and the
        # writer's pass before it is a rework pass. With no writer, its own round still
        # moves on, so its return is a rework pass with a final round ahead.
        if has_writer(stage):
            review = review_path(stage, state, paths)
            if not exists(review):
                raise RunError(f"{stage} sent work back but wrote no {review}")
            state.pending[pair] = review
        new_round(state, pair)
    state.open_sendbacks[stage] = file
    moved.snapshot = True
    state.review = file
    state.stage = f"{earlier}-writer"
    # Bounded by count, not by rounds: past it, a human sees it first.
    if state.sendbacks[earlier] > settings.max_sendbacks:
        moved.human = HumanStop(
            stage,
            state.rounds[pair],
            f"{stage} sent work back to the {earlier} pair, which has already taken"
            f" {settings.max_sendbacks} send-backs. Why is in {file}.",
            [f"Should the {earlier} pair take this send-back too? Answer, then rerun to send it."],
        )
        moved.stop = True


def new_round(state: State, pair: str) -> None:
    """A pair's next round, never a final one: a send-back is not a disagreement inside
    the pair, so it always has an ordinary review and a final one ahead."""
    state.rounds[pair] += 1
    if state.final[pair] <= state.rounds[pair]:
        state.final[pair] = state.rounds[pair] + 1
