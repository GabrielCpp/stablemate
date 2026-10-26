"""The reading of a changed member file goes through a source view under the docs home, the one tree the confined reading can see."""
from __future__ import annotations

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


def _reground(workspace: Workspace, tmp_path: Path) -> list[tuple[str, str]]:
    read: list[tuple[str, str]] = []

    def reading(args: dict[str, object]) -> dict[str, object]:
        path = str(args["path"])
        shown = workspace.docs / path
        read.append((path, shown.read_text(encoding="utf-8") if shown.is_file() else ""))
        return {"affected": []}

    writer = ArtifactWriter("okf-book", tmp_path / "runs", run_id="t0")
    env = RunEnv(
        writer=writer,
        workflow_dir=Path(okf_book.__file__).parent,
        session_id_path=writer.run_dir / ".session_id",
        config=RunConfig(),
        nodes=workflow.nodes,
        agent_runner=ScriptedRunner({"reground-file": reading}),
    )
    _ = cast("object", drive(RegroundBook(repo_dir=str(workspace.member), service="ledger"), env))
    return read


def test_a_changed_member_file_is_read_from_a_view_under_the_docs_home(workspace: Workspace, tmp_path: Path) -> None:
    _book(workspace)

    read = _reground(workspace, tmp_path)

    assert read == [(f"{VIEW_DIR}/{MEMBER}/{MEMBER_FILE}", CHANGED)]


def test_the_view_leaves_the_member_checkout_as_it_was(workspace: Workspace, tmp_path: Path) -> None:
    _book(workspace)

    _ = _reground(workspace, tmp_path)

    assert not (workspace.member / VIEW_DIR).exists()
    assert (workspace.member / MEMBER_FILE).read_text(encoding="utf-8") == CHANGED
