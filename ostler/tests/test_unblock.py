"""`ostler unblock` — clearing the give-up stamps a coder run leaves on stories.

The stamp is left on stories by coder runs that predate the give-up hard-fail, and read by
whatever agent picks the story up next. It is prose, it lands in two places per story.md, and a run stamps several
stories in one pass — which is what makes retyping it by hand the wrong tool.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from ostler import cli, crud, select
from ostler.model import load

from conftest import present

GIVE_UP = "QA give-up after 4 attempts — needs manual review: docs/specs/01-foo/qa.md"
DOCS_BLOCKED = "Docs blocked — needs manual review: documentation did not converge"


@pytest.mark.parametrize("status", [GIVE_UP, DOCS_BLOCKED, "Blocked", "blocked"])
def test_the_give_up_vocabulary_reads_as_blocked(status: str):
    assert select.is_blocked(status)


@pytest.mark.parametrize("status", ["Not started", "In progress", "QA passed", "Reviewed",
                                    "Review fixes applied", ""])
def test_an_ordinary_status_is_not_blocked(status: str):
    assert not select.is_blocked(status)


def test_unblock_rewrites_both_places_the_stamp_lives(repo: Path):
    """Frontmatter *and* the body bullet — `select` reads one, a human reads the other."""
    crud.set_status(load(repo), "01-foo", GIVE_UP)

    res = crud.unblock(load(repo), story="01-foo")

    assert res.ok, res.message
    text = (repo / "docs/epics/epic-a/stories/01-foo/story.md").read_text(encoding="utf-8")
    assert "status: Not started" in text
    assert "- **Status**: Not started" in text
    assert "give-up" not in text


def test_unblock_never_touches_a_finished_story(repo: Path):
    """The failure this must not have: resetting work that passed.

    `--all` sweeps the graph, so the guard is the vocabulary check and nothing else.
    """
    crud.set_status(load(repo), "01-foo", "QA passed")
    crud.set_status(load(repo), "01-bar", GIVE_UP)

    res = crud.unblock(load(repo))

    assert res.ok, res.message
    graph = load(repo)
    assert present(graph.find_story("01-foo"))[1].status == "QA passed"
    assert present(graph.find_story("01-bar"))[1].status == "Not started"


def test_unblock_is_idempotent(repo: Path):
    """A second run writes nothing and still succeeds, so a script can run it unconditionally."""
    crud.set_status(load(repo), "01-foo", GIVE_UP)
    crud.unblock(load(repo), story="01-foo")

    res = crud.unblock(load(repo), story="01-foo")

    assert res.ok and res.paths == []
    assert "nothing to unblock" in res.message


def test_unblock_scopes_to_one_epic(repo: Path):
    crud.set_status(load(repo), "01-foo", GIVE_UP)
    crud.set_status(load(repo), "01-bar", GIVE_UP)

    res = crud.unblock(load(repo), epic="epic-a")

    assert res.ok, res.message
    graph = load(repo)
    assert present(graph.find_story("01-foo"))[1].status == "Not started"
    assert present(graph.find_story("01-bar"))[1].status == GIVE_UP, "epic-b was out of scope"


def test_unblock_restores_a_chosen_status(repo: Path):
    """An epic given up mid-review goes back to review, not to the start of the pipeline."""
    crud.set_status(load(repo), "01-foo", DOCS_BLOCKED)

    res = crud.unblock(load(repo), story="01-foo", status="Reviewed")

    assert res.ok, res.message
    assert present(load(repo).find_story("01-foo"))[1].status == "Reviewed"


def test_unblock_reports_an_unknown_target(repo: Path):
    assert not crud.unblock(load(repo), story="99-nope").ok
    assert not crud.unblock(load(repo), epic="no-such-epic").ok
    assert not crud.unblock(load(repo), story="01-foo", epic="epic-a").ok


def test_cli_requires_a_scope(repo: Path, capsys: pytest.CaptureFixture[str]):
    """A bare `ostler unblock` would sweep the repo — the widest scope must be spelled out."""
    crud.set_status(load(repo), "01-foo", GIVE_UP)

    assert cli.main(["-C", str(repo), "unblock"]) == 1
    assert present(load(repo).find_story("01-foo"))[1].status == GIVE_UP
    assert "--all" in capsys.readouterr().out

    assert cli.main(["-C", str(repo), "unblock", "--all"]) == 0
    assert present(load(repo).find_story("01-foo"))[1].status == "Not started"


def test_cli_refuses_all_together_with_a_narrower_scope(repo: Path):
    assert cli.main(["-C", str(repo), "unblock", "01-foo", "--all"]) == 1
