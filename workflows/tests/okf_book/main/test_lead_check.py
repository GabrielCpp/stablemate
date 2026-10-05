"""A book whose page check refuses it goes to the lead of the check before any page repair: only the problems of rules it names the book's reach a repair, and the rest stop as blockers on the side it named."""
from __future__ import annotations

from pathlib import Path

import pytest
from okf_book.main.tally import TALLY
from okf_book.support import ScriptedRunner, always, git
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow import AgentTurnFailed
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv

from workhorse_workflows import okf_book
from workhorse_workflows.okf_book.main.lead_check_flow import LeadCheck
from workhorse_workflows.okf_book.main.nodes import check_pages
from workhorse_workflows.okf_book.main.nodes.check_lead import held, unheld, with_check_instructions
from workhorse_workflows.okf_book.main.nodes.lead_findings import LeadFinding, LedLap, read_findings, record_findings
from workhorse_workflows.okf_book.main.nodes.writer_commands import WriterCommandState
from workhorse_workflows.okf_book.shared.blockers import Side, read_blockers
from workhorse_workflows.okf_book.shared.page_check import PageProblem
from workhorse_workflows.okf_book.workflow import OkfBook, workflow

PAGE = "docs/features/tally/tally.md"
EDITOR = "docs/features/tally/gui/screens/editor.md"
CLICK = PageProblem(PAGE, f"okf:{PAGE}#add:does:1 does not compile: unresolved-precondition: no action for `click Add`",
                    node=f"{PAGE}#add", code="unresolved-precondition")
LOAD = PageProblem(EDITOR, f"okf:{EDITOR}#open:does:1 does not compile: unresolved-precondition: no compiled action for `the page loads`",
                   node=f"{EDITOR}#open", code="unresolved-precondition")
TYPED = PageProblem(EDITOR, f"okf:{EDITOR}#type:does:1 does not compile: unresolved-precondition: no compiled action for `typing`",
                    node=f"{EDITOR}#type", code="unresolved-precondition")
LINK = PageProblem(PAGE, f"{PAGE}:12: broken-link: ../nowhere.md does not exist", line=12, code="broken-link")
EVIDENCE = "ostler/qa/compile.py has no action for a load or a typed trigger"


def _lead(tmp_path: Path, runner: ScriptedRunner, *problems: PageProblem) -> LedLap:
    writer = ArtifactWriter("okf-book", tmp_path / "runs", run_id=f"t{runner.total}")
    env = RunEnv(writer=writer, workflow_dir=Path(okf_book.__file__).parent, session_id_path=writer.run_dir / ".session_id",
                 config=RunConfig(), nodes=workflow.nodes, agent_runner=runner)
    repo = tmp_path / "repo"
    if not repo.is_dir():
        repo.mkdir()
        _ = git(repo, "init")
    flow = LeadCheck(repo_dir=str(repo), parent_records_dir=str(tmp_path), service="tally", problems=problems)
    return LedLap.model_validate(drive(flow, env))


def _finding(side: Side, code: str = "unresolved-precondition", nodes: tuple[str, ...] = (), instruction: str = "", lap: int = 1) -> LeadFinding:
    return LeadFinding(service="tally", lap=lap, signature=code, count=1, side=side, evidence=EVIDENCE, instruction=instruction,
                       measured="check", nodes=nodes)


def _book(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *laps: tuple[LeadFinding, ...]) -> OkfBook:
    named = iter(laps)

    def _handoff(self: OkfBook, _flow: object, **_params: object) -> LedLap:
        findings = next(named, ())
        record_findings(self.records_dir, findings)
        return LedLap(findings=findings)

    monkeypatch.setattr(OkfBook, "handoff", _handoff)
    book = OkfBook(repo_dir=str(tmp_path), parent_records_dir=str(tmp_path), surfaces=(TALLY,))
    _ = book.start()
    return book


def test_the_lead_is_shown_every_rule_and_may_split_one_across_two_sides(tmp_path: Path) -> None:
    runner = ScriptedRunner({"lead-check": always({"findings": [
        {"group": 1, "side": "ostler", "evidence": EVIDENCE, "nodes": [f"{EDITOR}#open", f"{EDITOR}#type"]},
        {"group": 1, "side": "book", "evidence": "the source names the button New, not Add", "instruction": "click `New`"},
        {"group": 2, "side": "book", "evidence": "no such page", "instruction": "link the editor page"},
        {"group": 9, "side": "book", "evidence": "no such group"},
    ]})})

    led = _lead(tmp_path, runner, CLICK, LOAD, TYPED, LINK)
    [kept] = runner.args_of("lead-check")
    assert Path(str(kept["problems"])).read_text(encoding="utf-8").splitlines()[3] == f"broken-link\t{LINK.text}"
    _ = _lead(tmp_path, runner, CLICK)

    assert [(finding.signature, finding.side, finding.count, finding.pages, finding.instruction) for finding in led.findings] == [
        ("unresolved-precondition", Side.OSTLER, 2, (EDITOR,), ""),
        ("unresolved-precondition", Side.BOOK, 1, (PAGE,), "click `New`"),
        ("broken-link", Side.BOOK, 1, (PAGE,), "link the editor page"),
    ]
    first, second = runner.args_of("lead-check")
    assert first["groups"] == [
        {"number": 1, "code": "unresolved-precondition", "count": 3, "samples": [CLICK.text, LOAD.text, TYPED.text], "pages": [PAGE, EDITOR],
         "nodes": [f"{PAGE}#add", f"{EDITOR}#open", f"{EDITOR}#type"], "nodes_left": 0},
        {"number": 2, "code": "broken-link", "count": 1, "samples": [LINK.text], "pages": [PAGE], "nodes": [PAGE], "nodes_left": 0},
    ]
    assert second["earlier"] == [finding.model_dump(mode="json") for finding in led.findings]
    assert {finding.lap for finding in read_findings(tmp_path)} == {1, 2}


