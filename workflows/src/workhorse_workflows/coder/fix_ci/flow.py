"""One CI owner gets each workspace repo's epic branch green, then the lane merges the epic."""
from __future__ import annotations

from typing import ClassVar

from workhorse.pyflow import Await, Continue, Done, NodeNotRunError, Workflow
from workhorse_workflows.coder.shared import paths, roles
from workhorse_workflows.coder.shared.branches import epic_of_branch
from workhorse_workflows.coder.shared.ci import (
    poll_pr_checks,
    push_ci_fix,
    select_ci_repo,
)
from workhorse_workflows.coder.fix_ci.merge import flag_merge_failure, merge_pr
from workhorse_workflows.coder.shared.dev import read_operator_context
from workhorse_workflows.coder.shared.escalation import context_path, escalation
from workhorse_workflows.coder.shared.owner import (
    HUMAN_MODES,
    MAX_BLOCKS,
    MAX_LAPS,
    SILENCE_S,
    UNBOUNDED,
    owner_profile,
)
from workhorse_workflows.coder.shared.resolution import RESOLVER_POWER, answered, resolver_args
from workhorse_workflows.coder.shared.story import resolve_workspace_dirs
from workhorse_workflows.coder.shared.schemas.ci import CiChecks, CiLoop, FixCiResult
from workhorse_workflows.coder.shared.schemas.dev import OperatorResolution
from workhorse_workflows.coder.shared.schemas.pr import MergeFixResult
from workhorse_workflows.coder.shared.schemas.render import schema_block
from workhorse_workflows.coder.shared.schemas.story import StoryPaths, WorkspaceDirs


