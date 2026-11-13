from __future__ import annotations

import logging
from pathlib import Path

from _books import write_book
from _epics import epics_root
from ostler import Ostler

from workhorse_workflows.author.shared.nodes.stories import check_story_grounding

EPIC = "accounts"


def _epic(repo: Path, covers: list[str]) -> tuple[str, str]:
    write_book(repo, "web-app", screens=True)
    okf = Ostler(repo)
    okf.create_epic(EPIC, "Accounts")
    for seed_id in ("a", "b"):
        assert okf.add_seed(EPIC, seed_id, status="researched", summary=seed_id).ok
    assert okf.create_story(EPIC, "01-sign-in", "Sign in", covers=covers).ok
    epic_dir = epics_root() / "0001-accounts"
    return str(epic_dir / "stories/01-sign-in"), str(epic_dir)


def test_a_story_with_no_page_citation_is_grounded(logger: logging.Logger, repo: Path) -> None:
    story_dir, epic_dir = _epic(repo, ["a"])
    stale = repo / "docs/services/x/gui/screens/a.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("---\ntype: screen\nslug: a\ntitle: A\n---\n# A\n", encoding="utf-8")

    result = check_story_grounding(logger, story_dir=story_dir, epic_dir=epic_dir, repo_dir=str(repo))

    assert result.ok is True, result.errors


def test_a_story_claiming_a_seed_outside_its_epic_is_phantom_scope(
    logger: logging.Logger, repo: Path
) -> None:
    story_dir, epic_dir = _epic(repo, ["a"])
    assert Ostler(repo).remove_seed(EPIC, "a").ok

    result = check_story_grounding(logger, story_dir=story_dir, epic_dir=epic_dir, repo_dir=str(repo))

    assert result.ok is False
    assert "phantom scope" in result.errors
