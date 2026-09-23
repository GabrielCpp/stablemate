"""Phase 2's aggregation once a job's turn fails: write again, or after three failures put the book back and block the job."""
from __future__ import annotations

from workhorse.pyflow import Continue
from workhorse_workflows.okf_book.attempts import JobLedger
from workhorse_workflows.okf_book.blockers import Blocker, Phase, Side, record_blocker
from workhorse_workflows.okf_book.confine import revert
from workhorse_workflows.okf_book.flow_collect import Collect
from workhorse_workflows.okf_book.settled import settle_job


class Retry(Collect):
    """A failed job is written again with its problems, until its third failure hands it to the operator."""

    def _rewrite(self, ledger: JobLedger) -> Continue[...]:
        raise NotImplementedError

    def _retry(self, ledger: JobLedger) -> Continue[...]:
        if ledger.exhausted:
            return Continue(ledger.attempts, self.abandon_job, ledger=ledger)
        return self._rewrite(ledger)

    def abandon_job(self, ledger: JobLedger) -> Continue[...]:
        """Three failed turns: put the book back as it was."""
        reverted = revert(self.root, ledger.before, self.run_dir)
        return Continue(reverted, self.block_job, ledger=ledger)

    def block_job(self, ledger: JobLedger) -> Continue[...]:
        """Hand the abandoned job to the operator, and settle it as put back so no later turn reopens it."""
        reason = " ".join(ledger.problems)
        _ = record_blocker(self.run_dir, Blocker(subject=ledger.job.subject, phase=Phase.AGGREGATE, side=Side.BOOK, reason=reason))
        settle_job(self.run_dir, ledger.job, committed=False)
        return self._next_job(ledger.job.subject)
