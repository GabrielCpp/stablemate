"""Directly author one explicit epic without selecting or entering downstream stages."""
from __future__ import annotations

from typing import Any

from workhorse.pyflow import Continue, Done, Workflow
from workhorse_workflows.author.draft.schemas import Draft, spent_labels
from workhorse_workflows.author.epic_author.nodes import prepare_epic_target, validate_authored_epic
from workhorse_workflows.author.epic_author.schemas import EpicAuthorContext, EpicAuthorDone
from workhorse_workflows.author.pm import MAX_ANSWERS, GapAnswer
from workhorse_workflows.author.shared.nodes import load_config
from workhorse_workflows.author.shared.schemas import WriteEpicResult

MAX_REWORKS = 3


class EpicAuthor(Workflow):
    """Run the current epic-prose and seed pass for one caller-selected epic."""

    epic: str = ""
    note: str = ""

    def setup(self) -> EpicAuthorContext:
        """Resolve config and the explicit target only; never create a branch."""
        cfg = self.call(load_config, mode="epic")
        target = self.call(prepare_epic_target, self.epic)
        return EpicAuthorContext(**cfg.model_dump(), **target.model_dump())

    def labels(self) -> dict[str, str]:
        return {"work_id": self.epic, "epic": self.epic, "progress": "authoring one epic"}

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        return self.labels() | spent_labels(params, "epic_author")

    def _blocked(self, notes: str, draft: Draft) -> Done:
        self.logger.warning("the epic '%s' stays blocked: %s", self.ctx.epic, notes)
        return Done(
            EpicAuthorDone(
                status="blocked",
                epic=self.ctx.epic,
                epic_dir=self.ctx.epic_dir,
                epic_path=self.ctx.epic_path,
                notes=notes,
                reworks=draft.reworks,
                answers=draft.answers,
            )
        ).because("out of budget")

    def start(self) -> Continue:
        return Continue(None, self.author_epic, draft=Draft()).because("nothing written yet")

    def author_epic(self, draft: Draft) -> Continue | Done:
        """Write the epic's prose and seeds, then validate what the turn wrote."""
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
                "note": "\n\n".join(part for part in (self.note, draft.note) if part),
                "ledger": self.ctx.pm_ledger,
            },
        )
        if result.status == "blocked":
            if draft.answers >= MAX_ANSWERS:
                return self._blocked(result.notes, draft)
            return Continue(result, self.ask_pm, question=result.notes, draft=draft).because(
                "the writer has a question"
            )
        evidence = self.call(validate_authored_epic, self.ctx.epic)
        if not evidence.ok:
            if draft.reworks >= MAX_REWORKS:
                return self._blocked(evidence.errors, draft)
            note = f"The previous pass failed validation. Fix every error:\n{evidence.errors}"
            return Continue(
                evidence, self.author_epic, draft=draft.model_copy(update={"reworks": draft.reworks + 1, "note": note})
            ).because("the epic failed validation")
        return Done(
            EpicAuthorDone(
                epic=evidence.epic,
                epic_dir=evidence.epic_dir,
                epic_path=evidence.epic_path,
                seed_count=evidence.seed_count,
                reworks=draft.reworks,
                answers=draft.answers,
            )
        ).because("the epic validates")

    def ask_pm(self, question: str, draft: Draft) -> Continue:
        """Have the PM answer the writer's question, then write the epic again."""
        answer = self.handoff(GapAnswer, question=question, asker="epic-author")
        answered = draft.model_copy(update={"answers": draft.answers + 1, "note": answer.note})
        return Continue(answer, self.author_epic, draft=answered).because("the PM answered")


__all__ = ["EpicAuthor", "MAX_REWORKS"]
