"""Directly author one explicit epic without selecting or entering downstream stages."""
from __future__ import annotations

from typing import Any, ClassVar

from workhorse.pyflow import Continue, Done, Workflow
from workhorse_workflows.author.epic_author.nodes import prepare_epic_target, validate_authored_epic
from workhorse_workflows.author.epic_author.schemas import EpicAuthorContext, EpicAuthorDone
from workhorse_workflows.author.pm import MAX_ANSWERS, GapAnswer
from workhorse_workflows.author.shared.nodes import load_config
from workhorse_workflows.author.shared.schemas import WriteEpicResult
from workhorse_workflows.kit.telemetry import counter_labels

MAX_REWORKS = 3


class EpicAuthor(Workflow):
    """Run the current epic-prose and seed pass for one caller-selected epic."""

    epic: str = ""
    note: str = ""

    BUDGET_LABELS: ClassVar[tuple[str, ...]] = ("reworks", "answers")

    def setup(self) -> EpicAuthorContext:
        """Resolve config and the explicit target only; never create a branch."""
        cfg = self.call(load_config, mode="epic")
        target = self.call(prepare_epic_target, self.epic)
        return EpicAuthorContext(**cfg.model_dump(), **target.model_dump())

    def labels(self) -> dict[str, str]:
        return {"work_id": self.epic, "epic": self.epic, "progress": "authoring one epic"}

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        return self.labels() | counter_labels(params, "epic_author", self.BUDGET_LABELS)

    def _blocked(self, notes: str, reworks: int, answers: int) -> Done:
        self.logger.warning("the epic '%s' stays blocked: %s", self.ctx.epic, notes)
        return Done(
            EpicAuthorDone(
                status="blocked",
                epic=self.ctx.epic,
                epic_dir=self.ctx.epic_dir,
                epic_path=self.ctx.epic_path,
                notes=notes,
                reworks=reworks,
                answers=answers,
            )
        )

    def start(self) -> Continue:
        return Continue(None, self.author_epic)

    def author_epic(
        self, reworks: int = 0, answers: int = 0, note: str = ""
    ) -> Continue | Done:
        self.logger.info("authoring epic %s", self.ctx.epic, extra={"activity": True})
        result = self.agent(
            "epic_author/prompts/write-epic.md",
            returns=WriteEpicResult,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "epic": self.ctx.epic,
                "epic_dir": self.ctx.epic_dir,
                "milestone": self.ctx.milestone_path,
                "services_dir": self.ctx.services_dir,
                "note": "\n\n".join(part for part in (self.note, note) if part),
                "ledger": self.ctx.pm_ledger,
            },
        )
        if result.status == "blocked":
            if answers >= MAX_ANSWERS:
                return self._blocked(result.notes, reworks, answers)
            return Continue(
                result, self.ask_pm, question=result.notes, reworks=reworks, answers=answers
            )
        evidence = self.call(validate_authored_epic, self.ctx.epic)
        if not evidence.ok:
            if reworks >= MAX_REWORKS:
                return self._blocked(evidence.errors, reworks, answers)
            return Continue(
                evidence,
                self.author_epic,
                reworks=reworks + 1,
                answers=answers,
                note=f"The previous pass failed validation. Fix every error:\n{evidence.errors}",
            )
        return Done(
            EpicAuthorDone(
                epic=evidence.epic,
                epic_dir=evidence.epic_dir,
                epic_path=evidence.epic_path,
                seed_count=evidence.seed_count,
                reworks=reworks,
                answers=answers,
            )
        )

    def ask_pm(self, question: str, reworks: int = 0, answers: int = 0) -> Continue:
        answer = self.handoff(GapAnswer, question=question, asker="epic-author")
        return Continue(
            answer, self.author_epic, reworks=reworks, answers=answers + 1, note=answer.note
        )


__all__ = ["EpicAuthor", "MAX_REWORKS"]
