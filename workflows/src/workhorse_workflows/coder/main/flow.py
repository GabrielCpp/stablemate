"""`coder`: the epic/story loop."""
from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar, Literal

from workhorse.pyflow import (
    Await,
    Continue,
    Done,
    NodeNotRunError,
    Workflow,
    WorkflowFailed,
)
from workhorse_workflows.coder.shared import paths, roles
from workhorse_workflows.coder.dev import Dev
from workhorse_workflows.coder.docs import Docs
from workhorse_workflows.coder.fix import Fix
from workhorse_workflows.coder.fix_ci import FixCi
from workhorse_workflows.coder.qa import Qa
from workhorse_workflows.coder.qa.nodes import teardown_stack
from workhorse_workflows.coder.review import Review
from workhorse_workflows.coder.shared.ci import epic_branch, poll_pr_checks, push_ci_fix
from workhorse_workflows.coder.shared.worktree import snapshot_worktree_state
from workhorse_workflows.kit.telemetry import counter_labels
from workhorse_workflows.coder.main.nodes.pr import (
    flag_ci_failure,
    flag_merge_failure,
    merge_pr,
    open_pr,
    open_story_pr,
)
from workhorse_workflows.coder.shared.queue import (
    begin_run,
    branch_epic,
    branch_story,
    check_repos_clean,
    commit_story,
    flag_epic_blocked,
    init_base,
    prune_epic,
    select_epic,
    select_story,
    stamp_story_passed,
)
from workhorse_workflows.coder.shared.story import prepare_story, resolve_workspace_dirs
from workhorse_workflows.coder.shared.schemas.docs import DocsResult
from workhorse_workflows.coder.shared.schemas.pr import MergeFixResult
from workhorse_workflows.coder.shared.schemas.queue import ReplanResult, WorktreeSettled
from workhorse_workflows.coder.shared.schemas.render import schema_block
from workhorse_workflows.coder.shared.schemas.story import StoryPaths, WorkspaceDirs


_QA_RETRY_ARTIFACTS = {
    "qa_plan.py",
    "qa-plan.md",
    "qa-plan.yml",
    "qa-plan.yaml",
    "visual-verdicts.json",
}


def _docs_changed_qa_retry_artifact(result: DocsResult, spec_dir: str) -> bool:
    spec = Path(spec_dir).as_posix().rstrip("/")
    specs = {spec}
    marker = "/docs/specs/"
    if marker in spec:
        specs.add(f"docs/specs/{spec.split(marker, 1)[1]}")
    for node in result.authored_nodes:
        path = node.split("#", 1)[0]
        if Path(path).name not in _QA_RETRY_ARTIFACTS:
            continue
        if path.startswith("docs/specs/"):
            return True
        if any(path.startswith(f"{candidate}/") for candidate in specs):
            return True
    return False


def _documented(result: DocsResult) -> bool:
    """Did the book end up true of this story?"""
    return result.status in ("passed", "not_applicable")


def _docs_notes(result: DocsResult, what: str) -> str:
    """The reason the gate shows the operator, with the verdict that produced it named."""
    return f"{result.status or 'no status'} — {result.notes or 'no reason given'} ({what})"


