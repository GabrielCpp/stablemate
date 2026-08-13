"""Integrity tests for the frozen `seat-booking` app.

The app is what standalone QA is *scored against*, so a defect in it is worse than a
defect in the harness: the harness fails loudly, the fixture just moves the number. These
tests cover the three ways it can rot silently.

* **The book stops being clean.** A fixture with an `unparsed-check` in it hands the run
  under measurement a broken obligation and then counts the resulting miss against QA.
* **A story's manifest stops matching the tree.** `diff.yml` is what materialization reads;
  a path renamed in the app and not in the manifest produces a trial whose diff is not the
  story's, which is invisible in the score and fatal to it.
* **Materialization stops producing a worktree diff.** QA mints obligations from
  uncommitted changes; a trial that commits everything obligates nothing and every run
  passes. That failure mode reads exactly like "QA found no problems".

No docker and no agent here — this is the app and the manifest logic, nothing that costs
money to check.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

BENCHMARKS = Path(__file__).parents[1]
APP = BENCHMARKS / "apps" / "seat-booking"

_spec = importlib.util.spec_from_file_location("replay", BENCHMARKS / "replay.py")
assert _spec is not None and _spec.loader is not None  # noqa: S101 - a real file on disk
replay = importlib.util.module_from_spec(_spec)
sys.modules["replay"] = replay
_spec.loader.exec_module(replay)

STORIES = ("seat-map", "seat-hold", "confirm-booking")


def manifest(story: str) -> dict[str, list[str]]:
    data = yaml.safe_load((APP / "stories" / story / "diff.yml").read_text(encoding="utf-8"))
    return {"changed": list(data.get("changed") or []), "added": list(data.get("added") or [])}


# ── the book ──────────────────────────────────────────────────────────────────────────


def test_doctor_is_clean() -> None:
    """0 errors and 0 warnings, which is the bar the app was authored to.

    Warnings count here where they would not in a working repo: `undeclared-obligation` and
    `compound-normative-bullet` are both warnings, and both describe a book that cannot be
    used as an answer key — the first leaves a bullet nothing has to verify, the second a
    bullet two different verdicts can both honestly claim.
    """
    from ostler.api import Ostler  # noqa: PLC0415 - a heavy import only this test needs

    report = Ostler(APP).doctor()
    assert report["errors"] == 0, report["findings"]
    assert report["warnings"] == 0, report["findings"]


def test_the_fixture_ships_the_stories_it_claims() -> None:
    from ostler.api import Ostler  # noqa: PLC0415

    okf = Ostler(APP)
    slugs = {node.get("slug") or node.get("name") for node in okf.list("story")}
    assert set(STORIES) <= slugs


# ── the manifests ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("story", STORIES)
def test_every_manifest_path_exists_in_the_app(story: str) -> None:
    diff = manifest(story)
    for rel in [*diff["changed"], *diff["added"]]:
        assert (APP / rel).is_file(), f"{story}: {rel} is in diff.yml but not in the app tree"


@pytest.mark.parametrize("story", STORIES)
def test_changed_paths_have_a_pre_image_and_added_paths_do_not(story: str) -> None:
    """The asymmetry is the whole manifest contract.

    A `changed:` path with no `pre/` would be committed at its finished content and
    disappear from the story's diff; an `added:` path *with* one would be committed at all,
    which is the opposite of added. Both produce a trial that runs and reports a number.
    """
    diff = manifest(story)
    for rel in diff["changed"]:
        assert (APP / "stories" / story / "pre" / rel).is_file(), f"{story}: no pre/ for {rel}"
    for rel in diff["added"]:
        assert not (APP / "stories" / story / "pre" / rel).exists(), (
            f"{story}: {rel} is added but has a pre/ image"
        )


@pytest.mark.parametrize("story", STORIES)
def test_no_image_names_a_path_the_manifest_does_not(story: str) -> None:
    """A stale `pre/` or `post/` file is dead weight that reads as coverage."""
    diff = manifest(story)
    declared = {*diff["changed"], *diff["added"]}
    for phase in ("pre", "post"):
        root = APP / "stories" / story / phase
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                rel = path.relative_to(root).as_posix()
                assert rel in declared, f"{story}: {phase}/{rel} is not in diff.yml"


def test_each_story_starts_where_the_previous_one_ended() -> None:
    """Story N's `pre/` image is story N-1's `post/` image, byte for byte.

    Without this the stories are three unrelated snapshots rather than one history, and a
    trial on story 3 can present code story 2's trial never contained — so the same defect
    scores differently depending on which story it was seeded in.
    """
    for earlier, later in zip(STORIES, STORIES[1:], strict=False):
        for rel in manifest(later)["changed"]:
            after = replay.story_image(APP, earlier, rel, phase="post")
            before = APP / "stories" / later / "pre" / rel
            assert before.read_bytes() == after.read_bytes(), (
                f"{later}/pre/{rel} is not {earlier}'s post-image"
            )


# ── materialization ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("story", STORIES)
def test_materialize_leaves_exactly_this_story_uncommitted(story: str, tmp_path: Path) -> None:
    dest = replay.materialize(APP, story, tmp_path / "seat-booking")
    diff = manifest(story)

    porcelain = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=dest, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    dirty = {line[3:]: line[:2].strip() for line in porcelain}

    assert set(dirty) == {*diff["changed"], *diff["added"]}
    for rel in diff["changed"]:
        assert dirty[rel] == "M"
    for rel in diff["added"]:
        assert dirty[rel] == "??"


@pytest.mark.parametrize("story", STORIES)
def test_materialize_puts_this_story_content_in_the_worktree(story: str, tmp_path: Path) -> None:
    """The worktree holds the story's *post* image — the app tree only for the last story."""
    dest = replay.materialize(APP, story, tmp_path / "seat-booking")
    diff = manifest(story)
    for rel in [*diff["changed"], *diff["added"]]:
        expected = replay.story_image(APP, story, rel, phase="post").read_bytes()
        assert (dest / rel).read_bytes() == expected


def test_materialize_does_not_ship_the_answer_key(tmp_path: Path) -> None:
    """The seeded-defect list and the pre-images must not reach the tree QA reads.

    An agent that can read `defects.yml` is not being measured on detection, and nothing in
    its output would say so.
    """
    dest = replay.materialize(APP, "seat-hold", tmp_path / "seat-booking")
    for name in replay.NOT_THE_APP:
        assert not (dest / name).exists(), f"{name} was copied into the trial tree"


def test_materialized_book_is_unchanged(tmp_path: Path) -> None:
    """The book sits at its authored state on both sides of HEAD.

    A trial whose book is also uncommitted would let QA read the obligations as part of the
    work under review, which is the situation the OKF context is built to avoid.
    """
    dest = replay.materialize(APP, "confirm-booking", tmp_path / "seat-booking")
    changed_docs = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", "docs"],
        cwd=dest, capture_output=True, text=True, check=True,
    ).stdout
    assert changed_docs == ""


def test_fixture_points_at_the_app_and_names_the_trial_dir() -> None:
    fixture = replay.load_fixture("seat-booking")
    assert fixture.app == APP
    # farrier derives generated skill names from the basename; anything else dangles.
    assert fixture.repo_dirname == "seat-booking"
    assert fixture.slugs("qa") == list(STORIES)
