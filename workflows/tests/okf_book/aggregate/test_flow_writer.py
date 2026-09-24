"""The page writer runs no tool: it is shown what it needs, and only the pages its job may write land in the book."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from okf_book.support import BRIEFS, Reply, ScriptedRunner, WorkListView, WriteOnly, always, commits, drafted, judged, listing_runner, promised_contracts

from workhorse_workflows.okf_book.aggregate.flow import WRITER_PROFILE
from workhorse_workflows.okf_book.main.nodes.surface import Surface, SurfaceKind
from workhorse_workflows.okf_book.shared.entries import FEATURES_DIR

App = Callable[[str], Path]
RunBook = Callable[[WriteOnly, ScriptedRunner], WorkListView]

COMMANDS = ("init", "add", "import", "report", "export")
TALLY = Surface(service="tally", kind=SurfaceKind.CLI, entry="tally/__main__.py")
CONCEPT = f"{FEATURES_DIR}/tally/concepts/ledger-file.md"
FIXTURE = f"{FEATURES_DIR}/tally/fixtures/expenses-csv.md"


def _written(repo: Path, page: str) -> tuple[str, str]:
    return page, (repo / page).read_text(encoding="utf-8") + "\nTally keeps a ledger.\n"


def _run(repo: Path, run_book: RunBook, write: Reply) -> ScriptedRunner:
    runner = listing_runner(
        *COMMANDS,
        document_files=promised_contracts,
        write_page=write,
        write_operations=always({"summary": "none"}),
        write_flows=always({"summary": "none"}),
        verify_page=judged(),
    )
    _ = run_book(WriteOnly(repo_dir=str(repo), surfaces=(TALLY,)), runner)
    return runner


def test_the_page_writer_runs_no_tool_and_is_shown_its_page_the_format_and_the_checks(app: App, run_book: RunBook) -> None:
    repo = app("tally-cli")
    before = (repo / CONCEPT).read_text(encoding="utf-8")
    runner = _run(repo, run_book, lambda args: drafted("wrote", _written(repo, str(args["page"]))))

    writers = [node.agent for node in runner.nodes if node.id == "write-page"]
    assert writers
    assert all(agent == WRITER_PROFILE for agent in writers)
    [args] = [args for args in runner.args_of("write-page") if args["page"] == CONCEPT]
    assert BRIEFS.validate_python(args["bodies"]) == [{"page": CONCEPT, "body": before}]
    assert "### concept" in str(args["rules"])
    assert "unchanged(" in str(args["checks"])


def test_a_drafted_page_the_job_may_not_write_is_dropped(app: App, run_book: RunBook) -> None:
    repo = app("tally-cli")
    fixture_before = (repo / FIXTURE).read_text(encoding="utf-8")

    def write(args: dict[str, object]) -> dict[str, object]:
        stray = (FIXTURE, "---\ntype: fixture\n---\n# Overwritten\n")
        return drafted("wrote", _written(repo, str(args["page"])), stray)

    _ = _run(repo, run_book, write)

    assert "docs(tally): write ledger-file" in commits(repo)
    assert (repo / FIXTURE).read_text(encoding="utf-8") == fixture_before
