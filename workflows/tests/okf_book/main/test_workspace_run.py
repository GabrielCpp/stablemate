"""A run in a two-repo workspace reads the product member's source and commits the book to the docs home, leaving the member alone."""
from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from okf_book.support import MEMBER, MEMBER_FILE, MEMBER_FOLDER, MEMBER_SOURCE, ScriptedRunner, Workspace, git, head_of, status_of
from ostler import doctor, index
from ostler.model import load
from ostler.provenance import effective_checkouts
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv

from workhorse_workflows import okf_book
from workhorse_workflows.okf_book.main import exercise_book_flow
from workhorse_workflows.okf_book.main.nodes.stale_citations import stale_files
from workhorse_workflows.okf_book.main.nodes.surface import Surface, SurfaceKind
from workhorse_workflows.okf_book.shared.book_run import CompileOutcome, ExerciseResult, StackReadiness
from workhorse_workflows.okf_book.shared.citations import cites_changed_file
from workhorse_workflows.okf_book.shared.source_coverage import uncited_by_folder
from workhorse_workflows.okf_book.shared.source_repo import SourceRepo
from workhorse_workflows.okf_book.workflow import OkfBook, workflow

SERVICE = "ledger"
BOOK = f"docs/services/{SERVICE}"
CITED = f"repo://{MEMBER}/{MEMBER_FILE}::list_entries"

PAGES = {
    "index.md": "---\nexercised: false\n---\n# Ledger\n",
    "entries.md": "---\ntype: entries\ntitle: Ledger\n---\n# Ledger\n\n- [Ledger API](ledger-api.md)\n- [Read entries](flows/read-entries.md)\n",
    "ledger-api.md": (
        f"---\ntype: server\nslug: ledger-api\ntitle: Ledger API\n---\n# Ledger API\n\n- code: `{CITED}`\n\n"
        "## Endpoints\n\n- [list-entries](list-entries.md)\n"
    ),
    "list-entries.md": (
        "---\ntype: endpoint\nslug: list-entries\ntitle: list-entries\n---\n# list-entries\n\n"
        f"- server: [Ledger API](ledger-api.md)\n- method: GET\n- path: /entries\n- does: lists the entries\n- code: {CITED}\n"
    ),
    "flows/read-entries.md": (
        "---\ntype: flow\nslug: read-entries\ntitle: Read entries\n---\n# Read entries\n\n"
        "- fixture: none, because the route lists whatever is there\n- steps:\n  - [list-entries](../list-entries.md)\n"
    ),
}


def _write_book(args: dict[str, object], seen: dict[str, str], docs: Path) -> dict[str, object]:
    view = Path(str(args["source_view"]))
    seen.update({path.relative_to(view).as_posix(): path.read_text(encoding="utf-8") for path in view.rglob("*") if path.is_file()})
    seen["source_folder"] = str(args["source_folder"])
    for name, text in PAGES.items():
        page = docs / BOOK / name
        page.parent.mkdir(parents=True, exist_ok=True)
        _ = page.write_text(text, encoding="utf-8")
    return {}


def _stub_exercise(monkeypatch: pytest.MonkeyPatch) -> None:
    def _compile(*_args: object) -> CompileOutcome:
        return CompileOutcome(gaps=(), planned=True)

    def _bring_up(*_args: object) -> StackReadiness:
        return StackReadiness(up=True, serving=True, notes="")

    def _run_plan(*_args: object) -> ExerciseResult:
        return ExerciseResult(lines=(), passed=True)

    monkeypatch.setattr(exercise_book_flow, "compile_scenarios", _compile)
    monkeypatch.setattr(exercise_book_flow, "bring_up", _bring_up)
    monkeypatch.setattr(exercise_book_flow, "run_plan", _run_plan)


def _drive(workspace: Workspace, runner: ScriptedRunner, tmp_path: Path) -> None:
    writer = ArtifactWriter("okf-book", tmp_path / "runs", run_id="t0")
    env = RunEnv(
        writer=writer,
        workflow_dir=Path(okf_book.__file__).parent,
        session_id_path=writer.run_dir / ".session_id",
        config=RunConfig(),
        nodes=workflow.nodes,
        agent_runner=runner,
    )
    surface = Surface(service=SERVICE, kind=SurfaceKind.HTTP, entry=MEMBER_FOLDER, repo=MEMBER)
    finished = cast("object", drive(OkfBook(repo_dir=str(workspace.member), surfaces=(surface,)), env))
    assert finished is not None


@pytest.fixture
def written(workspace: Workspace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[dict[str, str], str, str]:
    _stub_exercise(monkeypatch)
    assert status_of(workspace.member) == ""
    member_head = head_of(workspace.member)
    seen: dict[str, str] = {}
    runner = ScriptedRunner({"write-book": lambda args: _write_book(args, seen, workspace.docs)})

    _drive(workspace, runner, tmp_path)

    return seen, member_head, head_of(workspace.member)


def test_the_writer_is_given_the_member_s_files_and_names_the_folder_by_its_member(written: tuple[dict[str, str], str, str]) -> None:
    seen, _, _ = written

    assert seen["handlers.py"] == MEMBER_SOURCE
    assert seen["source_folder"] == f"repo://{MEMBER}/{MEMBER_FOLDER}"


def test_the_book_is_committed_to_the_docs_home(workspace: Workspace, written: tuple[dict[str, str], str, str]) -> None:
    del written
    files = git(workspace.docs, "log", "--name-only", "--format=").split()

    assert {f"{BOOK}/{name}" for name in PAGES} <= set(files)


def test_the_committed_book_passes_the_citation_stale_and_coverage_checks(workspace: Workspace, written: tuple[dict[str, str], str, str]) -> None:
    del written
    source = SourceRepo(name=MEMBER, path=workspace.member)

    with index.session(workspace.docs):
        book = load(workspace.docs)
        uncited = uncited_by_folder(source, MEMBER_FOLDER, book, SERVICE)
        findings = [finding.code for finding in doctor.run(book).findings if finding.code in {"unreachable-citation", "dangling-code-ref", "stale-citation"}]

    assert not cites_changed_file(workspace.docs, SERVICE)
    assert stale_files(workspace.docs, SERVICE) == ()
    assert uncited == {}
    assert findings == []
    assert effective_checkouts(None)[MEMBER] == workspace.member


def test_the_member_repo_is_left_untouched(workspace: Workspace, written: tuple[dict[str, str], str, str]) -> None:
    _, before, after = written

    assert status_of(workspace.member) == ""
    assert after == before
