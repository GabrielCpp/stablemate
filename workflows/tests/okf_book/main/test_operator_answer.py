"""The operator's answer to the blockers reaches every repair turn that follows it."""
from __future__ import annotations

from pathlib import Path

from okf_book.main.tally import TALLY

from workhorse import gates, templates

from workhorse_workflows import okf_book
from workhorse_workflows.okf_book.main.flow import OPERATOR_NAME
from workhorse_workflows.okf_book.main.nodes.operator_answer import answer_below, read_answer, write_answer
from workhorse_workflows.okf_book.main.nodes.repair_batch_models import PageRepair, RepairBatch
from workhorse_workflows.okf_book.main.nodes.writer_commands import check_command, exercise_command, ostler_command
from workhorse_workflows.okf_book.main.nodes.writer_request import WriterRequest
from workhorse_workflows.okf_book.main.repair_book_flow import REPAIR_PROMPT
from workhorse_workflows.okf_book.shared.blockers import Blocker, Phase, Side, record_blocker
from workhorse_workflows.okf_book.workflow import OkfBook

ANSWER = "The admin checks revoke the supplier's tokens. Give them their own user."


def test_the_answer_to_the_blockers_is_kept_for_the_repair(tmp_path: Path) -> None:
    book = OkfBook(repo_dir=str(tmp_path), parent_records_dir=str(tmp_path), surfaces=(TALLY,))
    _ = book.start()
    _ = record_blocker(tmp_path, Blocker(subject="tally", service="tally", phase=Phase.EXERCISE, side=Side.BOOK, reason="failed its run"))
    question = "The run stopped on 1 blockers."
    gate = tmp_path / OPERATOR_NAME
    _ = gate.write_text(gates.apply_answer(gates.format_operator_gate(question), ANSWER), encoding="utf-8")

    _ = book.resume(gate=str(gate), question=question)

    assert read_answer(tmp_path) == ANSWER


def test_a_gate_asking_something_newer_holds_no_answer_to_the_old_question() -> None:
    answered = gates.apply_answer(gates.format_operator_gate("First question."), "First answer.")
    reasked = gates.append_operator_gate(answered, "Second question.")

    assert answer_below(answered, "First question.") == "First answer."
    assert answer_below(reasked, "First question.") == ""


def test_an_empty_answer_clears_the_last(tmp_path: Path) -> None:
    write_answer(tmp_path, ANSWER)
    write_answer(tmp_path, "")

    assert read_answer(tmp_path) == ""


def test_the_repair_prompt_carries_the_answer(tmp_path: Path) -> None:
    request = WriterRequest(
        surface=TALLY,
        repo_root=tmp_path,
        book_folder="docs",
        source_folder="src",
        source_view=tmp_path,
        ostler_command_line=ostler_command(tmp_path),
        check_command_line=check_command(tmp_path),
        exercise_command_line=exercise_command(tmp_path),
        qa_tools=(),
    )
    batch = RepairBatch(pages=(PageRepair(page="docs/features/tally/fixtures/signed-in.md", problems=("seed failed",)),), tokens=1)
    folder = Path(okf_book.__file__).parent

    answered = templates.render(REPAIR_PROMPT, request.repair_template_args(batch, failed_run=True, operator_answer=ANSWER), folder)
    unanswered = templates.render(REPAIR_PROMPT, request.repair_template_args(batch, failed_run=True), folder)

    assert f"    {ANSWER}" in answered
    assert "The operator read" not in unanswered
