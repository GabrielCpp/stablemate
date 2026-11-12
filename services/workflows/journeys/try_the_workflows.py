from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from ..commands import DryRunAuthor, DryRunCoder, DryRunLoopRunner, DryRunOkfBook, DryRunResearch, DryRunReviewDebt, Look
from ..events import InstallSkills
from ..fixtures import dry_run


class TryTheWorkflows(Journey):
    """A person checks every workflow in a fresh repository before using it. The loop-runner, research, author and
    review-debt dry runs pass. The coder and okf-book dry runs are refused until the skills their prompts name are
    installed, and pass once they are. A dry run repeated writes the same run directory again."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            DryRunLoopRunner(dry_run()),
            DryRunResearch(dry_run()),
            DryRunAuthor(dry_run()),
            DryRunReviewDebt(dry_run()),
            DryRunCoder(dry_run()),
            DryRunOkfBook(dry_run()),
            InstallSkills(),
            DryRunCoder(dry_run()),
            DryRunOkfBook(dry_run()),
            DryRunLoopRunner(dry_run()),
            Look(),
        )
