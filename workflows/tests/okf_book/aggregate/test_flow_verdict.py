"""The writer hears about each claim the judge finds on no page, and each node that needs a fix and was not cleared before."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from okf_book.support import (
    BRIEFS,
    Reply,
    ScriptedRunner,
    WorkListView,
    WriteOnly,
    always,
    commits,
    drafted,
    git,
    judged,
    listing_runner,
    promised_contracts,
)
from pydantic import TypeAdapter

from workhorse_workflows.okf_book.aggregate.verdict import GRAMMAR_GAPS_NAME, GrammarGap
from workhorse_workflows.okf_book.shared.attempts import MAX_ATTEMPTS
from workhorse_workflows.okf_book.main.nodes.surface import Surface, SurfaceKind
from workhorse_workflows.okf_book.shared.entries import FEATURES_DIR

App = Callable[[str], Path]
RunBook = Callable[[WriteOnly, ScriptedRunner], WorkListView]

COMMANDS = ("init", "add", "import", "report", "export")
TALLY = Surface(service="tally", kind=SurfaceKind.CLI, entry="tally/__main__.py")
CONCEPT = f"{FEATURES_DIR}/tally/concepts/ledger-file.md"
FIXTURE = f"{FEATURES_DIR}/tally/fixtures/expenses-csv.md"
PASS = judged()
NAMES = TypeAdapter(list[str])
NUMBERS = TypeAdapter(list[dict[str, object]])


def _writer(repo: Path) -> Reply:
    def _reply(args: dict[str, object]) -> dict[str, object]:
        page = str(args["page"])
        text = (repo / page).read_text(encoding="utf-8") + "\nTally keeps a ledger.\n"
        return drafted("wrote", (page, text))

    return _reply


def _book_runner(repo: Path, verify: Reply, write: Reply) -> ScriptedRunner:
    return listing_runner(
        *COMMANDS,
        document_files=promised_contracts,
        write_page=write,
        write_operations=always({"summary": "none"}),
        write_flows=always({"summary": "none"}),
        verify_page=verify,
    )


def _last_problems(repo: Path, run_book: RunBook, verify: Reply) -> list[str]:
    runner = _book_runner(repo, verify, _writer(repo))
    _ = run_book(WriteOnly(repo_dir=str(repo), surfaces=(TALLY,)), runner)
    tries = [args for args in runner.args_of("write-page") if args["page"] == CONCEPT]
    return NAMES.validate_python(tries[-1]["problems"])


def _judges_concept(args: dict[str, object]) -> bool:
    return CONCEPT in [page["page"] for page in BRIEFS.validate_python(args["pages"])]


def test_a_claim_the_verifier_leaves_unaccounted_is_charged_as_stated_on_no_page(app: App, run_book: RunBook) -> None:
    repo = app("tally-cli")
    _ = (repo / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    _ = git(repo, "add", "Dockerfile")
    _ = git(repo, "commit", "-qm", "build the image")

    def skip_claims(args: dict[str, object]) -> dict[str, object]:
        return {"claims": [], "problems": []} if args["kind"] == "operations" else PASS(args)

    runner = _book_runner(repo, skip_claims, _writer(repo))
    _ = run_book(WriteOnly(repo_dir=str(repo), surfaces=(TALLY,)), runner)
    problems = NAMES.validate_python(runner.args_of("write-operations")[-1]["problems"])

    unstated = [problem for problem in problems if "is stated on no page" in problem]
    assert unstated
    assert all("It works." in problem for problem in unstated)


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


def test_the_judge_is_told_the_checks_and_a_check_it_expected_reaches_the_writer_or_the_gap_record(
    app: App, run_book: RunBook,
) -> None:
    repo = app("tally-cli")
    node = f"{CONCEPT}#ledger-file"
    expected = ['contents(subject="tally.json", text="entries")', 'sorted(subject="entries")']

    def expect_checks(args: dict[str, object]) -> dict[str, object]:
        verdict = PASS(args)
        if not _judges_concept(args) or not expected:
            return verdict
        wanted = expected.pop(0)
        claims = [{"claim": 1, "node": node, "problem": "it reads stdout.", "expected": wanted},
                  *NUMBERS.validate_python(verdict["claims"])[1:]]
        return {**verdict, "claims": claims}

    runner = _book_runner(repo, expect_checks, _writer(repo))
    flow = WriteOnly(repo_dir=str(repo), surfaces=(TALLY,))
    _ = run_book(flow, runner)

    assert all("contents(" in str(args["checks"]) for args in runner.args_of("verify-page"))
    tries = [NAMES.validate_python(args["problems"]) for args in runner.args_of("write-page") if args["page"] == CONCEPT]
    assert tries[1] == [f'{node}: it reads stdout. The check that reads it: `verify: contents(subject="tally.json", text="entries")`.']
    assert tries[2] == [f"{node}: it reads stdout."]
    lines = (flow.run_dir / GRAMMAR_GAPS_NAME).read_text(encoding="utf-8").splitlines()
    assert [(gap.node, gap.expected) for gap in map(GrammarGap.model_validate_json, lines)] == [(node, 'sorted(subject="entries")')]


def test_a_node_an_earlier_round_cleared_is_not_faulted_while_its_text_is_unchanged(app: App, run_book: RunBook) -> None:
    repo = app("tally-cli")
    faulted: list[str] = []

    def write(args: dict[str, object]) -> dict[str, object]:
        page = str(args["page"])
        text = (repo / page).read_text(encoding="utf-8")
        added = "\nMore.\n" if "## Kept" in text else "\n## Kept\n\nIt stays.\n\n## Tail\n\nTally keeps a ledger.\n"
        return drafted("wrote", (page, text + added))

    def fault(args: dict[str, object]) -> dict[str, object]:
        if not _judges_concept(args):
            return PASS(args)
        faulted.append(f"{CONCEPT}#tail" if not faulted else f"{CONCEPT}#kept")
        return judged("it contradicts the other section.", node=faulted[-1])(args)

    runner = _book_runner(repo, fault, write)
    _ = run_book(WriteOnly(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert faulted == [f"{CONCEPT}#tail", f"{CONCEPT}#kept"]
    assert "docs(tally): write ledger-file" in commits(repo)
    [second] = [args for args in runner.args_of("verify-page") if _judges_concept(args)][1:]
    assert f"{CONCEPT}#kept" in NAMES.validate_python(second["cleared"])



def test_a_judge_that_faults_a_page_it_did_not_read_is_asked_again_and_no_writer_hears_of_it(
    app: App, run_book: RunBook,
) -> None:
    repo = app("tally-cli")

    def fault_unread(args: dict[str, object]) -> dict[str, object]:
        if "refused" in args or FIXTURE in [page["page"] for page in BRIEFS.validate_python(args["pages"])]:
            return PASS(args)
        return judged("it contradicts the ledger page.", node=FIXTURE)(args)

    runner = _book_runner(repo, fault_unread, _writer(repo))
    _ = run_book(WriteOnly(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    assert [reason for node, reason in runner.refused if node == "verify-page" and FIXTURE in reason]
    writes = [*runner.args_of("write-page"), *runner.args_of("write-operations"), *runner.args_of("write-flows")]
    assert not [problem for args in writes for problem in NAMES.validate_python(args["problems"]) if FIXTURE in problem]


def test_the_operations_and_flows_judges_read_the_service_and_charge_no_claim_a_page_owes(app: App, run_book: RunBook) -> None:
    repo = app("tally-cli")
    runner = _book_runner(repo, PASS, _writer(repo))
    _ = run_book(WriteOnly(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    for kind in ("operations", "flows"):
        args = next(a for a in runner.args_of("verify-page") if a["kind"] == kind)
        assert args["contracts"] == []
        assert "tally/cli.py" in [contract["file"] for contract in NUMBERS.validate_python(args["context"])]


def test_the_concept_judge_charges_no_claim_and_a_command_judge_still_does(app: App, run_book: RunBook) -> None:
    repo = app("tally-cli")
    runner = _book_runner(repo, PASS, _writer(repo))
    _ = run_book(WriteOnly(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    judged_pages = [(NUMBERS.validate_python(a["pages"]), a) for a in runner.args_of("verify-page") if a["kind"] == "page"]
    [concept] = [args for pages, args in judged_pages if CONCEPT in [page["page"] for page in pages]]
    assert concept["contracts"] == []
    assert concept["context"]
    assert all(args["contracts"] for pages, args in judged_pages if CONCEPT not in [page["page"] for page in pages])


def test_an_operations_job_is_charged_for_each_of_its_pages_it_leaves_unlinked(app: App, run_book: RunBook) -> None:
    repo = app("tally-cli")
    runner = _book_runner(repo, PASS, _writer(repo))
    _ = run_book(WriteOnly(repo_dir=str(repo), surfaces=(TALLY,)), runner)

    tries = runner.args_of("write-operations")
    assert len(tries) == MAX_ATTEMPTS
    problems = " ".join(NAMES.validate_python(tries[-1]["problems"]))
    for page in ("ops/run-tally.md", "ops/tally-checkout.md"):
        assert f"{page} is linked from no page the entries page reaches, so it is deleted after this job." in problems
