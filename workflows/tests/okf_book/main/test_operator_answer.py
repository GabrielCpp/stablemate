"""The operator's answer to the blockers reaches every owner turn that follows it."""
from __future__ import annotations

from pathlib import Path

import pytest

from okf_book.main.tally import TALLY

from workhorse import gates, templates

from workhorse_workflows import okf_book
from workhorse_workflows.okf_book.main.flow import OPERATOR_NAME
from workhorse_workflows.okf_book.main.nodes.operator_answer import ANSWER_LIMIT_CHARS, answer_below, read_answer, write_answer
from workhorse_workflows.okf_book.main.nodes.owner_gate import Gates, gate_template_args
from workhorse_workflows.okf_book.main.nodes.writer_commands import check_command, exercise_command, ostler_command
from workhorse_workflows.okf_book.main.nodes.writer_request import WriterRequest
from workhorse_workflows.okf_book.main.write_book_flow import WRITE_PROMPT
from workhorse_workflows.okf_book.shared.blockers import Blocker, Phase, Side, record_blocker
from workhorse_workflows.okf_book.workflow import OkfBook

ANSWER = "The admin checks revoke the supplier's tokens. Give them their own user."


def test_the_answer_to_the_blockers_is_kept_for_the_owner(tmp_path: Path) -> None:
    book = OkfBook(repo_dir=str(tmp_path), parent_records_dir=str(tmp_path), surfaces=(TALLY,))
    _ = book.start()
    _ = record_blocker(tmp_path, Blocker(subject="tally", service="tally", phase=Phase.EXERCISE, side=Side.BOOK, reason="failed its run"))
    question = "The run stopped on 1 blockers."
    gate_path = tmp_path / OPERATOR_NAME
    _ = gate_path.write_text(gates.apply_answer(gates.format_operator_gate(question), ANSWER), encoding="utf-8")

    step = book.resume(gate_path=str(gate_path), question=question)

    assert read_answer(tmp_path) == ANSWER
    assert step.state == "settle_gate"


def test_a_gate_asking_something_newer_holds_no_answer_to_the_old_question() -> None:
    answered = gates.apply_answer(gates.format_operator_gate("First question."), "First answer.")
    reasked = gates.append_operator_gate(answered, "Second question.")

    assert answer_below(answered, "First question.") == "First answer."
    assert answer_below(reasked, "First question.") == ""


def test_an_empty_answer_clears_the_last(tmp_path: Path) -> None:
    write_answer(tmp_path, ANSWER)
    write_answer(tmp_path, "")

    assert read_answer(tmp_path) == ""


@pytest.mark.usefixtures("ostler_okf_skill")
def test_the_owner_prompt_carries_the_answer(tmp_path: Path) -> None:
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
    folder = Path(okf_book.__file__).parent
    unanswered = templates.render(WRITE_PROMPT, {**request.template_args(), **gate_template_args(tmp_path, tmp_path, "tally", Gates())}, folder)
    write_answer(tmp_path, ANSWER)

    answered = templates.render(WRITE_PROMPT, {**request.template_args(), **gate_template_args(tmp_path, tmp_path, "tally", Gates())}, folder)

    assert ANSWER in answered
    assert "What the operator answered" not in unanswered


def test_a_long_answer_is_capped() -> None:
    text = gates.apply_answer(gates.format_operator_gate("A question."), "x" * 20000)

    answer = answer_below(text, "A question.")

    assert ANSWER_LIMIT_CHARS - 10 < len(answer) <= ANSWER_LIMIT_CHARS
    assert answer == "x" * len(answer)
