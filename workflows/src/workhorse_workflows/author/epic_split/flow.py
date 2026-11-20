"""Split one milestone into an ordered list of epic skeletons."""
from __future__ import annotations

from pathlib import Path

from workhorse.pyflow import Done, Workflow
from workhorse_workflows.author.draft import DraftLoop
from workhorse_workflows.author.epic_split.nodes import prepare_epic_split, validate_epic_split
from workhorse_workflows.author.epic_split.schemas import EpicSplitContext, EpicSplitDone


class EpicSplit(Workflow):
    """The epic-skeleton boundary; epic prose, seeds, stories, and delivery are unreachable."""

    note: str = ""

    def setup(self) -> EpicSplitContext:
        return self.call(prepare_epic_split)

    def labels(self) -> dict[str, str]:
        return {"work_id": Path(self.ctx.milestone_path).parent.name}

    def start(self) -> Done:
        """Draft the split until the PM passes it, then read back the epics it ordered."""
        done = self.handoff(
            DraftLoop,
            kind="epic-split",
            subject=self.ctx.milestone_path,
            split=self.ctx,
            args={
                "milestone": self.ctx.milestone_path,
                "epics_dir": self.ctx.epics_dir,
                "ledger": self.ctx.pm_ledger,
            },
            note=self.note,
        )
        if done.status == "blocked":
            self.logger.warning("the epic split stays blocked: %s", done.notes)
            return Done(
                EpicSplitDone(
                    status="blocked",
                    milestone_path=self.ctx.milestone_path,
                    notes=done.notes,
                    reworks=done.reworks,
                    answers=done.answers,
                )
            ).because("the split stayed blocked")
        validation = self.call(validate_epic_split, self.ctx)
        return Done(
            EpicSplitDone(
                milestone_path=validation.milestone_path,
                ordered_epics=validation.ordered_epics,
                reworks=done.reworks,
                answers=done.answers,
            )
        ).because("the PM passed the split")


__all__ = ["EpicSplit"]
