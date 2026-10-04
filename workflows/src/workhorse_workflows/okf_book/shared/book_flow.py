"""The base every okf-book machine sits on: the repo it writes, the folder its records go in, and how it commits a book."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from workhorse.pyflow import AgentTimeout, AgentTurnFailed, Await, Transition, Workflow
from workhorse.runner.failure import OutputParseError
from workhorse_workflows.kit import commit_returning_refusal
from workhorse_workflows.okf_book.shared.agent_files import render_agent_files_returning_failure

COMMIT_GATE = "commit-refused.md"
RENDER_GATE = "agent-files-unrendered.md"
FIX_COMMIT_TIMEOUT = 1800.0


class CommitFix(BaseModel):
    """What the turn sent to a refused commit says it changed, or why it changed nothing."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    fixed: str = ""
    blocked: str = ""


class BookFlow(Workflow):
    """The base each machine's states sit on. A handed-off machine keeps its records in the folder of the run that started it."""

    parent_records_dir: str = ""

    @property
    def root(self) -> Path:
        return Path(self.repo_dir).resolve()

    @property
    def records_dir(self) -> Path:
        return Path(self.parent_records_dir) if self.parent_records_dir else self.run_dir

    def _render_agent_files_or_await[**P](self, retry: Callable[P, Transition], *args: P.args, **kwargs: P.kwargs) -> Await[P] | None:
        """Render the repo's agent files before a book commit, so a skill the library changed does not refuse it. A failed render waits for the operator, whose answer renders again."""
        failure = render_agent_files_returning_failure(self.root)
        if not failure:
            return None
        return Await(
            self.run_dir / RENDER_GATE,
            f"The repo's agent files could not be rendered before the book commit:\n\n{failure}\n\nFix it, then answer here to render them again.",
            retry,
            *args,
            **kwargs,
        ).because("the agent files could not be rendered")

    def _commit_or_await[**P](
        self, message: str, pathspecs: tuple[str, ...], retry: Callable[P, Transition], *args: P.args, **kwargs: P.kwargs
    ) -> Await[P] | None:
        """Commit exactly *pathspecs*. A commit the repo refused goes to one turn that fixes what the refusal names, and is tried again. A commit refused after that waits for the operator, whose answer commits again."""
        refusal = commit_returning_refusal(self.root, message, *pathspecs)
        if not refusal:
            return None
        said = self._fix_refused_commit(refusal, pathspecs)
        refusal = commit_returning_refusal(self.root, message, *pathspecs)
        if not refusal:
            return None
        return self._await_operator_on_refused_commit(f"{refusal}\n\n{said}" if said else refusal, retry, *args, **kwargs)

    def _fix_refused_commit(self, refusal: str, pathspecs: tuple[str, ...]) -> str:
        """One turn at the repo's root reads the refusal and fixes its cause. Returns what the turn said of it, for the operator a second refusal reaches."""
        try:
            fix = self.agent(
                "shared/prompts/fix-refused-commit.md",
                returns=CommitFix,
                timeout=FIX_COMMIT_TIMEOUT,
                args={"refusal": refusal, "paths": list(pathspecs)},
                cwd=self.root,
            )
        except (AgentTurnFailed, AgentTimeout, OutputParseError) as ended:
            self.logger.warning("the turn sent to a refused commit ended without a reply: %s", ended)
            return ""
        if fix.blocked:
            return f"A turn sent to fix it changed nothing: {fix.blocked}"
        return f"A turn sent to fix it said: {fix.fixed}" if fix.fixed else ""

    def _await_operator_on_refused_commit[**P](self, refusal: str, retry: Callable[P, Transition], *args: P.args, **kwargs: P.kwargs) -> Await[P]:
        """Stop at the operator when the repo refused a book commit. Their answer tries the same commit again."""
        return Await(
            self.run_dir / COMMIT_GATE,
            f"The repo refused the book commit:\n\n{refusal}\n\nFix what it names in the repo, then answer here to commit again.",
            retry,
            *args,
            **kwargs,
        ).because("the repo refused the commit")