class Coder(Workflow):
    """Implement one epic's stories end to end, or one named story."""

    mode: Literal["epic", "story"] = "epic"
    docs_path: str = ""
    workspace_file: str = ""
    story: str = ""
    epic: str = ""
    operator_mode: Literal["auto", "human", "operator"] = "auto"
    target_env: Literal["local", "dev"] = "local"

    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    MAX_CI_REWORKS: ClassVar[int] = 3
    MAX_MERGE_REWORKS: ClassVar[int] = 2

    max_transitions: ClassVar[int] = 4000

    def setup(self) -> WorkspaceDirs:
        """Resolve every directory this run's agent turns may read, once."""
        return self.call(resolve_workspace_dirs, self.docs_path)

    def labels(self) -> dict[str, str]:
        """Which story, which epic, which mode, how far through: what a run's activity line shows."""
        base = {"work_id": self.story, "epic": self.epic, "mode": self.mode, "progress": ""}
        try:
            pick = self.output(select_story)
        except NodeNotRunError:
            return base
        return {
            **base,
            "work_id": pick.story_slug or self.story,
            "epic": pick.epic or self.epic,
            "progress": pick.progress,
        }

    BUDGET_LABELS: ClassVar[tuple[str, ...]] = ("ci_rework", "merge_rework")

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        """The same, plus which attempt of which budget the next state is on."""
        return self.labels() | counter_labels(params, "coder", self.BUDGET_LABELS)


    def start(self) -> Continue:
        """The queue, or the one story we were pointed at."""
        self.call(begin_run, str(self.run_dir))
        if self.mode == "story":
            branch = self.call(branch_story, self.story, self.docs_path)
            self.logger.info("story mode: %s off %s", branch.story_branch, branch.base_branch)
            return Continue(branch, self.prepare, slug=self.story)
        return Continue(self.call(init_base), self.select_epic)


    def select_epic(self) -> Continue | Done:
        """Take the front of the queue, and branch every repo for it."""
        pick = self.call(select_epic, self.docs_path, str(self.run_dir))
        if not pick.has_epic:
            self.logger.info("no epic to work: %s", pick.reason)
            self.call(teardown_stack, self.docs_path)
            return Done(pick)
        base = self.output(init_base).base_branch
        self.call(branch_epic, pick.epic, base, str(self.run_dir))
        return Continue(pick, self.select_story)

    def select_story(self) -> Continue:
        """The next unimplemented story of this epic."""
        epic = self._epic
        pick = self.call(select_story, epic, self.docs_path, str(self.run_dir))
        if pick.story_outcome == "story":
            return Continue(pick, self.prepare, slug=pick.story_slug)
        if pick.story_outcome == "done":
            self.logger.info("epic %s has no stories left — opening its PR", epic)
            return Continue(pick, self.open_pr)
        self.call(flag_epic_blocked, epic, str(self.run_dir), pick.reason)
        return Continue(pick, self.select_epic)


    def prepare(self, slug: str = "") -> Continue:
        """Resolve the slug to paths, and seed the triage counter."""
        self.call(snapshot_worktree_state, self.docs_path)
        story = self.call(prepare_story, self.docs_path, slug, self._epic)
        self.logger.info("preparing %s%s", slug, self._progress(), extra={"activity": True})
        return Continue(story, self.dev)

    def dev(self, triage: int = 0) -> Continue:
        """Plan and implement the story."""
        slug = self._story.story_slug
        self.logger.info("implementing %s%s", slug, self._progress(), extra={"activity": True})
        result = self.handoff(
            Dev,
            story=slug,
            docs_path=self.docs_path,
            epic=self._story_epic(),
            operator_mode=self.operator_mode,
            target_env=self.target_env,
        )
        if result.status == "replan":
            return Continue(result, self.replan, notes=result.operator_notes)
        return Continue(
            result,
            self.review,
            triage=triage,
            session_turns=result.session_turns,
        )

    def review(self, triage: int = 0, session_turns: int = 0) -> Continue:
        """Code review and reuse, with no branch on the outcome."""
        slug = self._story.story_slug
        self.logger.info("reviewing %s%s", slug, self._progress(), extra={"activity": True})
        result = self.handoff(
            Review,
            story=slug,
            docs_path=self.docs_path,
            epic=self._story_epic(),
            operator_mode=self.operator_mode,
            inherited_turns=session_turns,
        )
        return Continue(result, self.document, triage=triage)

    def document(self, triage: int = 0) -> Continue:
        """Fold the story into the OKF book."""
        result = self._document()
        if not _documented(result):
            return Continue(result, self.blocked_docs, triage=triage,
                            notes=_docs_notes(result, "story"))
        return Continue(result, self.qa, triage=triage)

    def blocked_docs(
        self,
        triage: int = 0,
        notes: str = "",
        resume_at: Literal["document", "give_up", "finalize"] = "document",
        attempts: int = 0,
    ) -> Await:
        """The docs phase would not pass the story: the run parks for a human, not ends failed."""
        slug = self._story.story_slug
        return Await(
            paths.operator_context_path(paths.launch_repo_root(self.repo_dir), "docs-operator", slug),
            f"Documentation did not pass for story {slug!r}: {notes or 'no reason given'}.\n\n"
            "Fix the code, the spec or the plan so the book can be made true of it, and "
            "touch this file when the run should try again.",
            self.docs_operator,
            triage=triage,
            resume_at=resume_at,
            attempts=attempts,
        )

    def docs_operator(
        self,
        triage: int = 0,
        resume_at: Literal["document", "give_up", "finalize"] = "document",
        attempts: int = 0,
    ) -> Continue:
        """The consume half of the docs gate: re-document on the operator's fix."""
        self.logger.info(
            "operator answered the docs gate — redocumenting %s", self._story.story_slug
        )
        if resume_at == "give_up":
            return Continue(None, self.give_up, attempts=attempts)
        if resume_at == "finalize":
            return Continue(None, self.finalize)
        return Continue(None, self.document, triage=triage)

    def qa(self, triage: int = 0) -> Continue:
        """The four-way gate the whole loop turns on."""
        result = self.handoff(
            Qa,
            story=self._story.story_slug,
            docs_path=self.docs_path,
            epic=self._story_epic(),
            operator_mode=self.operator_mode,
            target_env=self.target_env,
            triage_scope=triage,
            preexisting=self._preexisting(),
        )
        if result.status == "replan":
            return Continue(result, self.replan, notes=result.operator_notes)
        if result.status == "rescope":
            self.logger.info("QA rescoped %s — back to dev", self._story.story_slug)
            return Continue(result, self.dev, triage=result.triage_scope)
        if result.status == "refix":
            self.logger.info(
                "QA found a product defect in %s — back to dev", self._story.story_slug
            )
            return Continue(result, self.dev, triage=result.triage_scope)
        if result.status == "inconclusive":
            return Continue(result, self.give_up, attempts=result.qa_rework)
        return Continue(
            result,
            self.drain,
            docs_recheck_required=result.docs_recheck_required,
        )

    def replan(self, notes: str = "") -> Continue:
        """Rewrite the epic from what the operator said, and re-select."""
        self.logger.info("replanning epic %s", self._epic, extra={"activity": True})
        turn = roles.turn(self, "replan-epic", returns=ReplanResult)
        result = self.agent(
            turn.prompt,
            returns=turn.returns,
            power="high",
            add_dirs=self._dirs(),
            args=turn.args | {
                "epic": self._epic,
                "story_slug": self._story.story_slug,
                "story_id": self._story.story_id or self._story.story_slug,
                "story_path": self._story.story_path,
                "spec_dir": self._story.spec_dir,
                "operator_context": notes,
            },
        )
        return Continue(result, self.select_story)

    def give_up(self, attempts: int = 0) -> Continue:
        """QA could not be carried: the dev-target report ends here, and the run stops."""
        result = self._document()
        if not _documented(result):
            return Continue(
                result,
                self.blocked_docs,
                notes=_docs_notes(result, "failed story"),
                resume_at="give_up",
                attempts=attempts,
            )
        if _docs_changed_qa_retry_artifact(result, self._story.spec_dir):
            self.logger.info(
                "documentation changed QA retry artifacts for %s — rerunning QA",
                self._story.story_slug,
                extra={"activity": True},
            )
            return Continue(result, self.qa)
        raise WorkflowFailed(
            f"QA never passed for story {self._story.story_slug!r} after {attempts} "
            f"attempt(s); nothing was committed for this story.",
            failure_class="qa-give-up",
            artifacts={"spec_dir": str(self._story.spec_dir)},
        )


    def drain(self, docs_recheck_required: bool = True) -> Continue:
        """Hand the backlog to the `fix` flow, which drains it to dry and returns."""
        result = self.handoff(
            Fix,
            docs_path=self.docs_path,
            target_env=self.target_env,
        )
        return Continue(
            result,
            self.finalize,
            docs_recheck_required=docs_recheck_required,
        )


    def finalize(self, docs_recheck_required: bool = True) -> Continue:
        """Recheck documentation after a mutation, then commit the story."""
        if not docs_recheck_required:
            if self.mode == "epic":
                return Continue(None, self.commit)
            return Continue(None, self.commit_pr)
        result = self._document()
        if not _documented(result):
            return Continue(
                result,
                self.blocked_docs,
                notes=_docs_notes(result, "story (final pass)"),
                resume_at="finalize",
            )
        if self.mode == "epic":
            return Continue(result, self.commit)
        return Continue(result, self.commit_pr)

    def commit(self, dirty_laps: int = 0) -> Continue | Await:
        """The story's work is recorded, or it parks."""
        story = self._story
        state = self.call(
            check_repos_clean, story.story_slug, story.spec_dir, list(self._preexisting())
        )
        if not state.clean:
            if dirty_laps:
                return self._dirty_gate(state.dirty)
            return Continue(state, self.settle, dirty_laps=1)
        self.reset_session(self._settle_chain())
        result = self.call(
            stamp_story_passed, self._epic, story.story_slug, story.story_path
        )
        return Continue(result, self.select_story)

    def settle(self, dirty_laps: int = 1) -> Continue | Await:
        """One chained turn to record what the story left on disk, then re-read the tree."""
        state = self.output(check_repos_clean)
        story = self._story
        self.logger.info(
            "asking %s to settle %d uncommitted path(s)", story.story_slug, len(state.dirty),
            extra={"activity": True},
        )
        result = self.agent(
            "main/prompts/settle-worktree.md",
            power="medium",
            returns=WorktreeSettled,
            add_dirs=self._dirs(),
            args={
                "story_path": story.story_path,
                "spec_dir": story.spec_dir,
                "story_slug": story.story_slug,
                "story_id": story.story_id or story.story_slug,
                "epic": self._epic,
                "dirty_paths": "\n".join(state.dirty),
                "result_schema": schema_block(WorktreeSettled),
            },
            session=self._settle_chain(),
        )
        if result.blocked:
            return self._dirty_gate(state.dirty, notes=result.notes)
        return Continue(result, self.commit, dirty_laps=dirty_laps)

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


    def open_pr(self) -> Continue:
        """The epic is done, so ship it."""
        epic = self._epic
        self.call(prune_epic, epic)
        gate = self.call(open_pr, epic, self.output(init_base).base_branch, str(self.run_dir))
        if not gate.should_gate:
            self.logger.info("no PR to gate on for %s — taking the next epic", epic)
            return Continue(gate, self.select_epic)
        return Continue(gate, self.ci)

    def ci(self, ci_rework: int = 0, merge_rework: int = 0) -> Continue | Await:
        """Is the epic's PR green?"""
        gate = self.output(open_pr)
        checks = self.call(poll_pr_checks, "", epic_branch(gate.ci_epic))
        if checks.blocked:
            self.logger.warning(
                "CI for %s could not be read (%s) — parking it for an operator",
                gate.ci_epic, checks.summary,
            )
            return self._ci_gate(gate.ci_epic, ci_rework, checks.summary, merge_rework)
        if checks.status == "unavailable":
            self.logger.warning(
                "no CI verdict for %s (%s) — merging without one",
                gate.ci_epic, checks.summary,
            )
        if checks.status in ("passed", "unavailable"):
            return Continue(checks, self.merge, merge_rework=merge_rework)
        if ci_rework >= self.MAX_CI_REWORKS:
            return self._ci_gate(gate.ci_epic, ci_rework, checks.summary, merge_rework)
        return Continue(checks, self.repair_ci, ci_rework=ci_rework, merge_rework=merge_rework)

    def repair_ci(self, ci_rework: int = 0, merge_rework: int = 0) -> Continue | Await:
        """One automated attempt at red CI: fix it, push it, spend a lap."""
        gate = self.output(open_pr)
        summary = self.output(poll_pr_checks).summary
        self.handoff(
            FixCi, repo="", branch=epic_branch(gate.ci_epic), docs_path=self.docs_path,
        )
        push = self.call(push_ci_fix, "", epic_branch(gate.ci_epic))
        if push.status == "unavailable":
            self.logger.warning(
                "nothing to push the %s fix to (%s) — re-polling anyway",
                gate.ci_epic, push.notes,
            )
        if push.status in ("pushed", "unavailable"):
            return Continue(push, self.ci, ci_rework=ci_rework + 1, merge_rework=merge_rework)
        return self._ci_gate(gate.ci_epic, ci_rework, summary, merge_rework)

    def ci_operator(self, merge_rework: int = 0) -> Continue:
        """The consume half of the CI gate: the operator acted, so poll again."""
        self.logger.info("operator answered the CI gate — re-polling")
        return Continue(None, self.ci, ci_rework=0, merge_rework=merge_rework)

    def merge(self, merge_rework: int = 0) -> Continue | Await:
        """Land the epic's PR."""
        gate = self.output(open_pr)
        outcome = self.call(merge_pr, gate.ci_epic, gate.ci_base)
        if outcome.merge_status == "unavailable":
            self.logger.warning(
                "no PR to merge for %s — taking the next epic with the branch unmerged",
                gate.ci_epic,
            )
        if outcome.merge_status in ("merged", "unavailable"):
            self.reset_session(f"merge-fix:{gate.ci_epic}")
            return Continue(outcome, self.select_epic)
        if merge_rework >= self.MAX_MERGE_REWORKS:
            return self._merge_gate(gate.ci_epic, gate.ci_base, merge_rework)
        return Continue(outcome, self.fix_merge, merge_rework=merge_rework)

    def fix_merge(self, merge_rework: int = 0) -> Continue | Await:
        """One automated attempt at a merge that would not land."""
        gate = self.output(open_pr)
        self.logger.info("resolving the merge for %s", gate.ci_epic, extra={"activity": True})
        result = self.agent(
            "main/prompts/fix-merge.md",
            returns=MergeFixResult,
            power="high",
            add_dirs=self._dirs(),
            args={
                "ci_epic": gate.ci_epic,
                "ci_base": gate.ci_base,
                "result_schema": schema_block(MergeFixResult),
            },
            session=f"merge-fix:{gate.ci_epic}",
        )
        if result.blocked:
            self.logger.info("the merge resolver reported it cannot decide: %s", result.notes)
            return self._merge_gate(gate.ci_epic, gate.ci_base, merge_rework)
        push = self.call(push_ci_fix, "", gate.ci_epic)
        if push.status == "unavailable":
            self.logger.warning(
                "nothing to push the %s merge resolution to (%s) — re-merging anyway",
                gate.ci_epic, push.notes,
            )
        if push.status in ("pushed", "unavailable"):
            return Continue(push, self.merge, merge_rework=merge_rework + 1)
        return self._merge_gate(gate.ci_epic, gate.ci_base, merge_rework)

    def merge_operator(self) -> Continue:
        """The consume half of the merge gate: try the merge again, budget reset."""
        self.logger.info("operator answered the merge gate — re-merging")
        return Continue(None, self.merge, merge_rework=0)

    def dirty_operator(self) -> Continue:
        """The consume half of the dirty-tree gate: re-read the tree, budget reset."""
        self.logger.info("operator answered the dirty-tree gate — re-reading the worktree")
        return Continue(None, self.commit, dirty_laps=0)


    def _ci_gate(
        self,
        ci_epic: str,
        attempts: int,
        summary: str,
        merge_rework: int,
    ) -> Await:
        """The automated attempts are spent, so the epic parks for a person."""
        self.call(flag_ci_failure, ci_epic, str(attempts), summary)
        return Await(
            paths.operator_context_path(paths.launch_repo_root(self.repo_dir), "ci-operator", ci_epic),
            f"CI is still failing on `{ci_epic}` after {attempts} automated attempt(s).\n\n"
            f"{summary or 'no summary available'}\n\n"
            "Fix it on the branch (or in the pipeline) and touch this file when the run "
            "should poll again.",
            self.ci_operator,
            merge_rework=merge_rework,
        )

    def _merge_gate(self, ci_epic: str, ci_base: str, attempts: int) -> Await:
        """The merge-side twin of `_ci_gate`."""
        self.call(flag_merge_failure, ci_epic, ci_base, str(attempts))
        return Await(
            paths.operator_context_path(paths.launch_repo_root(self.repo_dir), "merge-operator", ci_epic),
            f"`{ci_epic}` will not merge into `{ci_base}` after {attempts} automated "
            "attempt(s).\n\nResolve it and touch this file when the run should try again.",
            self.merge_operator,
        )

    def _dirty_gate(self, dirty: list[str], notes: str = "") -> Await:
        """The uncommitted-work arm of `commit`: the story parks, it is not swept into a commit."""
        slug = self._story.story_slug
        self.reset_session(self._settle_chain())
        listing = "\n".join(f"- `{path}`" for path in dirty[:40])
        elided = f"\n\n_… and {len(dirty) - 40} more._" if len(dirty) > 40 else ""
        return Await(
            paths.operator_context_path(paths.launch_repo_root(self.repo_dir), "dirty-tree-operator", slug),
            f"`{slug}` finished with uncommitted work still on disk, and the lap that was "
            "asked to record it did not.\n\n"
            f"{listing}{elided}\n\n"
            + (f"The agent's own account:\n\n{notes}\n\n" if notes.strip() else "")
            + "Commit what belongs to this story, discard or set aside what does not, and "
            "touch this file when the run should re-read the tree.",
            self.dirty_operator,
        )

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

    def _settle_chain(self) -> str:
        """The conversation the settle lap runs on, keyed per story."""
        return f"settle-worktree:{self._story.story_slug}"

    def _story_epic(self) -> str:
        """`prepare_story.story_epic or _epic` — the *story's* epic."""
        return self._story.story_epic or self._epic

    @property
    def _epic(self) -> str:
        """`select_epic.epic or self.epic` — the epic the *queue* is working."""
        try:
            return self.output(select_epic).epic or self.epic
        except NodeNotRunError:
            return self.epic

    def _progress(self) -> str:
        """The ` · 3/7` suffix an activity line carries when the run knows how far through it is."""
        try:
            progress = self.output(select_story).progress
        except NodeNotRunError:
            return ""
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

