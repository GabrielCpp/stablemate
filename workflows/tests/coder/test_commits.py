"""The commit-message builder: what release-please will actually read.

These are unit tests because the thing under test is a *string format* that three
modules and two agent prompts have to agree on, and because the failure it guards is
invisible at the git level — a repo happily records `0004-checkout: guest-cart`, and
nothing goes wrong until a release that should have shipped the feature does not mention
it. The end-to-end assertions live in `test_workflow.py`; these pin the shape.
"""
from __future__ import annotations

from pathlib import Path

from workhorse_workflows.coder.shared import commits


# --------------------------------------------------------------------------- the subject


def test_the_subject_is_a_conventional_commit_with_the_package_as_its_scope() -> None:
    """The scope names the package, because that is what release-please releases."""
    assert commits.subject("feat", "api-service", "add guest cart") == (
        "feat(api-service): add guest cart"
    )


def test_a_package_with_no_usable_name_leaves_the_scope_off_rather_than_faking_one() -> None:
    """An empty scope is valid Conventional Commits; `feat(): x` is not.

    A repo resolved from a path can arrive as `""` or as punctuation, and a subject that
    parses as nothing releases nothing — the exact failure this module exists to prevent.
    """
    assert commits.subject("feat", commits.scope("   "), "add guest cart") == "feat: add guest cart"
    assert commits.subject("feat", commits.scope("///"), "add guest cart") == "feat: add guest cart"


def test_a_package_name_is_lowercased_and_stripped_to_what_a_scope_may_hold() -> None:
    assert commits.scope("API Service") == "api-service"
    assert commits.scope("web_app") == "web_app"
    assert commits.scope("-Mobile.App-") == "mobile.app"


def test_a_heading_becomes_a_description_without_becoming_a_different_word() -> None:
    """Lowercasing the first word is a changelog nicety; renaming an identifier is a bug."""
    assert commits.describe("Add password reset.") == "add password reset"
    assert commits.describe("STORY-1 pagination") == "STORY-1 pagination"
    assert commits.describe("OAuth token refresh") == "OAuth token refresh"
    assert commits.describe("  spaced   out  ") == "spaced out"


def test_a_long_description_is_trimmed_but_the_give_up_marker_never_is() -> None:
    """The marker is the first thing a human triaging the epic PR reads.

    Trimming the subject from the right would eat `[QA FAILED …]` before it ate a word of
    prose, and a half-eaten marker reads as a story that passed.
    """
    marker = "[QA FAILED after 3 attempts — needs manual review]"
    long_subject = commits.subject("feat", "api-service", "a" * 200, marker)

    assert long_subject.startswith("feat(api-service): ")
    assert long_subject.endswith(marker)


def test_a_short_subject_is_left_at_its_natural_length() -> None:
    assert len(commits.subject("feat", "api", "add guest cart")) <= commits.SUBJECT_LIMIT


def test_a_description_that_is_all_whitespace_still_yields_a_parseable_subject() -> None:
    """`feat(api):` with nothing after it is not a Conventional Commit."""
    assert commits.subject("feat", "api", "   ") == "feat(api): no description"


# --------------------------------------------------------------------------- the body


def test_the_epic_and_story_ride_in_the_body_not_the_subject() -> None:
    """A released changelog quotes the subject verbatim, and its reader has no doc graph."""
    message = commits.message(
        "feat", "api-service", "Add guest cart", epic="checkout", story="guest-cart"
    )

    assert message.splitlines() == [
        "feat(api-service): add guest cart",
        "",
        "Epic: checkout",
        "Story: guest-cart",
    ]


def test_a_message_with_nothing_to_attribute_is_a_bare_subject() -> None:
    assert commits.message("chore", "acme", "prune the queue") == "chore(acme): prune the queue"


# --------------------------------------------------------------------------- the story heading


def test_the_description_comes_from_the_story_heading(tmp_path: Path) -> None:
    """The heading is the one sentence a human wrote about this story."""
    story = tmp_path / "docs" / "story.md"
    story.parent.mkdir(parents=True)
    story.write_text("---\ntype: story\n---\n\n# Paginate the widget list\n", encoding="utf-8")

    assert commits.story_description(tmp_path, "docs/story.md", "widget-pagination") == (
        "paginate the widget list"
    )


def test_a_story_with_no_heading_or_no_file_falls_back_to_the_slug(tmp_path: Path) -> None:
    """The slug always exists and is greppable — that is the whole of its claim."""
    headless = tmp_path / "headless.md"
    headless.write_text("no heading here\n", encoding="utf-8")

    assert commits.story_description(tmp_path, "headless.md", "widget-pagination") == (
        "widget-pagination"
    )
    assert commits.story_description(tmp_path, "gone.md", "widget-pagination") == (
        "widget-pagination"
    )
    assert commits.story_description(tmp_path, "", "widget-pagination") == "widget-pagination"
