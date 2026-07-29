"""check-story-grounding.py — the deterministic pre-gate for a written story.

Two machine-checkable preconditions, and deliberately nothing else (semantic judgment is the
``audit-story`` agent's job downstream):

  - every seed item the story ``covers`` exists in the epic's seeds (no phantom scope);
  - **iff** the graph actually holds OKF UI nodes: the story cites at least one of them, and
    every citation it makes resolves.

The second one is armed on the *nodes*, not on a configured path — the author only ever reads
the book, so a greenfield repo whose okf-builder has not run has nothing to cite and must not
be hard-failed for it. Both halves are exercised here, in both arming states. All data comes
from the real ostler graph.
"""
from __future__ import annotations

from pathlib import Path

from conftest import run_script, write_epic, write_ui_node

FEAT = "docs/features"
SCREEN = f"{FEAT}/gui/screens/settings.md"


def story_body(context: str) -> str:
    """A structurally-good story whose ``## Context`` carries the citations under test."""
    return (
        "---\ntype: story\nslug: 01-settings\nstatus: not_started\n---\n\n"
        "# Story: 01-settings\n\n"
        f"## Context\n\n{context}\n\n"
        "## Acceptance Criteria\n\n"
        "- The profile form saves and shows the saved values on reload.\n\n"
        "## Implementation Status\n\n"
        "- **Status**: Not started\n"
    )


def _epic_with_story(repo: Path, *, seed_ids: list[str], covers: list[str],
                     context: str) -> tuple[str, str]:
    write_epic(
        repo, "e1",
        seeds=[{"id": s} for s in seed_ids],
        stories=[{"slug": "01-settings", "covers": covers, "body": story_body(context)}],
    )
    return "docs/epics/e1/stories/01-settings", "docs/epics/e1"


def gate(repo: Path, story_dir: str, epic_dir: str, features_dir: str = FEAT) -> dict:
    return run_script("check-story-grounding.py", story_dir, epic_dir, features_dir, repo=repo)


# ── the citation half: armed by the presence of UI nodes ──────────────────────────────────

def test_citing_a_file_node_passes(tmp_path: Path):
    write_ui_node(tmp_path, SCREEN, components=["Save profile"])
    story_dir, epic_dir = _epic_with_story(
        tmp_path, seed_ids=["s1"], covers=["s1"],
        context=f"Reworks [the settings screen]({SCREEN}).",
    )
    out = gate(tmp_path, story_dir, epic_dir)
    assert out["story_grounding_ok"] == "yes", out["story_grounding_errors"]


def test_citing_a_section_node_passes(tmp_path: Path):
    """The narrowest true node is a section — ``path#anchor`` is a node id like any other."""
    write_ui_node(tmp_path, SCREEN, components=["Save profile"])
    story_dir, epic_dir = _epic_with_story(
        tmp_path, seed_ids=["s1"], covers=["s1"],
        context=f"Reworks [Save profile]({SCREEN}#save-profile).",
    )
    out = gate(tmp_path, story_dir, epic_dir)
    assert out["story_grounding_ok"] == "yes", out["story_grounding_errors"]


def test_relative_citation_resolves(tmp_path: Path):
    """A story lives 4 dirs deep; a link written relative to it names the same node."""
    write_ui_node(tmp_path, SCREEN, components=["Save profile"])
    story_dir, epic_dir = _epic_with_story(
        tmp_path, seed_ids=["s1"], covers=["s1"],
        context="Reworks [settings](../../../../features/gui/screens/settings.md).",
    )
    out = gate(tmp_path, story_dir, epic_dir)
    assert out["story_grounding_ok"] == "yes", out["story_grounding_errors"]


def test_no_citation_fails_when_the_book_has_nodes(tmp_path: Path):
    write_ui_node(tmp_path, SCREEN, components=["Save profile"])
    story_dir, epic_dir = _epic_with_story(
        tmp_path, seed_ids=["s1"], covers=["s1"],
        context="Reworks the settings screen so profiles save.",
    )
    out = gate(tmp_path, story_dir, epic_dir)
    assert out["story_grounding_ok"] == "no"
    assert "cites no OKF node" in out["story_grounding_errors"]


def test_dangling_citation_fails_and_names_the_path(tmp_path: Path):
    """A mistyped id must not read as grounding — that is the whole reason it is reported."""
    write_ui_node(tmp_path, SCREEN, components=["Save profile"])
    story_dir, epic_dir = _epic_with_story(
        tmp_path, seed_ids=["s1"], covers=["s1"],
        context=f"Reworks [settings]({FEAT}/gui/screens/setttings.md).",
    )
    out = gate(tmp_path, story_dir, epic_dir)
    assert out["story_grounding_ok"] == "no"
    assert "setttings.md" in out["story_grounding_errors"]


def test_dangling_citation_fails_even_alongside_a_good_one(tmp_path: Path):
    write_ui_node(tmp_path, SCREEN, components=["Save profile"])
    story_dir, epic_dir = _epic_with_story(
        tmp_path, seed_ids=["s1"], covers=["s1"],
        context=f"Reworks [settings]({SCREEN}) and [Save]({SCREEN}#save-prophile).",
    )
    out = gate(tmp_path, story_dir, epic_dir)
    assert out["story_grounding_ok"] == "no"
    assert "save-prophile" in out["story_grounding_errors"]


def test_no_ui_nodes_disarms_the_citation_check(tmp_path: Path):
    """Greenfield: the okf-builder has not run, so there is nothing to cite. Not a failure."""
    story_dir, epic_dir = _epic_with_story(
        tmp_path, seed_ids=["s1"], covers=["s1"],
        context="Builds a brand-new settings screen from the mockup.",
    )
    out = gate(tmp_path, story_dir, epic_dir)
    assert out["story_grounding_ok"] == "yes", out["story_grounding_errors"]


# ── the seed half: unaffected by the book ─────────────────────────────────────────────────

def test_phantom_seed_item_fails(tmp_path: Path):
    write_ui_node(tmp_path, SCREEN, components=["Save profile"])
    story_dir, epic_dir = _epic_with_story(
        tmp_path, seed_ids=["s1"], covers=["ghost"],
        context=f"Reworks [the settings screen]({SCREEN}).",
    )
    out = gate(tmp_path, story_dir, epic_dir)
    assert out["story_grounding_ok"] == "no"
    assert "ghost" in out["story_grounding_errors"]


def test_phantom_seed_item_fails_without_any_ui_nodes(tmp_path: Path):
    """The seed check is structural — it does not ride on the book being built."""
    story_dir, epic_dir = _epic_with_story(
        tmp_path, seed_ids=["s1"], covers=["ghost"],
        context="Builds a brand-new settings screen from the mockup.",
    )
    out = gate(tmp_path, story_dir, epic_dir)
    assert out["story_grounding_ok"] == "no"
    assert "ghost" in out["story_grounding_errors"]


def test_missing_args_fail_closed(tmp_path: Path):
    out = run_script("check-story-grounding.py", "", "", FEAT, repo=tmp_path)
    assert out["story_grounding_ok"] == "no"
