"""The reading of a changed member file happens in the member checkout, which the turn is given as an added directory."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import cast

from okf_book.support import MEMBER, MEMBER_FILE, MEMBER_SOURCE, ScriptedRunner, Workspace
from ostler.stamp import digest_file
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv

from workhorse_workflows import okf_book
from workhorse_workflows.okf_book.main.nodes.source_view import VIEW_DIR
from workhorse_workflows.okf_book.main.reground_book_flow import RegroundBook
from workhorse_workflows.okf_book.workflow import workflow

CHANGED = MEMBER_SOURCE + "\n# changed\n"


def _book(workspace: Workspace) -> None:
    stamped = digest_file(MEMBER_SOURCE.encode())
    page = workspace.docs / "docs/services/ledger/handlers.md"
    page.parent.mkdir(parents=True)
    cited = f"repo://{MEMBER}/{MEMBER_FILE}::list_entries@{stamped}"
    _ = page.write_text(f"---\ntype: screen\nslug: handlers\ntitle: Handlers\n---\n# Handlers\n\n- code: `{cited}`\n\nWhat lists entries.\n", encoding="utf-8")
    _ = (workspace.member / MEMBER_FILE).write_text(CHANGED, encoding="utf-8")


def _reground(workspace: Workspace, tmp_path: Path, repo: Path | None = None) -> tuple[list[tuple[str, str]], ScriptedRunner]:
    read: list[tuple[str, str]] = []

    def reading(args: dict[str, object]) -> dict[str, object]:
        path = str(args["path"])
        shown = workspace.docs / path
        read.append((path, shown.read_text(encoding="utf-8") if shown.is_file() else ""))
        return {"affected": []}

    writer = ArtifactWriter("okf-book", tmp_path / "runs", run_id="t0")
    runner = ScriptedRunner({"reground-file": reading})
    env = RunEnv(
        writer=writer,
        workflow_dir=Path(okf_book.__file__).parent,
        session_id_path=writer.run_dir / ".session_id",
        config=RunConfig(),
        nodes=workflow.nodes,
        agent_runner=runner,
    )
    _ = cast("object", drive(RegroundBook(repo_dir=str(repo or workspace.member), service="ledger"), env))
    return read, runner


def test_a_changed_member_file_is_read_in_the_member_checkout(workspace: Workspace, tmp_path: Path) -> None:
    _book(workspace)

    read, _ = _reground(workspace, tmp_path)

    assert read == [((workspace.member / MEMBER_FILE).as_posix(), CHANGED)]


def test_the_turn_is_given_the_member_checkout_as_an_added_directory(workspace: Workspace, tmp_path: Path) -> None:
    _book(workspace)

    _, runner = _reground(workspace, tmp_path)

    assert [node.add_dirs for node in runner.nodes] == [[str(workspace.member)]]


def test_no_source_view_is_built_for_the_reading(workspace: Workspace, tmp_path: Path) -> None:
    _book(workspace)

    _ = _reground(workspace, tmp_path)

    assert not (workspace.docs / VIEW_DIR / MEMBER).exists()
    assert not (workspace.member / VIEW_DIR).exists()
    assert (workspace.member / MEMBER_FILE).read_text(encoding="utf-8") == CHANGED


def test_a_changed_file_of_the_books_own_repository_is_read_with_no_added_directory(workspace: Workspace, tmp_path: Path) -> None:
    stamped = digest_file(MEMBER_SOURCE.encode())
    page = workspace.docs / "docs/services/ledger/handlers.md"
    page.parent.mkdir(parents=True)
    cited = f"{MEMBER_FILE}::list_entries@{stamped}"
    _ = page.write_text(f"---\ntype: screen\nslug: handlers\ntitle: Handlers\n---\n# Handlers\n\n- code: `{cited}`\n\nWhat lists entries.\n", encoding="utf-8")
    (workspace.docs / MEMBER_FILE).parent.mkdir(parents=True, exist_ok=True)
    _ = (workspace.docs / MEMBER_FILE).write_text(MEMBER_SOURCE, encoding="utf-8")
    _ = subprocess.run(["git", "add", "-A"], cwd=workspace.docs, check=True)
    _ = subprocess.run(["git", "commit", "-qm", "stamped"], cwd=workspace.docs, check=True)
    _ = (workspace.docs / MEMBER_FILE).write_text(CHANGED, encoding="utf-8")

    read, runner = _reground(workspace, tmp_path, workspace.docs)

    assert read == [(MEMBER_FILE, CHANGED)]
    assert [node.add_dirs for node in runner.nodes] == [[]]
