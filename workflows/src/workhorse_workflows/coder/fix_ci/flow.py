"""The CI fix loop as a state machine: walk the workspace, get each epic branch green."""
from __future__ import annotations

from typing import ClassVar

from workhorse.pyflow import Continue, Done, NodeNotRunError, Workflow, WorkflowFailed
from workhorse_workflows.coder.shared import paths, roles
from workhorse_workflows.coder.shared.ci import (
    branch_epic,
    poll_pr_checks,
    push_ci_fix,
    select_ci_repo,
)
from workhorse_workflows.coder.shared.story import resolve_workspace_dirs
from workhorse_workflows.coder.shared.schemas.ci import CiChecks, CiLoop, FixCiResult
from workhorse_workflows.coder.shared.schemas.story import WorkspaceDirs


class FixCi(Workflow):
    """Poll a PR's Actions runs, hand a failure to a fixer, push, poll again."""

    repo: str = ""
    branch: str = ""
    pr_number: str = ""
    docs_path: str = ""
    workspace_file: str = ""


    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    MAX_ATTEMPTS: ClassVar[int] = 3

    def setup(self) -> WorkspaceDirs:
        """Every directory the fixer may read: the workspace repos, plus the docs root."""
        return self.call(resolve_workspace_dirs, self.docs_path)

    def start(self, loop: CiLoop | None = None) -> Continue | Done:
        """Take the next repo whose CI has not been looked at, or finish."""
        lap = loop or CiLoop()
        pick = self.call(select_ci_repo, self.repo, lap.processed)
        if not pick.has_repo:
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
                }
            ),
        )

    def poll(self, loop: CiLoop) -> Continue | Done:
        """Block until this repo's Actions runs settle, then route on the verdict."""
        checks = self.call(poll_pr_checks, loop.repo_dir, self.branch, self.pr_number)
        if checks.blocked:
            raise WorkflowFailed(
                f"could not read CI for {self.branch} in {loop.repo}: {checks.summary}"
            )
        lap = loop
        if checks.status == "unavailable":
            self.logger.warning(
                "no CI verdict for %s in %s (%s) — moving on without one",
                self.branch, loop.repo, checks.summary,
            )
            lap = loop.model_copy(
                update={"unread": [*loop.unread, f"{loop.repo}: {checks.summary}"]}
            )
        if checks.status in ("passed", "unavailable"):
            self.reset_session(self._session(lap.repo))
            return Continue(checks, self.start, loop=lap)
        if lap.attempts >= self.MAX_ATTEMPTS:
            self.reset_session(self._session(lap.repo))
            return self._finish(
                lap,
                f"CI still red for {self.branch} in {lap.repo} after {lap.attempts} "
                f"attempt(s): {checks.summary}",
            )
        return Continue(checks, self.fix, loop=lap, summary=checks.summary)

    def fix(self, loop: CiLoop, summary: str) -> Continue | Done:
        """Diagnose the failing checks and commit a fix on the branch."""
        turn = roles.turn(self, "fix-ci", returns=FixCiResult)
        result = self.agent(
            turn.prompt,
            power="medium",
            returns=turn.returns,
            cwd=loop.repo_dir,
            add_dirs=list(self.ctx.dirs),
            args=turn.args
            | {
                "ci_branch": self.branch,
                "ci_epic": branch_epic(self.branch),
                "ci_summary": summary,
            },
            session=self._session(loop.repo),
        )
        if result.blocked:
            self.reset_session(self._session(loop.repo))
            return self._finish(
                loop,
                f"the CI fixer reported it cannot make {self.branch} green in {loop.repo}: "
                f"{result.notes}",
            )
        return Continue(result, self.push, loop=loop)

    def push(self, loop: CiLoop) -> Continue | Done:
        """Push the fix so GitHub triggers a new run, then poll again."""
        outcome = self.call(push_ci_fix, loop.repo_dir, self.branch)
        if outcome.status not in ("pushed", "unavailable"):
            self.reset_session(self._session(loop.repo))
            return self._finish(
                loop, f"could not push the fix for {self.branch} in {loop.repo}"
            )
        return Continue(
            outcome, self.poll, loop=loop.model_copy(update={"attempts": loop.attempts + 1})
        )

    def _session(self, repo: str) -> str:
        """The fixer's conversation for one repo's CI on this branch."""
        return f"ci-fix:{self.branch}:{repo}"

    def _finish(self, loop: CiLoop, reason: str) -> Done:
        """The one terminal, reached from four places."""
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
