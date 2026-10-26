"""A run in a two-repo workspace reads the product member's source and commits the book to the docs home, leaving the member alone."""
from __future__ import annotations

import socket
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
from okf_book.support import (
    BOOK,
    BRING_UP_MARKER,
    MEMBER,
    MEMBER_FOLDER,
    MEMBER_SOURCE,
    SERVER,
    SERVICE,
    ScriptedRunner,
    Workspace,
    git,
    head_of,
    ledger_pages,
    status_of,
)
from ostler import doctor, index
from ostler.model import load
from ostler.provenance import effective_checkouts
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv

from workhorse_workflows import okf_book
from workhorse_workflows.okf_book.main import exercise_book_flow
from workhorse_workflows.okf_book.shared.book_run import CompileOutcome, ExerciseResult, StackReadiness
from workhorse_workflows.okf_book.main.nodes.stale_citations import stale_files
from workhorse_workflows.okf_book.main.nodes.surface import Surface, SurfaceKind
from workhorse_workflows.okf_book.shared.citations import cites_changed_file
from workhorse_workflows.okf_book.shared.scenarios import read_run
from workhorse_workflows.okf_book.shared.source_coverage import uncited_by_folder
from workhorse_workflows.okf_book.shared.source_repo import SourceRepo
from workhorse_workflows.okf_book.workflow import OkfBook, workflow

pytestmark = pytest.mark.filterwarnings(
    "ignore:subprocess .* is still running:ResourceWarning",
    "ignore:Exception ignored in.*Popen:pytest.PytestUnraisableExceptionWarning",
)


def _write_book(args: dict[str, object], seen: dict[str, str], docs: Path, pages: dict[str, str]) -> dict[str, object]:
    view = Path(str(args["source_dir"]))
    seen.update({path.relative_to(view).as_posix(): path.read_text(encoding="utf-8") for path in view.rglob("*") if path.is_file()})
    seen["source_folder"] = str(args["source_folder"])
    for name, text in pages.items():
        page = docs / BOOK / name
        page.parent.mkdir(parents=True, exist_ok=True)
        _ = page.write_text(text, encoding="utf-8")
    return {}


def _drive(workspace: Workspace, runner: ScriptedRunner, tmp_path: Path) -> Path:
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
    return writer.run_dir


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return cast("int", probe.getsockname()[1])


@pytest.fixture
def served(workspace: Workspace) -> Workspace:
    _ = (workspace.member / "serve.py").write_text(SERVER, encoding="utf-8")
    _ = (workspace.member / ".gitignore").write_text(f"{BRING_UP_MARKER}\n", encoding="utf-8")
    _ = git(workspace.member, "add", "serve.py", ".gitignore")
    _ = git(workspace.member, "commit", "-m", "serve the ledger")
    return workspace


@dataclass(frozen=True, slots=True)
class Ran:
    seen: dict[str, str]
    member_head_before: str
    member_head_after: str
    run_dir: Path
    exercised_from: list[SourceRepo | None]
    writer_add_dirs: list[list[str]]
    writer_prompt_dirs: list[str]


@pytest.fixture
def written(served: Workspace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Ran:
    assert status_of(served.member) == ""
    member_head = head_of(served.member)
    seen: dict[str, str] = {}
    pages = ledger_pages(_free_port())
    runner = ScriptedRunner({"write-book": lambda args: _write_book(args, seen, served.docs, pages)})

    exercised_from: list[SourceRepo | None] = []
    compile_scenarios, run_plan = exercise_book_flow.compile_scenarios, exercise_book_flow.run_plan

    def _compile(root: Path, service: str, spec: Path, targets: Sequence[str] = (), source: SourceRepo | None = None) -> CompileOutcome:
        exercised_from.append(source)
        return compile_scenarios(root, service, spec, targets, source)

    def _run(root: Path, spec: Path, gaps: tuple[str, ...], stack: StackReadiness, only: Sequence[str] = ()) -> ExerciseResult:
        exercised_from.append(stack.source)
        return run_plan(root, spec, gaps, stack, only)

    monkeypatch.setattr(exercise_book_flow, "compile_scenarios", _compile)
    monkeypatch.setattr(exercise_book_flow, "run_plan", _run)

    run_dir = _drive(served, runner, tmp_path)

    writer_add_dirs = [[str(folder) for folder in node.add_dirs] for node in runner.nodes if node.id == "write-book"]
    writer_prompt_dirs = [str(args.get("source_dir")) for args in runner.args_of("write-book")]
    return Ran(seen, member_head, head_of(served.member), run_dir, exercised_from, writer_add_dirs, writer_prompt_dirs)


def test_the_writer_is_given_the_member_s_files_and_names_the_folder_by_its_member(written: Ran) -> None:
    assert written.seen["handlers.py"] == MEMBER_SOURCE
    assert written.seen["source_folder"] == f"repo://{MEMBER}/{MEMBER_FOLDER}"


def test_the_writer_reads_the_member_folder_in_place_as_an_added_directory(served: Workspace, written: Ran) -> None:
    folder = (served.member / MEMBER_FOLDER).as_posix()

    assert [dirs[0] for dirs in written.writer_add_dirs] == [folder]
    assert written.writer_prompt_dirs == [folder]


def test_no_copy_of_the_member_source_is_made_for_the_writer(served: Workspace, written: Ran) -> None:
    del written

    assert not (served.docs / ".okf-book-source" / MEMBER).exists()
    assert not (served.member / ".okf-book-source" / MEMBER).exists()


def test_the_book_is_committed_to_the_docs_home(workspace: Workspace, written: Ran) -> None:
    del written
    files = git(workspace.docs, "log", "--name-only", "--format=").split()

    assert {f"{BOOK}/{name}" for name in ledger_pages(0)} <= set(files)


def test_the_committed_book_passes_the_citation_stale_and_coverage_checks(workspace: Workspace, written: Ran) -> None:
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


def test_the_member_repo_is_left_untouched(workspace: Workspace, written: Ran) -> None:
    assert status_of(workspace.member) == ""
    assert written.member_head_after == written.member_head_before


def test_the_scenario_compiled_for_the_members_cited_claim_passes(written: Ran) -> None:
    summary = read_run(written.run_dir)

    assert summary is not None
    assert summary.status == "passed"
    assert summary.scenarios
    assert {outcome.status for outcome in summary.scenarios.values()} == {"passed"}
    assert all(outcome.assertions for outcome in summary.scenarios.values())


def test_the_compile_and_the_run_were_given_the_member_the_surface_names(workspace: Workspace, written: Ran) -> None:
    assert written.exercised_from == [SourceRepo(name=MEMBER, path=workspace.member)] * 2


def test_the_bring_up_ran_its_steps_in_the_member_checkout(workspace: Workspace, written: Ran) -> None:
    del written

    assert (workspace.member / BRING_UP_MARKER).read_text(encoding="utf-8").strip() == str(workspace.member)
