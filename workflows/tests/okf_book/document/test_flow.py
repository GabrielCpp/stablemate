"""Every file on the work list gets a contract before any page is written, in turns that fit the budget."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from okf_book.support import DocumentOnly, WorkListView, ScriptedRunner, listing_runner
from pydantic import TypeAdapter

from workhorse_workflows.okf_book.document import nodes as document_nodes
from workhorse_workflows.okf_book.shared.blockers import Phase, read_blockers
from workhorse_workflows.okf_book.shared.budget import TURN_BUDGET_TOKENS
from workhorse_workflows.okf_book.shared.contracts import read_contract
from workhorse_workflows.okf_book.shared.attempts import MAX_ATTEMPTS
from workhorse_workflows.okf_book.shared.metrics import read_metrics
from workhorse_workflows.okf_book.main.nodes.surface import Surface, SurfaceKind

App = Callable[[str], Path]
RunBook = Callable[[DocumentOnly, ScriptedRunner], WorkListView]
NODE = "document-files"
COMMANDS = ("init", "add", "import", "report", "export")
TALLY = Surface(service="tally", kind=SurfaceKind.CLI, entry="tally/__main__.py")
BRIEFS = TypeAdapter(list[dict[str, object]])
ENTRIES = TypeAdapter(list[str])


def _files(args: dict[str, object]) -> list[str]:
    return [str(brief["file"]) for brief in BRIEFS.validate_python(args["files"])]


def _contracts(symbol_of: Callable[[str], str]) -> Callable[[dict[str, object]], dict[str, object]]:
    def _reply(args: dict[str, object]) -> dict[str, object]:
        return {"contracts": [
            {"file": f, "purpose": f"{f} runs part of tally.", "promises": [{"text": "It works.", "symbol": symbol_of(f)}]}
            for f in _files(args)
        ]}

    return _reply


def _run(app: App, run_book: RunBook, symbol_of: Callable[[str], str]) -> tuple[DocumentOnly, ScriptedRunner, WorkListView]:
    flow = DocumentOnly(repo_dir=str(app("tally-cli")), surfaces=(TALLY,))
    runner = listing_runner(*COMMANDS, document_files=_contracts(symbol_of))
    return flow, runner, run_book(flow, runner)


def test_every_file_gets_a_contract_in_turns_under_the_budget(app: App, run_book: RunBook) -> None:
    flow, runner, listed = _run(app, run_book, lambda _f: "")

    assert all(read_contract(flow.run_dir, file) for file in listed.files)
    assert sorted(f for args in runner.args_of(NODE) for f in _files(args)) == sorted(listed.files)
    turns = [m for m in read_metrics(flow.run_dir) if m.phase is Phase.DOCUMENT]
    assert len(turns) == runner.turns[NODE]
    assert all(0 < m.tokens <= TURN_BUDGET_TOKENS for m in turns)
    assert read_blockers(flow.run_dir) == ()


def test_a_contract_citing_an_undeclared_symbol_blocks_its_file_after_three_turns(app: App, run_book: RunBook) -> None:
    bad = "tally/report.py"
    flow, runner, listed = _run(app, run_book, lambda f: "no_such_symbol" if f == bad else "")

    tried = [args for args in runner.args_of(NODE) if bad in _files(args)]
    assert len(tried) == MAX_ATTEMPTS
    retried = [brief for brief in BRIEFS.validate_python(tried[-1]["files"]) if brief["file"] == bad]
    assert "no_such_symbol" in str(retried[0]["problems"])
    assert read_contract(flow.run_dir, bad) is None
    assert all(read_contract(flow.run_dir, f) for f in listed.files if f != bad)
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
    assert (blocker.subject, blocker.reason) == ("tally/cli.py", "The contract of tally/cli.py promises nothing, but the file runs code. State what a user sees because it runs, and leave `symbol` empty when the file declares none that carries it.")


def test_each_turn_names_the_entry_points_a_claim_is_seen_through(app: App, run_book: RunBook) -> None:
    _, runner, _ = _run(app, run_book, lambda _f: "")

    assert all(args["entry_points"] == [f"tally: {c.title()}" for c in COMMANDS] for args in runner.args_of(NODE))


def test_each_turn_says_what_each_check_reads_on_a_cli(app: App, run_book: RunBook) -> None:
    _, runner, _ = _run(app, run_book, lambda _f: "")

    checks = ENTRIES.validate_python(runner.args_of(NODE)[0]["checks"])
    assert any(line.startswith("`count(") and "the command's stdout" in line for line in checks)
    assert any(line.startswith("`absent(") and "before the first step on a flow's `start:`" in line for line in checks)
    assert any(line.startswith("`visible(") and line.endswith("reads nothing a command shows.") for line in checks)


def test_entry_points_past_their_budget_are_counted_not_listed(app: App, run_book: RunBook, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(document_nodes, "ENTRY_POINTS_BUDGET_TOKENS", 10)

    _, runner, _ = _run(app, run_book, lambda _f: "")

    for args in runner.args_of(NODE):
        kept = ENTRIES.validate_python(args["entry_points"])
        assert 0 < len(kept) < len(COMMANDS)
        assert len(kept) + int(str(args["entry_points_left_out"])) == len(COMMANDS)
