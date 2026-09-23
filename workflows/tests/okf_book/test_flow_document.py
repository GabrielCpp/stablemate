"""Every file of the work set gets a contract before any page is written, in turns that fit the budget."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from okf_book.support import DocumentOnly, ScriptedRunner, listing_runner
from pydantic import TypeAdapter

from workhorse_workflows.okf_book.blockers import Phase, read_blockers
from workhorse_workflows.okf_book.budget import TURN_BUDGET_TOKENS
from workhorse_workflows.okf_book.contracts import read_contract
from workhorse_workflows.okf_book.attempts import MAX_ATTEMPTS
from workhorse_workflows.okf_book.metrics import read_metrics
from workhorse_workflows.okf_book.surface import Surface, SurfaceKind
from workhorse_workflows.okf_book.work_set import WorkSet

App = Callable[[str], Path]
RunBook = Callable[[DocumentOnly, ScriptedRunner], WorkSet]
NODE = "document-files"
COMMANDS = ("init", "add", "import", "report", "export")
TALLY = Surface(service="tally", kind=SurfaceKind.CLI, entry="tally/__main__.py")
BRIEFS = TypeAdapter(list[dict[str, object]])


def _files(args: dict[str, object]) -> list[str]:
    return [str(brief["file"]) for brief in BRIEFS.validate_python(args["files"])]


def _contracts(symbol_of: Callable[[str], str]) -> Callable[[dict[str, object]], dict[str, object]]:
    def _reply(args: dict[str, object]) -> dict[str, object]:
        return {"contracts": [
            {"file": f, "purpose": f"{f} runs part of tally.", "promises": [{"text": "It works.", "symbol": symbol_of(f)}]}
            for f in _files(args)
        ]}

    return _reply


def _run(app: App, run_book: RunBook, symbol_of: Callable[[str], str]) -> tuple[DocumentOnly, ScriptedRunner, WorkSet]:
    flow = DocumentOnly(repo_dir=str(app("tally-cli")), surfaces=(TALLY,))
    runner = listing_runner(*COMMANDS, document_files=_contracts(symbol_of))
    return flow, runner, run_book(flow, runner)


def test_every_file_gets_a_contract_in_turns_under_the_budget(app: App, run_book: RunBook) -> None:
    flow, runner, work_set = _run(app, run_book, lambda _f: "")

    assert all(read_contract(flow.run_dir, file) for file in work_set.files)
    assert sorted(f for args in runner.args_of(NODE) for f in _files(args)) == sorted(work_set.files)
    turns = [m for m in read_metrics(flow.run_dir) if m.phase is Phase.DOCUMENT]
    assert len(turns) == runner.turns[NODE]
    assert all(0 < m.tokens <= TURN_BUDGET_TOKENS for m in turns)
    assert read_blockers(flow.run_dir) == ()


def test_a_contract_citing_an_undeclared_symbol_blocks_its_file_after_three_turns(app: App, run_book: RunBook) -> None:
    bad = "tally/report.py"
    flow, runner, work_set = _run(app, run_book, lambda f: "no_such_symbol" if f == bad else "")

    tried = [args for args in runner.args_of(NODE) if bad in _files(args)]
    assert len(tried) == MAX_ATTEMPTS
    retried = [brief for brief in BRIEFS.validate_python(tried[-1]["files"]) if brief["file"] == bad]
    assert "no_such_symbol" in str(retried[0]["problems"])
    assert read_contract(flow.run_dir, bad) is None
    assert all(read_contract(flow.run_dir, f) for f in work_set.files if f != bad)
    [blocker] = read_blockers(flow.run_dir)
    assert (blocker.subject, blocker.phase) == (bad, Phase.DOCUMENT)
    assert "no_such_symbol" in blocker.reason


def test_a_file_that_declares_and_runs_nothing_needs_no_promise(app: App, run_book: RunBook) -> None:
    empty = "tally/__init__.py"
    manifest = "pyproject.toml"
    flow = DocumentOnly(repo_dir=str(app("tally-cli")), surfaces=(TALLY,))

    def _reply(args: dict[str, object]) -> dict[str, object]:
        return {"contracts": [
            {"file": f, "purpose": f"{f} runs part of tally.", "promises": [] if f in (empty, manifest, "tally/cli.py") else [{"text": "It works."}]}
            for f in _files(args)
        ]}

    _ = run_book(flow, listing_runner(*COMMANDS, document_files=_reply))

    for file in (empty, manifest):
        contract = read_contract(flow.run_dir, file)
        assert contract is not None
        assert contract.promises == ()
    [blocker] = read_blockers(flow.run_dir)
    assert (blocker.subject, blocker.reason) == ("tally/cli.py", "The contract of tally/cli.py promises nothing.")
