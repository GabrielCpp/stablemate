"""`coder`: the run that works its launch's stories off one worklist, one dev owner per item."""
from __future__ import annotations

from typing import Any, ClassVar, Literal

from workhorse import worklist as wl
from workhorse.pyflow import (
    Continue,
    Done,
    NodeNotRunError,
    Workflow,
    WorkflowFailed,
)
from workhorse_workflows.coder.shared import paths, roles, work
from workhorse_workflows.coder.docs import Docs
from workhorse_workflows.coder.fix import Fix
from workhorse_workflows.coder.fix_ci import FixCi
from workhorse_workflows.coder.dev import Dev
from workhorse_workflows.coder.qa import Qa
from workhorse_workflows.coder.qa.nodes import teardown_stack
from workhorse_workflows.coder.shared.branches import (
    branch_epic,
    branch_story,
    epic_branch,
    init_base,
)
from workhorse_workflows.coder.shared.worktree import snapshot_worktree_state
from workhorse_workflows.coder.main.nodes.pr import open_pr, open_story_pr
from workhorse_workflows.coder.shared.queue import (
    ALL_EPICS,
    begin_run,
    prune_epic,
    resolve_launch,
)
from workhorse_workflows.coder.shared.story_commit import (
    check_repos_clean,
    commit_story,
    stamp_story_passed,
)
from workhorse_workflows.coder.shared.story import prepare_story, resolve_workspace_dirs
from workhorse_workflows.coder.shared.schemas.docs import DocsResult
from workhorse_workflows.coder.shared.schemas.queue import ReplanResult
from workhorse_workflows.coder.shared.schemas.story import StoryPaths, WorkspaceDirs


def _documented(result: DocsResult) -> bool:
    """Did the book end up true of this story?"""
    return result.status in ("passed", "not_applicable")


