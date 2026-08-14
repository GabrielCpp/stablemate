"""Which doctor findings a story owns when it names a whole document as affected.

A book file is long and its debt is old. A story that adds two bullets near the top of one
was being charged with every pre-existing error below them, because naming the file was read
as owning the file. That is not a hypothetical: a live story spent a documentation lap
hunting a `missing-placement` measurement for a dialog 250 lines past anything it wrote.

So the scoping is tested here directly rather than through the flow, since what it turns on
is a *git diff* and an anchor's line span — two inputs an end-to-end docs run cannot vary
deliberately. The graph is built by hand for the same reason: `Ostler`'s loader is exercised for real
in `test_flow.py`, and what these tests need of it is three anchors at chosen lines.
"""
from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from ostler.model import Graph, UINode

from workhorse_workflows.coder.shared.docs import _finding_affects_nodes, story_touched_lines

DOC_REL = "docs/features/app/editor.md"

#: A document with three anchors, spread far enough apart that a diff can land inside one
#: without touching its neighbours — the whole shape under test.
DOC = "\n".join(
    ["# Editor", "", "intro prose", ""]
    + ["## interaction: toggle bold", "", "- role: button", ""]
    + ["filler"] * 20
    + ["## interaction: cross-reference picker", "", "- role: dialog", ""]
    + ["filler"] * 20
    + ["## interaction: create document", "", "- role: button", ""]
)
TOGGLE_LINE = 5
PICKER_LINE = 29
CREATE_LINE = 53


def _graph(root: Path) -> Graph:
    """The three anchors as ostler itself models them, at the lines the document puts them."""
    return Graph(
        root=root,
        org_name="example-org",
        profile="full",
        doc_roots={},
        ui_nodes=[
            UINode(
                type="interaction",
                kind="section",
                id=f"{DOC_REL}#{anchor}",
                path=root / DOC_REL,
                anchor=anchor,
                line=line,
                level=2,
            )
            for anchor, line in (
                ("toggle-bold", TOGGLE_LINE),
                ("cross-reference-picker", PICKER_LINE),
                ("create-document", CREATE_LINE),
            )
        ],
    )


def _finding(line: int) -> dict[str, Any]:
    return {"severity": "error", "code": "missing-placement", "path": DOC_REL, "line": line}


@pytest.fixture
def book(
    repo: Path,
    git: Callable[..., subprocess.CompletedProcess],
    write: Callable[[Path, str], Path],
) -> Path:
    """The document committed, so a later edit is a diff and not a new file."""
    write(repo / DOC_REL, DOC)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "the book as it stood")
    return repo


def _edit(repo: Path, line: int, text: str) -> None:
    """Change one 1-indexed line of the document in the worktree."""
    lines = (repo / DOC_REL).read_text(encoding="utf-8").splitlines()
    lines[line - 1] = text
    (repo / DOC_REL).write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_a_story_owns_the_anchors_its_own_edits_reached(book: Path) -> None:
    """The defect this scoping exists for: one edit, not the document's whole history."""
    _edit(book, TOGGLE_LINE + 2, "- role: switch")
    touched = story_touched_lines(book, {DOC_REL}, logging.getLogger(__name__))
    graph = _graph(book)

    assert _finding_affects_nodes(graph, _finding(TOGGLE_LINE), {DOC_REL}, touched)
    assert not _finding_affects_nodes(graph, _finding(PICKER_LINE), {DOC_REL}, touched)
    assert not _finding_affects_nodes(graph, _finding(CREATE_LINE), {DOC_REL}, touched)


def test_naming_an_anchor_owns_it_whatever_the_diff_says(book: Path) -> None:
    """The author's claim is the stronger one — it is what the gate asks for in point 1."""
    touched = story_touched_lines(book, set(), logging.getLogger(__name__))
    affected = {f"{DOC_REL}#cross-reference-picker"}

    assert _finding_affects_nodes(_graph(book), _finding(PICKER_LINE), affected, touched)


def test_a_finding_against_the_document_itself_stays_the_story_s(book: Path) -> None:
    """No line means no anchor to place it in, so the file's owner answers for it."""
    _edit(book, TOGGLE_LINE + 2, "- role: switch")
    touched = story_touched_lines(book, {DOC_REL}, logging.getLogger(__name__))
    finding = {"severity": "error", "code": "missing-title", "path": DOC_REL}

    assert _finding_affects_nodes(_graph(book), finding, {DOC_REL}, touched)


def test_an_untracked_document_is_the_story_s_in_its_entirety(
    repo: Path, write: Callable[[Path, str], Path]
) -> None:
    """A file this story created has no `HEAD` side to diff, and every line of it is new."""
    write(repo / DOC_REL, DOC)
    touched = story_touched_lines(repo, {DOC_REL}, logging.getLogger(__name__))

    assert touched[DOC_REL] is None
    assert _finding_affects_nodes(_graph(repo), _finding(PICKER_LINE), {DOC_REL}, touched)


def test_an_unreadable_diff_charges_the_story_rather_than_excusing_it(
    tmp_path: Path, write: Callable[[Path, str], Path]
) -> None:
    """Fail-closed, the same direction the rest of the gate fails in."""
    write(tmp_path / "bare" / DOC_REL, DOC)
    touched = story_touched_lines(tmp_path / "bare", {DOC_REL}, logging.getLogger(__name__))

    assert touched == {DOC_REL: None}
    graph = _graph(tmp_path / "bare")

    assert _finding_affects_nodes(graph, _finding(PICKER_LINE), {DOC_REL}, touched)


def test_a_finding_in_a_file_this_story_never_named_is_not_its_problem(book: Path) -> None:
    """Unchanged, and the reason the whole filter came first: other books stay other books."""
    touched = story_touched_lines(book, {DOC_REL}, logging.getLogger(__name__))

    other = {"docs/other.md"}

    assert not _finding_affects_nodes(_graph(book), _finding(PICKER_LINE), other, touched)