class FixCi(Workflow):
    """Poll a PR's Actions runs, hand a red one to the CI owner, push, poll again, then merge."""

    repo: str = ""
    branch: str = ""
    pr_number: str = ""
    docs_path: str = ""
    workspace_file: str = ""
    operator_mode: str = "auto"
    base: str = ""

    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    def setup(self) -> WorkspaceDirs:
        """Every directory the owner may read: the workspace repos, plus the docs root."""
        return self.call(resolve_workspace_dirs, self.docs_path)

    def start(self, loop: CiLoop | None = None) -> Continue | Done:
        """Take the next repo whose CI has not been looked at, or finish."""
        lap = loop or CiLoop()
        pick = self.call(select_ci_repo, self.repo, lap.processed)
        if not pick.has_repo:
            if self.base:
                return Continue(pick, self.merge, loop=lap.model_copy(update={"merging": True}))
            return self._finish(lap, "no workspace repo left to check")
        self.logger.info("checking CI for %s in %s", self.branch, pick.repo)
        return Continue(
            pick,
            self.poll,
            loop=lap.model_copy(
                update={
                    "repo": pick.repo,
                    "repo_dir": pick.repo_cwd,
                    "processed": pick.processed,
                    "laps": 0,
                }
            ),
        )

    def poll(self, loop: CiLoop) -> Continue | Await:
        """Read this repo's CI before any agent turn, so a green branch costs none."""
        checks = self.call(poll_pr_checks, loop.repo_dir, self.branch, self.pr_number)
        return self._route(checks, loop, 0)

    def work(
        self, loop: CiLoop, report: str = "", operator_context: str = "", blocks: int = 0
    ) -> Continue | Await:
        """Run the owner turn: it diagnoses and fixes the red checks through its subagents."""
        self.logger.info(
            "the CI owner is on %s in %s", self.branch, loop.repo, extra={"activity": True}
        )
        turn = roles.turn(self, "fix-ci", returns=FixCiResult)
        result = self.agent(
            turn.prompt,
            returns=turn.returns,
            power="high",
            timeout=UNBOUNDED,
            silence=SILENCE_S,
            profile=owner_profile("ci"),
            session=self._session(loop.repo),
            cwd=loop.repo_dir,
            add_dirs=list(self.ctx.dirs),
            args=turn.args
            | {
                "ci_branch": self.branch,
                "ci_epic": epic_of_branch(self.branch),
                "report": report,
                "operator_context": operator_context,
            },
        )
        if result.blocked:
            return self._block(result, loop, result.notes, "the CI owner turn", blocks)
        return Continue(result, self.check, loop=loop, blocks=blocks)

    def check(self, loop: CiLoop, blocks: int = 0) -> Continue | Await:
        """Push the owner's commits, then wait for the run they trigger."""
        outcome = self.call(push_ci_fix, loop.repo_dir, self.branch)
        if outcome.status not in ("pushed", "unavailable"):
            notes = f"Could not push the fix for {self.branch} in {loop.repo}: {outcome.notes}"
            return self._block(outcome, loop, notes, "the push", blocks)
        checks = self.call(poll_pr_checks, loop.repo_dir, self.branch, self.pr_number)
        return self._route(checks, loop.model_copy(update={"laps": loop.laps + 1}), blocks)

    def merge(
        self, loop: CiLoop, operator_context: str = "", blocks: int = 0
    ) -> Continue | Await | Done:
        """Land the epic's PR once every repo is green, or hand the refusal to the merge turn."""
        epic = epic_of_branch(self.branch)
        outcome = self.call(merge_pr, epic, self.base)
        if outcome.merge_status in ("merged", "unavailable"):
            self.reset_session(self._merge_session())
            return self._finish(loop, f"merge {outcome.merge_status}")
        if loop.merges >= MAX_LAPS:
            notes = (
                f"`{epic}` still does not merge into `{self.base}` after "
                f"{loop.merges} attempt(s)."
            )
            return self._block(outcome, loop, notes, "the merge", blocks)
        return Continue(
            outcome, self.fix_merge, loop=loop, operator_context=operator_context, blocks=blocks
        )

    def fix_merge(
        self, loop: CiLoop, operator_context: str = "", blocks: int = 0
    ) -> Continue | Await:
        """Run the merge turn: it makes the branch merge cleanly, then CI is read again."""
        epic = epic_of_branch(self.branch)
        self.logger.info("resolving the merge for %s", epic, extra={"activity": True})
        result = self.agent(
            "fix_ci/prompts/fix-merge.md",
            returns=MergeFixResult,
            power="high",
            timeout=UNBOUNDED,
            silence=SILENCE_S,
            profile=owner_profile("ci"),
            session=self._merge_session(),
            add_dirs=list(self.ctx.dirs),
            args={
                "ci_epic": epic,
                "ci_branch": self.branch,
                "ci_base": self.base,
                "operator_context": operator_context,
                "result_schema": schema_block(MergeFixResult),
            },
        )
        if result.blocked:
            return self._block(result, loop, result.notes, "the merge turn", blocks)
        push = self.call(push_ci_fix, "", self.branch)
        if push.status not in ("pushed", "unavailable"):
            notes = f"Could not push the merge resolution for {self.branch}: {push.notes}"
            return self._block(push, loop, notes, "the push", blocks)
        return Continue(push, self.start, loop=CiLoop(merges=loop.merges + 1))

    def _route(self, checks: CiChecks, loop: CiLoop, blocks: int) -> Continue | Await:
        if checks.blocked:
            notes = f"Could not read CI for {self.branch} in {loop.repo}: {checks.summary}"
            return self._block(checks, loop, notes, "reading CI", blocks)
        lap = loop
        if checks.status == "unavailable":
            self.logger.warning(
                "no CI verdict for %s in %s (%s), moving on without one",
                self.branch, loop.repo, checks.summary,
            )
            lap = loop.model_copy(
                update={"unread": [*loop.unread, f"{loop.repo}: {checks.summary}"]}
            )
        if checks.status in ("passed", "unavailable"):
            self.reset_session(self._session(lap.repo))
            return Continue(checks, self.start, loop=lap)
        if lap.laps >= MAX_LAPS:
            notes = (
                f"CI is still red for {self.branch} in {lap.repo} after {lap.laps} "
                f"repair turn(s): {checks.summary}"
            )
            return self._block(checks, lap, notes, "the checks", blocks)
        return Continue(checks, self.work, loop=lap, report=checks.summary, blocks=blocks)

    def _block(
        self, result: object, loop: CiLoop, notes: str, where: str, blocks: int
    ) -> Continue | Await:
        if self.operator_mode in HUMAN_MODES or blocks >= MAX_BLOCKS:
            return self._ask(loop, notes, where, blocks)
        return Continue(result, self.resolve, loop=loop, notes=notes, where=where, blocks=blocks)

    def _ask(
        self,
        loop: CiLoop,
        notes: str,
        where: str,
        blocks: int,
        result: OperatorResolution | None = None,
    ) -> Await:
        if loop.merging:
            self.call(flag_merge_failure, epic_of_branch(self.branch), self.base, str(loop.merges))
        gate = escalation(
            self,
            block_kind="ci",
            where=where,
            notes=notes,
            number=blocks + 1,
            result=result,
            story=self._gate(),
        )
        return Await(
            context_path(self, self._gate().story_path),
            gate.body,
            self.read_operator,
            loop=loop,
            notes=notes,
            blocks=blocks + 1,
        )

    def resolve(self, loop: CiLoop, notes: str, where: str, blocks: int = 0) -> Continue | Await:
        """Answer a block from what is already written down, or ask the operator."""
        self.logger.info("resolving a block at %s", where, extra={"activity": True})
        result = self.agent(
            "shared/prompts/resolve-operator.md",
            returns=OperatorResolution,
            power=RESOLVER_POWER,
            timeout=UNBOUNDED,
            add_dirs=list(self.ctx.dirs),
            args=resolver_args(
                self, block_kind="ci", notes=notes, docs_path=self.docs_path, story=self._gate()
            ),
        )
        if answered(self, result, "ci"):
            return Continue(
                result, self.read_operator, loop=loop, notes=notes, blocks=blocks + 1
            )
        return self._ask(loop, notes, where, blocks, result)

    def read_operator(self, loop: CiLoop, notes: str = "", blocks: int = 0) -> Continue:
        """Resume the owner's session with the block, its answer and a fresh lap budget."""
        answer = self.call(read_operator_context, self._gate().story_path)
        if loop.merging:
            return Continue(
                answer,
                self.merge,
                loop=loop.model_copy(update={"merges": 0}),
                operator_context=answer.content,
                blocks=blocks,
            )
        return Continue(
            answer,
            self.work,
            loop=loop.model_copy(update={"laps": 0}),
            report=notes,
            operator_context=answer.content,
            blocks=blocks,
        )

    def _gate(self) -> StoryPaths:
        """Where this branch's CI gate lives, since a CI fix has no story folder to park in."""
        epic = epic_of_branch(self.branch)
        folder = paths.launch_repo_root(self.repo_dir) / paths.OPERATOR_DIR / "ci-fix"
        name = epic.replace("/", "-") or "unnamed-branch"
        return StoryPaths(
            story_path=str(folder / name / "gate.md"), story_slug=self.branch, story_epic=epic
        )

    def _session(self, repo: str) -> str:
        """The owner's conversation for one repo's CI on this branch."""
        return f"ci-fix:{self.branch}:{repo}"

    def _merge_session(self) -> str:
        """The merge turn's conversation for this epic."""
        return f"merge-fix:{epic_of_branch(self.branch)}"

    def _finish(self, loop: CiLoop, reason: str) -> Done:
        try:
            status = self.output(poll_pr_checks).status
        except NodeNotRunError:
            status = "unavailable"
        summary = reason
        if loop.unread:
            summary = f"{reason} (no CI verdict for {'; '.join(loop.unread)})"
        self.logger.info("CI fix loop finished: %s", summary)
        return Done(CiChecks(status=status, summary=summary))


__all__ = ["FixCi"]
