"""The PR a delivery opens, made from its proof: which screenshots the proof cites, and the
title and body the runner sends — pure functions over the proof's text."""

from __future__ import annotations

from delivery.run.publish import SQUASH_NOTE, cited_screenshots, pr_body, pr_title

PROOF = """\
# gh-3 — acceptance proof: accepted

## Summary
- Display names are unique.

## Try it
- The PR's preview: its origin is in a comment on this PR.

## Acceptance criteria
| # | Criterion | Proven by | Result | Screenshot |
|---|---|---|---|---|
| 1 | Unique | test_a | proven | [taken](../../../build/acceptance/feature/taken.png) |
| 2 | Shown | test_b | proven | ![shown](../../../build/acceptance/feature/shown.png) |

## Screenshots
[build/acceptance/](../../../build/acceptance/) — listed by test.
- ![taken again](../../../build/acceptance/feature/taken.png)
- [the standard pack's results](../../../build/acceptance/standard/results.xml)
- ![signed in](../../../build/acceptance/standard/signed-in.jpg)

## For the human
Nothing open. See [the plan](01-implementation-plan.md).

## The run
01 plan-writer done [3 min]
02 plan-reviewer approved [2 min]
"""

LINKS = {
    "feature/taken.png": "https://x/blob/a1/docs/plans/gh-3/proof/feature/taken.png?raw=true",
    "feature/shown.png": "https://x/blob/a1/docs/plans/gh-3/proof/feature/shown.png?raw=true",
    "standard/signed-in.jpg": "https://x/blob/a1/docs/plans/gh-3/proof/standard/signed-in.jpg?raw=true",
}


def body(proof: str = PROOF, links=LINKS) -> str:
    return pr_body(proof, issue_number=3, links=links)


# --- cited screenshots -----------------------------------------------------


def test_the_screenshots_cited_are_the_images_under_build_acceptance_once_each_in_order():
    assert cited_screenshots(PROOF) == [
        "feature/taken.png",
        "feature/shown.png",
        "standard/signed-in.jpg",
    ]


def test_a_proof_with_no_screenshots_cites_none():
    assert cited_screenshots("# gh-3 — acceptance proof: accepted\n\n## Summary\n- x\n") == []


def test_a_link_that_climbs_out_of_build_acceptance_is_not_a_screenshot():
    proof = "![x](../../../build/acceptance/../../secrets.png)\n![y](../../../src/a.png)\n"

    assert cited_screenshots(proof) == []


# --- the body --------------------------------------------------------------


def test_the_proofs_heading_is_dropped_and_its_sections_kept():
    text = body()

    assert "acceptance proof" not in text
    assert text.startswith("## Summary\n- Display names are unique.\n")
    assert "## For the human\nNothing open." in text


def test_each_cited_screenshot_links_to_the_commit_that_holds_it():
    text = body()

    assert f"[taken]({LINKS['feature/taken.png']})" in text
    assert f"![shown]({LINKS['feature/shown.png']})" in text
    assert f"![taken again]({LINKS['feature/taken.png']})" in text
    assert f"![signed in]({LINKS['standard/signed-in.jpg']})" in text
    assert "../../../build/acceptance/feature/" not in text


def test_any_other_link_into_build_acceptance_becomes_its_path_since_nothing_serves_it():
    text = body()

    assert "`build/acceptance/` — listed by test." in text
    assert "the standard pack's results (`build/acceptance/standard/results.xml`)" in text
    assert "../../../build/acceptance" not in text


def test_a_link_that_is_not_into_build_acceptance_is_left_alone():
    assert "[the plan](01-implementation-plan.md)" in body()


def test_the_run_is_collapsed_and_ends_where_its_section_does():
    text = body()

    assert (
        "<details><summary>The run</summary>\n\n"
        "01 plan-writer done [3 min]\n02 plan-reviewer approved [2 min]\n\n</details>"
    ) in text
    assert "## The run" not in text


def test_a_section_after_the_run_stays_outside_its_details():
    proof = PROOF.replace("## The run\n", "## The run\n01 x\n\n## Later\nAfter.\n", 1)

    text = body(proof)

    assert "01 x\n\n</details>" in text
    assert text.index("</details>") < text.index("## Later\nAfter.")


def test_the_body_closes_the_issue_and_asks_for_a_squash_merge():
    text = body()

    assert text.rstrip().endswith(f"Closes #3\n\n{SQUASH_NOTE}")
    assert "squash" in SQUASH_NOTE.lower()
    assert text.index("</details>") < text.index("Closes #3")


def test_a_proof_with_no_run_section_still_closes_the_issue():
    proof = PROOF[: PROOF.index("## The run")]

    text = body(proof)

    assert "<details>" not in text
    assert "Closes #3" in text


# --- the title -------------------------------------------------------------


def test_the_title_is_the_issues_with_its_key():
    assert pr_title("Display names are unique", "gh-3") == "Display names are unique (gh-3)"
