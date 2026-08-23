"""Where the workflow puts the files it writes into somebody else's checkout.

Two of these locations are load-bearing in a way a path join does not look. A gate's
question is not the repo's content, and a decision record is documentation — neither
belongs in the top-level listing, and one of them actively breaks the gate that wrote it.
"""
from __future__ import annotations

from pathlib import Path

from workhorse_workflows.coder.shared import paths


def test_a_gate_with_no_epic_folder_writes_under_the_operator_dir(tmp_path: Path) -> None:
    """Not the repo root. `dirty-tree-operator` is the reason this matters most: its whole
    subject is uncommitted work, and a question dropped at the root joins the listing the
    operator is being asked to settle.
    """
    got = paths.operator_context_path(tmp_path, "dirty-tree-operator", "sign-in")
    assert got == tmp_path / ".agents/operator/dirty-tree-operator-context.sign-in.md"
    assert paths.operator_context_path(tmp_path, "ci-operator") == (
        tmp_path / ".agents/operator/ci-operator-context.md")


def test_an_epic_that_has_a_folder_still_gets_its_questions_next_to_it(tmp_path: Path) -> None:
    """Rung 1 is unchanged: the operator is already reading the epic, so the file goes
    there rather than into a directory nothing points at.
    """
    epic = tmp_path / "docs" / "epics" / "0001-checkout"
    epic.mkdir(parents=True)
    # ostler resolves a bare slug to its numbered folder through the epic document, not
    # through the directory name alone.
    (epic / "epic.md").write_text("# checkout\n", encoding="utf-8")
    assert paths.operator_context_path(tmp_path, "ci-operator", "checkout") == (
        epic / "ci-operator-context.md")


def test_the_operator_dir_files_are_still_excused_from_the_dirty_check(tmp_path: Path) -> None:
    """The naming survived the move, because rung 1 puts one in the docs tree where no
    gitignore covers it — `is_gate_context` is what keeps that from parking a story twice.
    """
    for gate in ("dirty-tree-operator", "ci-operator", "merge-operator"):
        assert paths.is_gate_context(paths.operator_context_path(tmp_path, gate, "e"))


def test_decisions_land_with_the_documents_not_beside_the_service_directories(
    tmp_path: Path,
) -> None:
    """A decision record is a document a person reads, so it sits under `docs/` with the
    backlog and the epics rather than as a stray top-level folder.
    """
    assert paths.decisions_dir(tmp_path) == tmp_path / "docs" / "decisions"
    # Derived from the backlog rather than joined independently, so the two stay together
    # if ostler ever moves the convention.
    assert paths.decisions_dir(tmp_path).name == "decisions"
    assert paths.backlog_file(tmp_path, "").startswith("docs/")
