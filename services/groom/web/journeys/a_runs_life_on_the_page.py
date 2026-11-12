from datetime import date

from ostler.book import Journey

from ...fixtures import running
from ..interactions import ReportExit, ReportGate, ReportProgress


class ARunsLifeOnThePage(Journey):
    """A workflow starts, asks an operator a question and exits while the dashboard is open.
    The list shows the run each time it speaks: running, blocked on a gate, then ended."""

    def steps(self, today: date):
        run = running()
        yield ReportProgress(run.but(repo_name="shop", repo_branch="main", current_node="plan"))
        yield ReportGate(run.but(file_path="gates/approve.md", question="Ship it?"))
        yield ReportProgress(run.but(current_node="build"))
        yield ReportExit(run.but(exit_code=0))
