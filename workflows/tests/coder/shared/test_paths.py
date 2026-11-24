"""Where the workflow puts the files it writes into somebody else's checkout."""
from __future__ import annotations

from pathlib import Path

import pytest

from workhorse_workflows.coder.shared import paths, resolution
from _epics import epics_root


def test_a_gate_with_no_epic_folder_writes_under_the_operator_dir(tmp_path: Path) -> None:
    """Not the repo root."""
    got = paths.operator_context_path(tmp_path, "dirty-tree-operator", "sign-in")
    assert got == tmp_path / ".agents/operator/dirty-tree-operator-context.sign-in.md"
    assert paths.operator_context_path(tmp_path, "ci-operator") == (
        tmp_path / ".agents/operator/ci-operator-context.md")


def test_an_epic_that_has_a_folder_still_gets_its_questions_next_to_it(tmp_path: Path) -> None:
    """Rung 1 is unchanged: the operator is already reading the epic, so the file goes there rather than into a directory nothing points at."""
    epic = epics_root() / "0001-checkout"
    epic.mkdir(parents=True)
    (epic / "epic.md").write_text("# checkout\n", encoding="utf-8")
    assert paths.operator_context_path(tmp_path, "ci-operator", "checkout") == (
        epic / "ci-operator-context.md")


def test_the_operator_dir_files_are_still_excused_from_the_dirty_check(tmp_path: Path) -> None:
    """The naming survived the move, because rung 1 puts one in the docs tree where no gitignore covers it — `is_gate_context` is what keeps that from parking a story twice."""
    for gate in ("dirty-tree-operator", "ci-operator", "merge-operator"):
        assert paths.is_gate_context(paths.operator_context_path(tmp_path, gate, "e"))


def test_the_product_pages_sit_in_the_product_folder_of_a_repository_that_keeps_its_book(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STABLEMATE_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "agents.yml").write_text("book:\n  home: repo\n", encoding="utf-8")
    assert resolution.product_dir(str(repo)) == repo.resolve() / "product"
    assert not hasattr(paths, "decisions_dir")
    assert not hasattr(resolution, "decisions_dir")