class Coder(Workflow):
    """Work every story the launch names, in order, each by one dev owner, and ship each epic."""

    docs_path: str = ""
    workspace_file: str = ""
    story: str = ""
    epic: str = ALL_EPICS
    operator_mode: Literal["auto", "human", "operator"] = "auto"
    target_env: Literal["local", "dev"] = "local"

    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    max_transitions: ClassVar[int] = 4000

    def setup(self) -> WorkspaceDirs:
        """Resolve every directory this run's agent turns may read, once."""
        return self.call(resolve_workspace_dirs, self.docs_path)

    def labels(self) -> dict[str, str]:
        """Which item, which epic, which mode, how far through: what a run's activity line shows."""
        item = self._active
        return {
            "work_id": item.id if item else self.story,
            "epic": self._epic,
            "mode": self._mode,
            "progress": work.progress(self._worklist, item.id if item else None).progress,
        }


    def start(self) -> Continue:
        """File every story the launch names, in order, and cut the branch they land on."""
        self.call(begin_run, str(self.run_dir))
        launch = self.call(resolve_launch, self.docs_path, self.epic, self.story)
        filed = work.file(
            self._worklist,
            work.story_items([entry.model_dump() for entry in launch.entries]),
            by="launch",
        )
        self.logger.info("filed %d of %d launch stories", len(filed), len(launch.entries))
        if launch.mode == "story":
            branch = self.call(branch_story, self.story, self.docs_path)
            self.logger.info("story mode: %s off %s", branch.story_branch, branch.base_branch)
            return Continue(branch, self.route)
        return Continue(self.call(init_base), self.route)

    def route(self) -> Continue | Done:
        """Take the next story or follow-up off the worklist, or end the run when none is left."""
        taken = self._worklist.claim(1, kind=work.PROGRESS_KINDS, strict=True)
        if not taken:
            if self._mode == "story":
                return Continue(None, self.commit_pr)
            self.logger.info("the worklist is done")
            self.call(teardown_stack, self.docs_path)
            return Done(None)
        if self._mode == "epic":
            self.call(
                branch_epic, self._epic, self.output(init_base).base_branch, str(self.run_dir)
            )
        return Continue(None, self.prepare)

    def prepare(self) -> Continue:
        """Resolve the item's story to paths, and record what was already dirty."""
        item = self._item
        self.call(snapshot_worktree_state, self.docs_path)
        story = self.call(prepare_story, self.docs_path, work.story_of(item), self._epic)
        self.logger.info("preparing %s%s", item.id, self._progress(), extra={"activity": True})
        return Continue(story, self.dev)

    def dev(self, note: str = "") -> Continue:
        """Hand the item to its dev owner, which builds, reviews and fixes it, and answers every finding."""
        item = self._item
        self.logger.info("developing %s%s", item.id, self._progress(), extra={"activity": True})
        result = self.handoff(
            Dev,
            story=self._story.story_slug,
            docs_path=self.docs_path,
            epic=self._story_epic(),
            operator_mode=self.operator_mode,
            target_env=self.target_env,
            branch=self._branch(),
            work_id=item.id,
            follow_up_title=str(item.payload.get("title") or ""),
            follow_up_reason=str(item.payload.get("reason") or ""),
            note=note,
            preexisting=self._preexisting(),
        )
        if result.status == "replan":
            return Continue(result, self.replan, notes=result.operator_notes)
        return Continue(result, self.document)

    def document(self) -> Continue:
        """Fold the story into the OKF book, or replan when the operator scoped its block to the epic."""
        result = self._document()
        if not _documented(result):
            return Continue(result, self.replan, notes=result.notes)
        return Continue(result, self.qa)

    def qa(self) -> Continue:
        """The gate the item turns on: pass it, or send what QA found back to the dev owner."""
        result = self.handoff(
            Qa,
            story=self._story.story_slug,
            docs_path=self.docs_path,
            epic=self._story_epic(),
            operator_mode=self.operator_mode,
            target_env=self.target_env,
            preexisting=self._preexisting(),
        )
        if result.status == "replan":
            return Continue(result, self.replan, notes=result.operator_notes)
        if result.status == "refix":
            slug = self._story.story_slug
            self.logger.info("QA found product defects in %s — back to its dev owner", slug)
            number = work.next_round(self._worklist, self._item.id, "qa")
            findings = [f.model_dump() for f in result.findings]
            return Continue(result, self.refix, number=number, findings=findings)
        return Continue(
            result,
            self.drain,
            docs_recheck_required=result.docs_recheck_required,
        )

    def refix(self, number: int = 1, findings: list[dict[str, Any]] | None = None) -> Continue:
        """File QA's findings against the item, and hand them to its dev owner to answer."""
        item = self._item
        filed = work.file(
            self._worklist,
            work.finding_items(item.id, "qa", number, findings or []),
            by="qa",
        )
        self.logger.info("filed %d QA finding(s) against %s", len(filed), item.id)
        return Continue(None, self.dev)

    def replan(self, notes: str = "") -> Continue:
        """Rewrite the epic from what the operator said, and re-file its open stories."""
        epic = self._epic
        self.logger.info("replanning epic %s", epic, extra={"activity": True})
        turn = roles.turn(self, "replan-epic", returns=ReplanResult)
        result = self.agent(
            turn.prompt,
            returns=turn.returns,
            power="high",
            add_dirs=self._dirs(),
            args=turn.args | {
                "epic": epic,
                "story_slug": self._story.story_slug,
                "story_id": self._story.story_id or self._story.story_slug,
                "story_path": self._story.story_path,
                "spec_dir": self._story.spec_dir,
                "operator_context": notes,
            },
        )
        if self._mode == "story":
            launch = self.call(resolve_launch, self.docs_path, self.epic, self.story)
        else:
            launch = self.call(resolve_launch, self.docs_path, epic)
        filed = work.amend(
            self._worklist, epic, [entry.model_dump() for entry in launch.entries]
        )
        self.logger.info("re-filed %d stories of %s after the replan", len(filed), epic)
        return Continue(result, self.route)

    def drain(self, docs_recheck_required: bool = True) -> Continue:
        """Hand the backlog to the `fix` flow, which drains it to dry and returns."""
        result = self.handoff(
            Fix,
            docs_path=self.docs_path,
            target_env=self.target_env,
            operator_mode=self.operator_mode,
        )
        return Continue(
            result,
            self.finalize,
            docs_recheck_required=docs_recheck_required,
        )

    def finalize(self, docs_recheck_required: bool = True) -> Continue:
        """Recheck documentation after a mutation, then commit the story."""
        result = self._document() if docs_recheck_required else None
        if result is not None and not _documented(result):
            return Continue(result, self.replan, notes=result.notes)
        if self._mode == "epic":
            return Continue(result, self.commit)
        return Continue(result, self.standing)

    def commit(self) -> Continue:
        """Stamp the item passed, or send what the later lanes left uncommitted to its dev owner."""
        story = self._story
        state = self.call(
            check_repos_clean, story.story_slug, story.spec_dir, list(self._preexisting())
        )
        if not state.clean:
            listing = "\n".join(f"- `{path}`" for path in state.dirty[:40])
            note = f"These paths are still uncommitted after the item passed QA:\n\n{listing}"
            return Continue(state, self.dev, note=note)
        if self._item.kind == work.STORY:
            self.call(stamp_story_passed, self._epic, story.story_slug, story.story_path)
        return Continue(state, self.standing)

    def standing(self) -> Continue:
        """The item passed: mark it done, and ship its epic once nothing of it is left."""
        item = self._item
        epic = self._epic
        w = self._worklist
        work.move(w, [item.id], work.DONE, kind=item.kind, by="standing")
        self.logger.info("%s is done%s", item.id, self._progress(), extra={"activity": True})
        if self._mode == "epic" and work.epic_done(w, epic):
            self.logger.info("epic %s has nothing left — opening its PR", epic)
            return Continue(None, self.open_pr, epic=epic)
        return Continue(None, self.route)

    def commit_pr(self) -> Done:
        """Story mode's end: commit what the story left, and open its PR."""
        story = self._story
        branch = self.output(branch_story)
        self.call(
            commit_story,
            "",
            story.story_slug,
            story.spec_dir,
            story.story_path,
            story_id=story.story_id,
        )
        self.call(teardown_stack, self.docs_path)
        return Done(
            self.call(
                open_story_pr,
                story.story_slug,
                branch.base_branch,
                story.story_path,
                story.spec_dir,
                branch.story_branch,
            )
        )


    def open_pr(self, epic: str = "") -> Continue:
        """The epic is done, so ship it."""
        self.call(prune_epic, epic)
        gate = self.call(open_pr, epic, self.output(init_base).base_branch)
        if not gate.should_gate:
            self.logger.info("no PR to gate on for %s — taking the next epic", epic)
            return Continue(gate, self.route)
        return Continue(gate, self.ship)

    def ship(self) -> Continue:
        """Hand the epic's PR to the ship lane, which gets it green and merges it."""
        gate = self.output(open_pr)
        shipped = self.handoff(
            FixCi,
            branch=epic_branch(gate.ci_epic),
            base=gate.ci_base,
            docs_path=self.docs_path,
            operator_mode=self.operator_mode,
        )
        self.logger.info("shipped %s: %s", gate.ci_epic, shipped.summary)
        return Continue(shipped, self.route)

    def _document(self) -> DocsResult:
        """The `Docs` handoff, identical at all three points the story reaches it."""
        return self.handoff(
            Docs,
            story=self._story.story_slug,
            docs_path=self.docs_path,
            epic=self._story_epic(),
            target_env=self.target_env,
            preexisting=self._preexisting(),
            operator_mode=self.operator_mode,
        )

    def _story_epic(self) -> str:
        """`prepare_story.story_epic or _epic` — the *story's* epic."""
        return self._story.story_epic or self._epic

    @property
    def _worklist(self) -> wl.WorkList:
        """The run's worklist, read from disk each time."""
        return work.worklist(self.run_dir)

    @property
    def _active(self) -> wl.WorkItem | None:
        """The story or follow-up `route` claimed, or nothing between items."""
        return next(
            (it for it in self._worklist.items(work.PROGRESS_KINDS) if it.status == work.ACTIVE),
            None,
        )

    @property
    def _item(self) -> wl.WorkItem:
        """The story or follow-up this iteration is working."""
        item = self._active
        if item is None:
            raise WorkflowFailed("no story or follow-up is active on the worklist")
        return item

    @property
    def _mode(self) -> str:
        """`epic` or `story`, as the launch resolved it."""
        try:
            return self.output(resolve_launch).mode
        except NodeNotRunError:
            return "story" if self.story else "epic"

    @property
    def _epic(self) -> str:
        """The epic of the item being worked, or the one the launch named."""
        item = self._active
        epic = str(item.payload.get("epic") or "") if item is not None else ""
        return epic or ("" if self.epic == ALL_EPICS else self.epic)

    def _branch(self) -> str:
        """The branch the item's commits land on."""
        if self._mode == "story":
            return self.output(branch_story).story_branch
        return epic_branch(self._epic)

    def _progress(self) -> str:
        """The ` · 3/7` suffix an activity line carries when the run knows how far through it is."""
        item = self._active
        progress = work.progress(self._worklist, item.id if item else None).progress
        return f" · {progress}" if progress else ""

    def _preexisting(self) -> tuple[str, ...]:
        """What `prepare`'s snapshot found already dirty, or nothing when it never ran."""
        try:
            return tuple(self.output(snapshot_worktree_state).entries)
        except NodeNotRunError:
            return ()

    def _dirs(self) -> list[str]:
        """The directories every agent turn in this graph may read."""
        return list(self.ctx.dirs)

    @property
    def _story(self) -> StoryPaths:
        """The story this iteration is building, as `prepare` resolved it."""
        return self.output(prepare_story)

