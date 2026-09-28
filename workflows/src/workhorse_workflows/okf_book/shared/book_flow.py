"""The base every okf-book machine sits on: the repo it writes, the folder its records go in, and how it commits a book."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from workhorse.pyflow import Await, Transition, Workflow
from workhorse_workflows.kit import commit_returning_refusal
from workhorse_workflows.okf_book.shared.agent_files import render_agent_files

COMMIT_GATE = "commit-refused.md"


class BookFlow(Workflow):
    """The base each machine's states sit on. A handed-off machine keeps its records in the folder of the run that started it."""

    parent_records_dir: str = ""

    @property
    def root(self) -> Path:
        return Path(self.repo_dir).resolve()

    @property
    def records_dir(self) -> Path:
        return Path(self.parent_records_dir) if self.parent_records_dir else self.run_dir

    def _commit(self, message: str, *pathspecs: str) -> str:
        """Render the repo's agent files, then commit exactly *pathspecs*. Returns what the repo said when it refused, and empty when it did not."""
        render_agent_files(self.root, self.logger)
        return commit_returning_refusal(self.root, message, *pathspecs)

    def _await_operator_on_refused_commit[**P](self, refusal: str, retry: Callable[P, Transition], *args: P.args, **kwargs: P.kwargs) -> Await[P]:
        """Stop at the operator when the repo refused a book commit. Their answer tries the same commit again."""
        return Await(
            self.run_dir / COMMIT_GATE,
            f"The repo refused the book commit:\n\n{refusal}\n\nFix what it names in the repo, then answer here to commit again.",
            retry,
            *args,
            **kwargs,
        ).because("the repo refused the commit")
