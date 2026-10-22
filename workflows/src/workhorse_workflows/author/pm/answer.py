"""A writer's product question, answered from the milestone or by the operator, and kept."""
from __future__ import annotations

from pathlib import Path

from workhorse.pyflow import Await, Done, Workflow, WorkflowFailed
from workhorse_workflows.author.pm.nodes import append_ledger
from workhorse_workflows.author.pm.schemas import Answer, GapAnswered
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.answer import answer_below
from workhorse_workflows.author.shared.nodes import load_config
from workhorse_workflows.author.shared.schemas import Config

MAX_ANSWERS = 2


def accepts(answer: Answer) -> None:
    """The check a reply must pass: an answer carries its text, an amendment carries its reason."""
    if answer.kind == "answered" and not answer.answer.strip():
        raise ValueError("an answered reply needs a non-empty `answer`")
    if answer.kind == "amendment" and not answer.reason.strip():
        raise ValueError("an amendment reply needs a non-empty `reason`")


def note_for(question: str, answer: str, by: str) -> str:
    """The note a writer is retried with."""
    return f"You asked: {question.strip()}\nThe {by} answers: {answer}"


class GapAnswer(Workflow):
    """Answer one writer's question as the PM, or ask the operator when only an amendment can."""

    question: str = ""
    asker: str = ""

    def setup(self) -> Config:
        return self.call(load_config, mode="pm")

    def labels(self) -> dict[str, str]:
        return {"work_id": self.asker, "progress": "answering a writer's question"}

    def _gate(self) -> Path:
        return Path(self.ctx.repo_root) / paths.author_context(self.ctx.repo_root)

    def start(self) -> Done | Await:
        if not self.question.strip():
            raise WorkflowFailed(
                "gap-answer needs a non-empty 'question'",
                failure_class="gap-answer-missing-question",
            )
        answer = self.agent(
            "pm/prompts/answer.md",
            returns=Answer,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "question": self.question,
                "asker": self.asker,
                "milestone_dir": self.ctx.milestone_dir,
                "ledger": self.ctx.pm_ledger,
                "services_dir": self.ctx.services_dir,
                "epics_dir": self.ctx.epics_dir,
            },
            accept=accepts,
        )
        if answer.kind == "answered":
            self.call(append_ledger, self.ctx.pm_ledger, self.asker, self.question, answer.answer, "pm")
            return Done(
                GapAnswered(
                    kind="answered",
                    answer=answer.answer,
                    by="pm",
                    note=note_for(self.question, answer.answer, "PM"),
                )
            )
        asked = (
            f"{self.asker} needs a product decision the milestone does not make.\n\n"
            f"Question: {self.question.strip()}\n\n"
            f"The PM cannot settle it because: {answer.reason.strip()}\n\n"
            "Answer below. Your answer is recorded in the PM ledger and binds every later turn."
        )
        return Await(self._gate(), asked, self.record_human, asked=asked)

    def record_human(self, asked: str) -> Done:
        gate = self._gate()
        text = gate.read_text(encoding="utf-8") if gate.is_file() else ""
        human = answer_below(text, asked)
        if human:
            self.call(append_ledger, self.ctx.pm_ledger, self.asker, self.question, human, "human")
        return Done(
            GapAnswered(
                kind="amendment",
                answer=human,
                by="human",
                note=note_for(self.question, human, "operator"),
            )
        )


__all__ = ["GapAnswer", "MAX_ANSWERS", "accepts", "note_for"]
