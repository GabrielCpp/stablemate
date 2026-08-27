"""The CI fix loop as a state machine: walk the workspace, get each epic branch green.

It is reached from the main graph's epic gate as a sub-flow handoff, and standalone as
`workhorse-coder run fix_ci`. Its job is to walk the workspace one repo at a time and, for
each, get the epic branch's CI green — or establish that it cannot be::

    (pick a repo → (poll → fix → push)* )*

Four states, and the two loops share them rather than nesting: `poll` returning to `start`
is the outer one advancing to the next repo, and `push` returning to `poll` is the inner
one re-reading CI after a fix. What each lap carries is one `CiLoop` value.

**The repo is a parameter, not the process's cwd.** A driver state has no per-node cwd, so
the directory arrives as `repo_dir`. The agent turn still takes a real `cwd`, because there
the working directory decides which flavor prompt and which `CLAUDE.md` the turn sees; that
is a genuine use of it, not a path-resolution workaround.

**Every exit is a `Done`, except an unreadable CI.** A branch left red, a fixer that says it
cannot help, a push that will not land — each of those ends this loop and hands the last CI
verdict back, because the caller re-gates: `Coder.ci` polls the same PR again and parks on
`_ci_gate`, an operator `Await`, when it is still not green. Ending here in `WorkflowFailed`
would take that gate away rather than add anything to it. The exception is CI that could
not be *read* — a token GitHub will not accept, a repository the API will not open. No lap
of this loop repairs a credential, the poll it would re-run is the one that just failed, and
the alternative is the silence this loop was built to stop: an ungated branch reported the
same as a green one.
"""
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

    #: An explicit workspace repo key. Empty iterates every workspace repo in order.
    repo: str = ""
    #: The full branch name (e.g. `feat/EPIC-X`). Nothing to gate on without it.
    branch: str = ""
    #: A PR number, pinning the poll to one PR. Empty resolves by branch name, which a
    #: branch that has carried more than one PR can resolve wrongly.
    pr_number: str = ""
    #: The docs repo root, prepended to the fixer's readable directories. Empty walks up
    #: from `repo_dir`.
    docs_path: str = ""
    #: The `.code-workspace` manifest naming this run's repos. Empty falls back to the
    #: single checkout at `repo_dir` — a one-repo run needs no manifest.
    workspace_file: str = ""


    #: The ambient path inputs — `repo_dir`, `docs_path`, `workspace_file`. The seams
    #: fill each one in for any node or sub-flow that declares a parameter of the same
    #: name and was not passed one; see `Workflow.injects`.
    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    #: `fix → push → poll` cycles before the loop gives up, across every repo.
    #: `ClassVar` because `Workflow` is a pydantic model and every annotated class
    #: attribute is otherwise an operator-settable input; a budget the flow owns is not one.
    MAX_ATTEMPTS: ClassVar[int] = 3

    def setup(self) -> WorkspaceDirs:
        """Every directory the fixer may read: the workspace repos, plus the docs root.

        `setup` rather than a state because nothing decides on it — it is read once, by the
        agent turn, as `add_dirs` — and because a resume should not re-derive the workspace
        it was already driving against.

        The node is the story spine's `resolve_workspace_dirs`, which carries
        `resolve_ci_workspace` as an alias: this flow called the same body under that name
        before `dev` needed it too, and the alias is what keeps an in-flight run resumable
        across the rename.
        """
        return self.call(resolve_workspace_dirs, self.docs_path)

    def start(self, loop: CiLoop | None = None) -> Continue | Done:
        """Take the next repo whose CI has not been looked at, or finish.

        A repo joins `processed` the moment it is *picked* rather than when its CI settles,
        so a repo that exhausts the fix budget is still not revisited — which is what makes
        the outer loop terminate.
        """
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
        """Block until this repo's Actions runs settle, then route on the verdict.

        `unavailable` moves on with `passed`: a repo with no pipeline, no open PR or no
        origin is not evidence of a broken branch, and sending a fixer at it would give it
        nothing to fix. It is recorded on the lap rather than forgotten, so the closing line
        names the repos this loop never actually gated. `blocked` — CI that exists and could
        not be read — is the one verdict that ends the run; see the module docstring.
        """
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
            # This repo is settled; the next one round the loop has its own failures.
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
        """Diagnose the failing checks and commit a fix on the branch.

        A state of its own, holding nothing but the turn: it is the expensive thing in the
        loop and the checkpoint is written before a state runs, so leaving the push
        downstream is what makes a resume cheap.

        `cwd` is the picked repo, which is what lets workhorse resolve a repo-specific
        flavor override from `<repo>/.agents/flavors/coder/fix-ci.md`. It does **not**
        push: `push` below does, so credential handling stays in one place.

        The branch and the epic are separate arguments because the prompt needs both and
        they are not interchangeable: the ref to stay on is `feat/<epic>`, the `Epic:`
        trailer is `<epic>`. One argument standing in for both is what put `feat/feat/`
        into the branch line and a ref into the trailer of every CI-fix commit.
        """
        turn = roles.turn(self, "fix-ci", returns=FixCiResult)
        result = self.agent(
            turn.prompt,
            # medium: reads failing job logs and the diff, and makes a narrow repair —
            # bounded diagnosis rather than design.
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
            # Nothing this repo contains would make the checks green, so the remaining
            # attempts would each re-ask a turn that has already answered. Ending here is
            # the same ending the budget's own arm takes, minus the laps: the branch is
            # left red and the caller's gate is what an operator meets it at.
            self.reset_session(self._session(loop.repo))
            return self._finish(
                loop,
                f"the CI fixer reported it cannot make {self.branch} green in {loop.repo}: "
                f"{result.notes}",
            )
        return Continue(result, self.push, loop=loop)

    def push(self, loop: CiLoop) -> Continue | Done:
        """Push the fix so GitHub triggers a new run, then poll again.

        A fix that cannot be pushed can never turn CI green, so a `failed` push ends the
        loop for this repo rather than spending another attempt polling an unmoved PR head.
        `unavailable` continues, so an offline run still reaches the poll that records the
        pass-through.
        """
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
        """The fixer's conversation for one repo's CI on this branch.

        One chain per repo per branch: attempt two is this repo's CI still red after attempt
        one's push, and the turn that wrote that push knows which theory it was testing. A
        different repo's failures are a different worklist.

        A method rather than a literal at each of the five sites that need it — the turn
        that opens it and the four exits that close it — because four of those are `reset`s
        and a reset that spells the key differently resets nothing.
        """
        return f"ci-fix:{self.branch}:{repo}"

    def _finish(self, loop: CiLoop, reason: str) -> Done:
        """The one terminal, reached from four places.

        What is handed back is the last CI verdict the loop actually read, with `reason` as
        its summary, because that is the most informative thing available at any of the
        exits. Before the first poll there is none, and "we never got as far as looking" is
        `unavailable`. Any repo that was walked past ungated is named after it, so a caller
        reading a settled-looking result can still see what was never checked.
        """
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
