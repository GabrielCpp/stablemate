"""Author composition: fill each kind of work from the ostler graph, drain it, then gate completion."""
from __future__ import annotations

from pathlib import Path

from workhorse.pyflow import Await, Continue, Done, Workflow
from workhorse.worklist import WorkItem
from workhorse_workflows.author.epic_author import EpicAuthor
from workhorse_workflows.author.epic_split import EpicSplit
from workhorse_workflows.author.finalize import Finalize
from workhorse_workflows.author.main.nodes import (
    answer_below,
    check_completion,
    check_epic_split,
    contract_digest,
    fill_work,
)
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.nodes import (
    adopt_backlog,
    load_config,
    prune_bullet,
    seed_story,
)
from workhorse_workflows.author.parity_surveyor import ParitySurveyor
from workhorse_workflows.author.shared.schemas import RunContext
from workhorse_workflows.author.story_author import StoryAuthor
from workhorse_workflows.author.story_split import StorySplitFlow
from workhorse_workflows.author.surveyor import Surveyor


class Author(Workflow):
    """Compose independently runnable author stages over one milestone."""

    mode: str = "epic"
    epic: str = ""
    bullet: str = ""
    layers: str = ""
    services: str = ""
    rubric: str = "docs/survey/rubric.md"
    survey_dir: str = "docs/survey"
    baseline_inventory: str = ""
    parity_survey_dir: str = "docs/survey/legacy-vs-new"
    operator_mode: str = "auto"

    def setup(self) -> RunContext:
        """Resolve the paths every handed-off stage works against."""
        cfg = self.call(load_config, mode=self.mode)
        return RunContext(**cfg.model_dump())

    def start(self) -> Continue | Done:
        """Dispatch discovery modes, one backlog story, or the stage chain."""
        if self.mode == "survey":
            return Done(self.handoff(
                Surveyor,
                rubric=self.rubric,
                survey_dir=self.survey_dir,
                operator_mode=self.operator_mode,
            ))
        if self.mode == "parity-survey":
            return Done(self.handoff(
                ParitySurveyor,
                baseline_inventory=self.baseline_inventory,
                survey_dir=self.parity_survey_dir,
            ))
        if self.mode == "story":
            self.call(adopt_backlog)
            seeded = self.call(
                seed_story,
                self.epic,
                self.bullet,
                layers=self.layers,
                services=self.services,
            )
            self.handoff(
                StoryAuthor,
                epic=self.epic,
                story=seeded.story_slug,
                feedback_dir=str(self.run_dir),
                operator_mode=self.operator_mode,
            )
            return Done(self.call(
                prune_bullet,
                seeded.bullet_id,
                seeded.from_backlog,
            ))
        self.call(contract_digest, self.ctx.milestone_path)
        return Continue(None, self.split_epics)

    def _context_path(self) -> Path:
        return Path(self.ctx.repo_root) / paths.author_context(self.ctx.repo_root)

    def split_epics(self) -> Continue:
        """Split the milestone into epics unless it already has a valid ordered split."""
        if not self.call(check_epic_split).ok:
            self.handoff(EpicSplit, operator_mode=self.operator_mode)
        return Continue(None, self.fill_epics)

    def fill_epics(self) -> Continue:
        self.call(fill_work, "epic", str(self.run_dir))
        return Continue(None, self.epics)

    def epics(self) -> Continue | Done | Await:
        return self.pipeline(
            "epic", to=EpicAuthor, n=1, operator_mode=self.operator_mode
        ) or Continue(None, self.fill_story_splits)

    def fill_story_splits(self) -> Continue:
        self.call(fill_work, "story-split", str(self.run_dir))
        return Continue(None, self.story_splits)

    def story_splits(self) -> Continue | Done | Await:
        return self.pipeline(
            "story-split", to=StorySplitFlow, n=1, operator_mode=self.operator_mode
        ) or Continue(None, self.fill_stories)

    def fill_stories(self) -> Continue:
        self.call(fill_work, "story", str(self.run_dir))
        return Continue(None, self.stories)

    def stories(self) -> Continue | Done | Await:
        return self.pipeline("story", to=self.author_story, n=1) or Continue(
            None, self.complete
        )

    def author_story(self, items: list[WorkItem]) -> Continue:
        """Write one story, and keep a story nobody can fix blocked on the work list."""
        item = items[0]
        result = self.handoff(
            StoryAuthor,
            epic=item.payload["epic"],
            story=item.payload["story"],
            feedback_dir=str(self.run_dir),
            operator_mode=self.operator_mode,
            note=item.note,
        )
        if result.status == "blocked":
            self.logger.warning(
                "story '%s' in epic '%s' remains audit-blocked",
                item.payload["story"],
                item.payload["epic"],
            )
            self.work_list.mark(item.id, "blocked", kind="story")
        return Continue(result, self.stories)

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
            return Await(self._context_path(), question, self.complete, baseline=check.digest)
        if check.unfinished:
            listed = "\n".join(
                f"- {row.kind} {row.id}: {row.status} after {row.laps} laps"
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
            )
        return Done(self.handoff(Finalize, operator_mode=self.operator_mode))

    def requeue(self, ids: list[str], question: str) -> Continue:
        """Reset the unfinished rows with the operator's answer as their note, and run the chain again."""
        gate = self._context_path()
        text = gate.read_text(encoding="utf-8") if gate.is_file() else ""
        self.work_list.requeue(ids, answer_below(text, question))
        return Continue(None, self.split_epics)


__all__ = ["Author"]
