"""Author composition: fill each kind of work from the planning graph, drain it, then gate completion."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from workhorse.pyflow import Await, Continue, Done, Workflow, WorkflowFailed
from workhorse.worklist import WorkItem
from workhorse_workflows.author.epic_author import EpicAuthor
from workhorse_workflows.author.epic_split.flow import EpicSplit
from workhorse_workflows.author.finalize import Finalize
from workhorse_workflows.author.main.nodes import (
    check_completion,
    check_epic_split,
    contract_digest,
    fill_work,
    snapshot_epics,
)
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.answer import answer_below
from workhorse_workflows.author.shared.nodes import (
    load_config,
    promote_record,
    seed_story,
)
from workhorse_workflows.author.parity_surveyor import ParitySurveyor
from workhorse_workflows.author.shared.schemas import RunContext
from workhorse_workflows.author.story_author import StoryAuthor
from workhorse_workflows.author.story_split.flow import StorySplitFlow
from workhorse_workflows.author.story_split.nodes import derive_story_services

MODES = ("epic", "story", "parity-survey")
STAGES = ("epic", "story-split", "story")


class Author(Workflow):
    """Compose independently runnable author stages over one milestone."""

    mode: str = "epic"
    epic: str = ""
    record: str = ""
    layers: str = ""
    services: str = ""
    baseline_inventory: str = ""
    parity_survey_dir: str = "docs/survey/legacy-vs-new"
    operator_mode: str = "auto"

    def setup(self) -> RunContext:
        """Resolve the paths every handed-off stage works against."""
        if self.mode not in MODES:
            raise WorkflowFailed(f"unknown author mode '{self.mode}': the author runs one of {', '.join(MODES)}")
        cfg = self.call(load_config, mode=self.mode)
        return RunContext(**cfg.model_dump())

    def start(self) -> Continue | Done:
        """Dispatch discovery modes, one register story, or the stage chain."""
        if self.mode == "parity-survey":
            return Done(self.handoff(
                ParitySurveyor,
                baseline_inventory=self.baseline_inventory,
                survey_dir=self.parity_survey_dir,
            )).because("parity survey mode")
        if self.mode == "story":
            seeded = self.call(
                seed_story,
                self.epic,
                self.record,
                layers=self.layers,
                services=self.services,
            )
            self.call(derive_story_services, self.epic)
            self.handoff(
                StoryAuthor,
                epic=self.epic,
                story=seeded.story_slug,
                feedback_dir=str(self.run_dir),
            )
            return Done(self.call(
                promote_record,
                seeded.record_id,
                self.epic,
                seeded.story_slug,
            )).because("register story written")
        self.call(contract_digest, self.ctx.milestone_path)
        self.call(snapshot_epics)
        return Continue(None, self.split_epics).because("milestone digested")

    def _context_path(self) -> Path:
        return Path(self.ctx.repo_root) / paths.author_context(self.ctx.repo_root)

    def split_epics(self, note: str = "") -> Continue | Await:
        """Split the milestone into epics unless it already has a valid ordered split."""
        if not self.call(check_epic_split).ok:
            result = self.handoff(EpicSplit, note=note)
            if result.status == "blocked":
                return Await(
                    self._context_path(),
                    result.notes,
                    self.answered_split,
                    question=result.notes,
                ).because("the split stayed blocked")
        return Continue(None, self.fill).because("the milestone has an ordered split")

    def answered_split(self, question: str) -> Continue:
        """Run the epic split again with the operator's answer as its note."""
        gate = self._context_path()
        text = gate.read_text(encoding="utf-8") if gate.is_file() else ""
        return Continue(None, self.split_epics, note=answer_below(text, question)).because(
            "the operator answered"
        )

    def fill(self, stage: int = 0) -> Continue:
        """Queue one stage's rows from the planning graph."""
        self.call(fill_work, STAGES[stage], str(self.run_dir))
        return Continue(None, self.drain, stage=stage).because("rows queued")

    def drain(self, stage: int = 0) -> Continue | Done | Await:
        """Hand the stage's rows to its sub-flow one at a time, then move to the next stage."""
        if stage + 1 < len(STAGES):
            after = Continue(None, self.fill, stage=stage + 1).because("stage drained")
        else:
            after = Continue(None, self.complete).because("last stage drained")
        return self.pipeline(STAGES[stage], to=self.author_row, n=1, stage=stage) or after

    def author_row(self, items: list[WorkItem], stage: int) -> Continue:
        """Author one row through its stage's sub-flow, and keep a row nobody can fix blocked on the work list."""
        item = items[0]
        kind = STAGES[stage]
        result = self._author(kind, item)
        if result.status == "blocked":
            self.logger.warning("%s '%s' remains blocked", kind, item.id)
            self.work_list.mark(item.id, "blocked", kind=kind, note=result.notes)
        return Continue(result, self.drain, stage=stage).because("row authored or blocked")

    def _author(self, kind: str, item: WorkItem) -> Any:
        epic = item.payload["epic"]
        if kind == "epic":
            return self.handoff(EpicAuthor, epic=epic, note=item.note)
        if kind == "story-split":
            return self.handoff(StorySplitFlow, epic=epic, note=item.note)
        return self.handoff(
            StoryAuthor,
            epic=epic,
            story=item.payload["story"],
            feedback_dir=str(self.run_dir),
            note=item.note,
        )

    def complete(self, baseline: str = "") -> Await | Done:
        """Finalize only when the contract held and every row is done; both gates wait for a human."""
        accepted = baseline or self.output(contract_digest).digest
        check = self.call(
            check_completion,
            self.ctx.milestone_path,
            accepted,
            str(self.run_dir),
        )
        if not check.matches:
            question = (
                "The milestone body changed while the run authored from it. "
                f"Its digest is now {check.digest}. Answer to accept the change "
                "and finish the run, or restore the body and answer."
            )
            return Await(self._context_path(), question, self.complete, baseline=check.digest).because(
                "the milestone body changed"
            )
        if check.unfinished:
            listed = "\n".join(
                f"- {row.kind} {row.id}: {row.status} after {row.laps} laps"
                + (f". {row.note}" if row.note else "")
                for row in check.unfinished
            )
            question = (
                f"The run left {len(check.unfinished)} work items unfinished:\n{listed}\n\n"
                "Answer to requeue them with your answer as their context."
            )
            return Await(
                self._context_path(),
                question,
                self.requeue,
                ids=[row.id for row in check.unfinished],
                question=question,
            ).because("rows left unfinished")
        return Done(self.handoff(
            Finalize,
            operator_mode=self.operator_mode,
            baseline=self.output(snapshot_epics).model_dump_json(),
        )).because("every row done")

    def requeue(self, ids: list[str], question: str) -> Continue:
        """Reset the unfinished rows with the operator's answer as their note, and run the chain again."""
        gate = self._context_path()
        text = gate.read_text(encoding="utf-8") if gate.is_file() else ""
        self.work_list.requeue(ids, answer_below(text, question))
        return Continue(None, self.split_epics).because("rows requeued with the answer")


__all__ = ["Author"]
