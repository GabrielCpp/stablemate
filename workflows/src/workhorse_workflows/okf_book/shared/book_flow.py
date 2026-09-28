"""The base every okf-book machine sits on: the repo it writes, the folder its records go in, and how it commits a book."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from workhorse.pyflow import Await, Transition, Workflow
from workhorse_workflows.kit import commit_returning_refusal
from workhorse_workflows.okf_book.shared.agent_files import render_agent_files_returning_failure

COMMIT_GATE = "commit-refused.md"
RENDER_GATE = "agent-files-unrendered.md"


class BookFlow(Workflow):
    """The base each machine's states sit on. A handed-off machine keeps its records in the folder of the run that started it."""

    parent_records_dir: str = ""

    @property
    def root(self) -> Path:
        return Path(self.repo_dir).resolve()

    @property
    def records_dir(self) -> Path:
        return Path(self.parent_records_dir) if self.parent_records_dir else self.run_dir

    def _render_and_commit_or_await[**P](
        self, message: str, pathspecs: tuple[str, ...], retry: Callable[P, Transition], *args: P.args, **kwargs: P.kwargs
    ) -> Await[P] | None:
        """Render the repo's agent files, then commit exactly *pathspecs*. A render that failed or a commit the repo refused waits for the operator, whose answer tries the whole step again."""
        render_failure = render_agent_files_returning_failure(self.root)
        if render_failure:
            return Await(
                self.run_dir / RENDER_GATE,
                f"The repo's agent files could not be rendered before the book commit:\n\n{render_failure}\n\nFix it, then answer here to render and commit again.",
                retry,
                *args,
                **kwargs,
            ).because("the agent files could not be rendered")
        refusal = commit_returning_refusal(self.root, message, *pathspecs)
        if refusal:
            return self._await_operator_on_refused_commit(refusal, retry, *args, **kwargs)
        return None

    def _await_operator_on_refused_commit[**P](self, refusal: str, retry: Callable[P, Transition], *args: P.args, **kwargs: P.kwargs) -> Await[P]:
        """Stop at the operator when the repo refused a book commit. Their answer tries the same commit again."""
        return Await(
            self.run_dir / COMMIT_GATE,
            f"The repo refused the book commit:\n\n{refusal}\n\nFix what it names in the repo, then answer here to commit again.",
            retry,
            *args,
            **kwargs,
        ).because("the repo refused the commit")
