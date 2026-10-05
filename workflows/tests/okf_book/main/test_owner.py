"""The book's owner names a side for each group of failures it was shown, and only the groups it names the book's come back to it."""
from __future__ import annotations

from pathlib import Path

from okf_book.main.tally import TALLY
from ostler.qa.attribution import Cause, Signature

from workhorse_workflows.okf_book.main.nodes.check_lead import latest_check_findings, unheld
from workhorse_workflows.okf_book.main.nodes.lead_findings import GroupVerdict, OwnerReply, read_findings
from workhorse_workflows.okf_book.main.nodes.owner_gate import Gates, gate_template_args, record_owner_reply
from workhorse_workflows.okf_book.shared.blockers import Side, read_blockers
from workhorse_workflows.okf_book.shared.book_run import ExerciseResult
from workhorse_workflows.okf_book.shared.page_check import PageProblem
from workhorse_workflows.okf_book.shared.scenarios import RUN_NAME, FailedCheck, RunSummary, ScenarioOutcome
from workhorse_workflows.okf_book.workflow import OkfBook

PAGE = "docs/features/tally/tally.md"
MISREAD = Signature(Cause.BOOK, "", "422", "POST /entries/…", 1, "adds: expected [201], observed 422")
UNNAMED = PageProblem(PAGE, f"{PAGE}:4: prose-name: the control has no name", node=f"{PAGE}#add", code="prose-name")
UNLINKED = PageProblem(PAGE, f"{PAGE}:9: off-journey: no flow links it", node=f"{PAGE}#list", code="off-journey")


def _book(tmp_path: Path) -> OkfBook:
    book = OkfBook(repo_dir=str(tmp_path), parent_records_dir=str(tmp_path), surfaces=(TALLY,))
    _ = book.start()
    return book


def _run() -> ExerciseResult:
    misread = FailedCheck(label="adds", expected="[201]", actual="422", cause=Cause.BOOK, status="422", shape="POST /entries/…",
                          covers=(f"okf:{PAGE}#add:does:1",))
    summary = RunSummary(status="failed", scenarios={"tally-add": ScenarioOutcome(status="failed", failed_checks=(misread,))},
                         signatures=(MISREAD,))
    return ExerciseResult(lines=("scenario tally-add: failed",), summary=summary)


def _named(side: Side) -> GroupVerdict:
    return GroupVerdict(group=1, side=side, evidence="plan.json:12 sends the body the page does not state")


def test_a_run_group_the_owner_names_the_toolchain_s_is_a_blocker_there_and_never_reaches_the_owner(tmp_path: Path) -> None:
    book = _book(tmp_path)
    exercised = _run()
    _ = record_owner_reply(tmp_path, "tally", Gates(exercised=exercised), OwnerReply(run=(_named(Side.OSTLER),)))

    _ = book.settle_run(index=0, run_failures_repaired=False, exercised=exercised)

    assert [blocker.side for blocker in read_blockers(tmp_path)] == [Side.OSTLER]
    assert book.map_run_failures(index=0, exercised=exercised).state == "report"


def test_a_run_group_the_owner_names_the_book_s_goes_back_to_the_owner(tmp_path: Path) -> None:
    book = _book(tmp_path)
    exercised = _run()
    _ = record_owner_reply(tmp_path, "tally", Gates(exercised=exercised), OwnerReply(run=(_named(Side.BOOK),)))

    _ = book.settle_run(index=0, run_failures_repaired=False, exercised=exercised)

    assert book.map_run_failures(index=0, exercised=exercised).state == "copy_source"


def test_a_check_group_the_owner_names_another_side_s_is_held_back_from_the_book(tmp_path: Path) -> None:
    problems = (UNNAMED, UNLINKED)
    reply = OwnerReply(check=(GroupVerdict(group=1, side=Side.BOOK, evidence="no flow under flows/ links #list"),
                              GroupVerdict(group=2, side=Side.OSTLER, evidence="ostler reads a prose name the skill allows")))

    _ = record_owner_reply(tmp_path, "tally", Gates(problems=problems), reply)

    assert unheld(problems, latest_check_findings(read_findings(tmp_path), "tally")) == (UNLINKED,)


def test_a_reply_that_names_no_side_records_nothing(tmp_path: Path) -> None:
    assert record_owner_reply(tmp_path, "tally", Gates(exercised=_run(), problems=(UNNAMED,)), OwnerReply()) == ()
    assert read_findings(tmp_path) == ()


def test_the_owner_opens_on_the_groups_what_it_named_before_and_where_the_whole_run_is_kept(tmp_path: Path) -> None:
    exercised = _run()
    _ = record_owner_reply(tmp_path, "tally", Gates(exercised=exercised), OwnerReply(run=(_named(Side.APP),)))

    args = gate_template_args(tmp_path, tmp_path, "tally", Gates(exercised=exercised, problems=(UNNAMED,)))

    assert args["run_groups"] == [{"number": 1, "text": MISREAD.text(), "cause": "book", "count": 1, "sample": MISREAD.sample, "pages": [PAGE]}]
    assert args["check_groups"] == [{"number": 1, "code": "prose-name", "count": 1, "samples": [UNNAMED.text], "pages": [PAGE],
                                     "nodes": [UNNAMED.node], "nodes_left": 0}]
    [finding] = read_findings(tmp_path)
    assert finding.side is Side.APP
    assert args["earlier"] == [finding.model_dump(mode="json")]
    assert Path(str(args["run_summary"])).name == RUN_NAME
    assert Path(str(args["check_problems"])).read_text(encoding="utf-8") != ""
