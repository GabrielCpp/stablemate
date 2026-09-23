"""The writer hears about each claim the judge finds on no page, and each claim whose node needs a fix."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from okf_book.support import BRIEFS, Reply, ScriptedRunner, WorkListView, WriteOnly, always, judged, listing_runner, promised_contracts
from pydantic import TypeAdapter

from workhorse_workflows.okf_book.main.nodes.surface import Surface, SurfaceKind
from workhorse_workflows.okf_book.shared.entries import FEATURES_DIR

App = Callable[[str], Path]
RunBook = Callable[[WriteOnly, ScriptedRunner], WorkListView]

COMMANDS = ("init", "add", "import", "report", "export")
TALLY = Surface(service="tally", kind=SurfaceKind.CLI, entry="tally/__main__.py")
CONCEPT = f"{FEATURES_DIR}/tally/concepts/ledger-file.md"
PASS = judged()
NAMES = TypeAdapter(list[str])
NUMBERS = TypeAdapter(list[dict[str, object]])


def _writer(repo: Path) -> Reply:
    def _reply(args: dict[str, object]) -> dict[str, object]:
        path = repo / str(args["page"])
        _ = path.write_text(path.read_text(encoding="utf-8") + "\nTally keeps a ledger.\n", encoding="utf-8")
        return {"summary": "wrote"}

    return _reply


def _last_problems(repo: Path, run_book: RunBook, verify: Reply) -> list[str]:
    runner = listing_runner(
        *COMMANDS,
        document_files=promised_contracts,
        write_page=_writer(repo),
        write_operations=always({"summary": "none"}),
        write_flows=always({"summary": "none"}),
        verify_page=verify,
    )
    _ = run_book(WriteOnly(repo_dir=str(repo), surfaces=(TALLY,)), runner)
    tries = [args for args in runner.args_of("write-page") if args["page"] == CONCEPT]
    return NAMES.validate_python(tries[-1]["problems"])


def _judges_concept(args: dict[str, object]) -> bool:
    return CONCEPT in [page["page"] for page in BRIEFS.validate_python(args["pages"])]


def test_a_claim_the_verifier_leaves_unaccounted_is_charged_as_stated_on_no_page(app: App, run_book: RunBook) -> None:
    def skip_claims(args: dict[str, object]) -> dict[str, object]:
        return {"claims": [], "problems": []} if _judges_concept(args) else PASS(args)

    problems = _last_problems(app("tally-cli"), run_book, skip_claims)

    assert problems
    assert all("It works." in problem and "is stated on no page" in problem for problem in problems)


def test_a_claim_the_verifier_finds_badly_checked_hands_the_writer_its_node_and_fix(app: App, run_book: RunBook) -> None:
    fix = "its `verify:` also passes when the ledger is left untouched."
    node = f"{CONCEPT}#ledger-file"

    def flag_first(args: dict[str, object]) -> dict[str, object]:
        verdict = PASS(args)
        if not _judges_concept(args):
            return verdict
        claims = [{"claim": 1, "node": node, "problem": fix}, *NUMBERS.validate_python(verdict["claims"])[1:]]
        return {**verdict, "claims": claims}

    problems = _last_problems(app("tally-cli"), run_book, flag_first)

    assert problems == [f"{node}: {fix}"]
