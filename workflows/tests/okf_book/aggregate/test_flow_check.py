"""Every writing turn that runs tools runs the page check it is charged by, and starts with the whole of a turn's check output."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from okf_book.support import BRIEFS, Reply, ScriptedRunner, WorkListView, WriteOnly, always, drafted, judged, listing_runner, promised_contracts

from workhorse_workflows.okf_book.aggregate.nodes.job_check import charge, check_command, spent_tokens
from workhorse_workflows.okf_book.main.nodes.surface import Surface, SurfaceKind
from workhorse_workflows.okf_book.shared.attempts import MAX_ATTEMPTS
from workhorse_workflows.okf_book.shared.budget import CHECK_OUTPUT_BUDGET_TOKENS
from workhorse_workflows.okf_book.shared.entries import FEATURES_DIR

App = Callable[[str], Path]
RunBook = Callable[[WriteOnly, ScriptedRunner], WorkListView]

COMMANDS = ("init", "add", "import", "report", "export")
TALLY = Surface(service="tally", kind=SurfaceKind.CLI, entry="tally/__main__.py")
FIXTURE = f"{FEATURES_DIR}/tally/fixtures/expenses-csv.md"
PASS = judged()


def _append(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    _ = path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


def _writer(repo: Path) -> Reply:
    def _reply(args: dict[str, object]) -> dict[str, object]:
        page = str(args["page"])
        text = (repo / page).read_text(encoding="utf-8") + "\nTally keeps a ledger.\n"
        return drafted("wrote", (page, text))

    return _reply


def _run(
    repo: Path, run_book: RunBook, operations: Reply = always({"summary": "none"}), verify: Reply = PASS,
) -> tuple[WriteOnly, ScriptedRunner]:
    runner = listing_runner(
        *COMMANDS,
        document_files=promised_contracts,
        write_page=_writer(repo),
        write_operations=operations,
        write_flows=always({"summary": "none"}),
        verify_page=verify,
    )
    flow = WriteOnly(repo_dir=str(repo), surfaces=(TALLY,))
    _ = run_book(flow, runner)
    return flow, runner


def test_every_tool_using_writing_turn_is_handed_the_check_it_is_charged_by(app: App, run_book: RunBook) -> None:
    repo = app("tally-cli")
    flow, runner = _run(repo, run_book)

    writes = [*runner.args_of("write-operations"), *runner.args_of("write-flows")]
    assert writes
    assert {args["check"] for args in writes} == {check_command(flow.run_dir)}
    assert all("check" not in args for args in runner.args_of("write-page"))


def test_every_writing_turn_is_handed_the_format_and_the_checks_it_is_compiled_against(app: App, run_book: RunBook) -> None:
    repo = app("tally-cli")
    _, runner = _run(repo, run_book)

    writes = [*runner.args_of("write-page"), *runner.args_of("write-operations"), *runner.args_of("write-flows")]
    assert runner.args_of("write-operations")
    assert runner.args_of("write-flows")
    assert all("### flow" in str(args["rules"]) and "exit_status" in str(args["checks"]) for args in writes)


def test_every_writing_turn_starts_with_the_whole_check_budget(app: App, run_book: RunBook) -> None:
    repo = app("tally-cli")
    spent: list[int] = []

    def write(args: dict[str, object]) -> dict[str, object]:
        path = Path(str(args["check"]).split()[-1])
        _append(repo, FIXTURE, "\nThe scenario directory holds it.\n")
        spent.append(spent_tokens(path))
        charge(path, CHECK_OUTPUT_BUDGET_TOKENS)
        return {"summary": "wrote"}

    def reject(args: dict[str, object]) -> dict[str, object]:
        if FIXTURE in [page["page"] for page in BRIEFS.validate_python(args["pages"])]:
            return judged("The page says nothing about the fixture's rows.")(args)
        return PASS(args)

    _ = _run(repo, run_book, operations=write, verify=reject)

    assert len(spent) == MAX_ATTEMPTS
    assert set(spent) == {0}