def test_a_lead_turn_that_ends_without_a_verdict_names_nothing(tmp_path: Path) -> None:
    def _fails(_args: dict[str, object]) -> dict[str, object]:
        raise AgentTurnFailed("the model returned nothing")

    led = _lead(tmp_path, ScriptedRunner({"lead-check": _fails}), CLICK)

    assert led == LedLap()
    assert read_findings(tmp_path) == ()


def test_a_split_rule_holds_only_the_nodes_named_another_side_s() -> None:
    findings = (_finding(Side.OSTLER, nodes=(f"{EDITOR}#open", f"{EDITOR}#type")), _finding(Side.BOOK, instruction="click `New`"))

    assert unheld((CLICK, LOAD, TYPED, LINK), findings) == (CLICK, LINK)
    assert [problem for problem, _finding_ in held((CLICK, LOAD, TYPED), findings)] == [LOAD, TYPED]
    assert with_check_instructions((CLICK, LINK), findings)[0] == PageProblem(
        PAGE, "the lead read the whole check, and says of unresolved-precondition: click `New`", code="lead"
    )


def test_a_rule_named_with_no_nodes_holds_a_problem_it_has_not_seen_yet() -> None:
    later = PageProblem(PAGE, f"okf:{PAGE}#drag:does:1 does not compile: unresolved-precondition: no action", node=f"{PAGE}#drag",
                        code="unresolved-precondition")

    assert unheld((later, LINK), (_finding(Side.OSTLER),)) == (LINK,)


def test_a_rule_the_lead_names_the_toolchain_s_is_a_blocker_and_never_reaches_a_repair(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book = _book(tmp_path, monkeypatch, (_finding(Side.OSTLER), _finding(Side.BOOK, code="broken-link", instruction="link the editor")))

    step = book.lead_check(index=0, problems=(CLICK, LOAD, LINK))

    blockers = read_blockers(tmp_path)
    assert [(blocker.side, blocker.pages) for blocker in blockers] == [(Side.BOOK, (PAGE,)), (Side.OSTLER, (PAGE, EDITOR))]
    assert blockers[1].reason.endswith(f"the lead read the whole check: {EVIDENCE}")
    assert step.state == "copy_source"


def test_a_check_the_lead_holds_whole_goes_to_the_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book = _book(tmp_path, monkeypatch, (_finding(Side.OSTLER),))

    step = book.lead_check(index=0, problems=(CLICK, LOAD))

    assert step.state == "run_book"


def test_a_lead_that_names_nothing_leaves_what_the_last_lead_of_the_check_named(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book = _book(tmp_path, monkeypatch, (_finding(Side.OSTLER),), ())

    _ = book.lead_check(index=0, problems=(CLICK, LINK))
    step = book.lead_check(index=0, problems=(CLICK, LOAD, LINK))

    assert [blocker.side for blocker in read_blockers(tmp_path)] == [Side.BOOK, Side.OSTLER]
    assert step.state == "copy_source"


def test_a_repaired_check_is_compared_on_the_problems_the_lead_left_the_book(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    held_whole = (_finding(Side.OSTLER),)
    book = _book(tmp_path, monkeypatch, held_whole, held_whole)
    second_link = PageProblem(PAGE, f"{PAGE}:20: broken-link: ../gone.md does not exist", line=20, code="broken-link")

    _ = book.lead_check(index=0, problems=(CLICK, LINK, second_link))
    step = book.lead_check(index=0, problems=(CLICK, LOAD, TYPED, LINK), repaired=True)

    assert step.state == "copy_source"


def test_the_writer_s_check_leaves_out_what_the_lead_held(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _problems(_root: Path, _service: str) -> tuple[PageProblem, ...]:
        return (CLICK, LOAD, LINK)

    monkeypatch.setattr(check_pages, "page_problems", _problems)
    record_findings(tmp_path, (_finding(Side.OSTLER, nodes=(f"{EDITOR}#open",)),))
    state = WriterCommandState(root=tmp_path, service="tally")

    assert check_pages.scoped_problems(state.model_copy(update={"records_dir": tmp_path})) == (CLICK.text, LINK.text)
    assert check_pages.scoped_problems(state) == (CLICK.text, LOAD.text, LINK.text)
