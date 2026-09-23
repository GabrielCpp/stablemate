"""Every writing turn runs the page check it is charged by, and starts with the whole of a turn's check output."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from okf_book.support import BRIEFS, Reply, ScriptedRunner, WorkListView, WriteOnly, always, listing_runner, promised_contracts

from workhorse_workflows.okf_book.aggregate.nodes.job_check import JobCheck, check_command
from workhorse_workflows.okf_book.main.nodes.surface import Surface, SurfaceKind
from workhorse_workflows.okf_book.shared.attempts import MAX_ATTEMPTS
from workhorse_workflows.okf_book.shared.budget import CHECK_OUTPUT_BUDGET_TOKENS
from workhorse_workflows.okf_book.shared.entries import FEATURES_DIR

App = Callable[[str], Path]
RunBook = Callable[[WriteOnly, ScriptedRunner], WorkListView]

COMMANDS = ("init", "add", "import", "report", "export")
TALLY = Surface(service="tally", kind=SurfaceKind.CLI, entry="tally/__main__.py")
CONCEPT = f"{FEATURES_DIR}/tally/concepts/ledger-file.md"
PASS = always({"passed": True, "problems": []})


def _append(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    _ = path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


def _writer(repo: Path) -> Reply:
    def _reply(args: dict[str, object]) -> dict[str, object]:
        _append(repo, str(args["page"]), "\nTally keeps a ledger.\n")
        return {"summary": "wrote"}

    return _reply


def _run(repo: Path, run_book: RunBook, write: Reply, verify: Reply = PASS) -> tuple[WriteOnly, ScriptedRunner]:
    runner = listing_runner(
        *COMMANDS,
        document_files=promised_contracts,
        write_page=write,
        write_operations=always({"summary": "none"}),
        write_flows=always({"summary": "none"}),
        verify_page=verify,
    )
    flow = WriteOnly(repo_dir=str(repo), surfaces=(TALLY,))
    _ = run_book(flow, runner)
    return flow, runner


def test_every_writing_turn_is_handed_the_check_it_is_charged_by(app: App, run_book: RunBook) -> None:
    repo = app("tally-cli")
    flow, runner = _run(repo, run_book, write=_writer(repo))

    writes = [*runner.args_of("write-page"), *runner.args_of("write-operations"), *runner.args_of("write-flows")]
    assert writes
    assert {args["check"] for args in writes} == {check_command(flow.run_dir)}


def test_every_writing_turn_starts_with_the_whole_check_budget(app: App, run_book: RunBook) -> None:
    repo = app("tally-cli")
    spent: list[int] = []

    def write(args: dict[str, object]) -> dict[str, object]:
        path = Path(str(args["check"]).split()[-1])
        _append(repo, str(args["page"]), "\nTally keeps a ledger.\n")
        check = JobCheck.model_validate_json(path.read_text(encoding="utf-8"))
        spent.append(check.spent_tokens)
        _ = path.write_text(check.model_copy(update={"spent_tokens": CHECK_OUTPUT_BUDGET_TOKENS}).model_dump_json(), encoding="utf-8")
        return {"summary": "wrote"}

    def reject(args: dict[str, object]) -> dict[str, object]:
        rejected = CONCEPT in [page["page"] for page in BRIEFS.validate_python(args["pages"])]
        return {"passed": not rejected, "problems": ["The page says nothing about the ledger's columns."] if rejected else []}

    _ = _run(repo, run_book, verify=reject, write=write)

    assert len(spent) > MAX_ATTEMPTS
    assert set(spent) == {0}
