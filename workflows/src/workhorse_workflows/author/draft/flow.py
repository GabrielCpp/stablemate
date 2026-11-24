"""Draft one document: write it, check it, have the PM review it, and rework it until it passes or stays blocked."""
from __future__ import annotations

from typing import Any

from workhorse.pyflow import Continue, Done, Workflow, WorkflowFailed, dry_run
from workhorse_workflows.author.draft.kinds import KINDS, REWORK, WRITE, Kind
from workhorse_workflows.author.draft.schemas import Draft, DraftDone, spent_labels
from workhorse_workflows.author.epic_split.nodes import validate_epic_split
from workhorse_workflows.author.epic_split.schemas import EpicSplitContext
from workhorse_workflows.author.pm import MAX_ANSWERS, GapAnswer, PMReview
from workhorse_workflows.author.shared.nodes import (
    check_story_grounding,
    load_config,
    record_attempt,
    validate_coverage,
    validate_story,
)
from workhorse_workflows.author.shared.schemas import Config, Defects
from workhorse_workflows.author.story_split.nodes import derive_story_services

MAX_REWORKS = 3


@dry_run(kind="story")
class DraftLoop(Workflow):
    """Loop one document through write, check, PM review and rework, whatever its kind.

    `subject` is what the PM reviews. `args` are the prompt arguments the caller owns.
    `epic`, `epic_dir`, `story_dir` and `split` are what the kind's checks read. With
    `written`, the document already exists and the loop opens at its check.
    """

    kind: str = ""
    subject: str = ""
    epic: str = ""
    epic_dir: str = ""
    story_dir: str = ""
    split: EpicSplitContext | None = None
    args: dict[str, str] = {}
    note: str = ""
    written: bool = False
    max_answers: int = MAX_ANSWERS

    def setup(self) -> Config:
        return self.call(load_config, mode="draft")

    def labels(self) -> dict[str, str]:
        kind = KINDS.get(self.kind)
        return {"work_id": self.subject, "epic": self.epic, "progress": kind.progress if kind else ""}

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        kind = KINDS.get(self.kind)
        return self.labels() | (spent_labels(params, kind.counter) if kind else {})

    @property
    def _kind(self) -> Kind:
        return KINDS[self.kind]

    def _args(self, draft: Draft, **extra: str) -> dict[str, str]:
        return {
            **self.args,
            "findings": draft.findings,
            "note": "\n\n".join(part for part in (self.note, draft.note) if part),
            **extra,
        }

    def _check(self) -> Defects:
        if self.kind == "epic-split":
            split = self.call(validate_epic_split, self.split or EpicSplitContext())
            return Defects(ok=split.ok, errors=split.errors)
        if self.kind == "story-split":
            self.call(derive_story_services, self.epic)
            return self.call(validate_coverage, self.epic_dir, require_authored=False)
        structure = self.call(validate_story, self.story_dir)
        if not structure.ok:
            return structure
        return self.call(check_story_grounding, self.story_dir, self.epic_dir)

    def _blocked(self, notes: str, draft: Draft) -> Done:
        self.logger.warning("the %s draft of %s stays blocked: %s", self.kind, self.subject, notes)
        return Done(
            DraftDone(status="blocked", notes=notes, reworks=draft.reworks, answers=draft.answers)
        ).because("out of budget")

    def _rework(self, draft: Draft, findings: str, prior: str) -> Continue | Done:
        if draft.reworks >= MAX_REWORKS:
            return self._blocked(findings, draft)
        return Continue(
            None, self.rework, draft=draft.model_copy(update={"findings": findings, "prior": prior})
        ).because("needs rework")

    def _ask(self, question: str, phase: str, draft: Draft) -> Continue | Done:
        if draft.answers >= self.max_answers:
            return self._blocked(question, draft)
        return Continue(None, self.ask_pm, question=question, phase=phase, draft=draft).because(
            "the writer has a question"
        )

    def start(self) -> Continue:
        if self.kind not in KINDS:
            raise WorkflowFailed(
                f"the draft loop has no kind '{self.kind}'; its kinds are {sorted(KINDS)}",
                failure_class="draft-unknown-kind",
            )
        if self.written:
            return Continue(None, self.check, draft=Draft()).because("already written")
        return Continue(None, self.write, draft=Draft()).because("nothing written yet")

    def write(self, draft: Draft) -> Continue | Done:
        """Write the document, with the PM's answer when the last write asked a question."""
        self.logger.info("drafting %s", self.subject, extra={"activity": True})
        result = self.agent(
            WRITE[self.kind],
            returns=self._kind.returns,
            power="high",
            cwd=self.ctx.repo_root,
            args=self._args(draft),
        )
        if result.status in self._kind.blocked:
            return self._ask(result.notes, "write", draft)
        return Continue(result, self.check, draft=draft.model_copy(update={"note": ""})).because("written")

    def check(self, draft: Draft) -> Continue | Done:
        """Run the kind's mechanical checks."""
        defects = self._check()
        if not defects.ok:
            return self._rework(draft, defects.errors, draft.prior)
        return Continue(defects, self.review, draft=draft).because("the checks pass")

    def review(self, draft: Draft) -> Continue | Done:
        """Have the PM review the document, verifying the last review's findings."""
        verdict = self.handoff(
            PMReview, stage=self._kind.stage, subject=self.subject, epic=self.epic, prior=draft.prior
        )
        if verdict.passed:
            if verdict.notes:
                self.logger.info("the PM passed %s with notes:\n%s", self.subject, verdict.notes)
            return Done(DraftDone(reworks=draft.reworks, answers=draft.answers)).because("the PM passed it")
        return self._rework(draft, verdict.notes, verdict.notes)

    def rework(self, draft: Draft) -> Continue | Done:
        """Repair what the check or the review found, with the attempts so far when the kind keeps a ledger."""
        attempts = ""
        if self.story_dir:
            ledger = self.call(
                record_attempt, f"{self.story_dir.rstrip('/')}/attempts.md", str(draft.reworks), draft.findings
            )
            attempts = ledger.prior_attempts
        result = self.agent(
            REWORK[self.kind],
            returns=self._kind.returns,
            power="high",
            cwd=self.ctx.repo_root,
            args=self._args(draft, prior_attempts=attempts),
        )
        if result.status in self._kind.blocked:
            return self._ask(result.notes, "rework", draft)
        return Continue(
            result, self.check, draft=draft.model_copy(update={"note": "", "reworks": draft.reworks + 1})
        ).because("reworked")

    def ask_pm(self, question: str, phase: str, draft: Draft) -> Continue:
        """Have the PM answer the writer's question, then run the turn that asked it again."""
        answer = self.handoff(GapAnswer, question=question, asker=self._kind.asker)
        answered = draft.model_copy(update={"note": answer.note, "answers": draft.answers + 1})
        if phase == "write":
            return Continue(answer, self.write, draft=answered).because("the PM answered")
        return Continue(answer, self.rework, draft=answered).because("the PM answered")


__all__ = ["MAX_REWORKS", "DraftLoop"]
