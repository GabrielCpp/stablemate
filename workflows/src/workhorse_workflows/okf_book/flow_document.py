"""Phase 2's first half: every file in the work set gets a contract before any page is written."""
from __future__ import annotations

import time

from workhorse.pyflow import Continue
from workhorse_workflows.okf_book.blockers import Blocker, Phase, Side, read_blockers, record_blocker
from workhorse_workflows.okf_book.contracts import ContractReply, contract_problems, read_contract, save_contract
from workhorse_workflows.okf_book.attempts import FailureTally, charge_failure, exhausted, last_problems
from workhorse_workflows.okf_book.document import check_vocabulary, next_batch
from workhorse_workflows.okf_book.flow_aggregate import Aggregate
from workhorse_workflows.okf_book.metrics import TurnMetric, record_turn


class Document(Aggregate):
    """Phase 2's document turns: a batch of files per turn, each file at most three turns, then aggregation."""

    def _pending(self) -> tuple[str, ...]:
        blocked = {b.subject for b in read_blockers(self.run_dir) if b.phase is Phase.DOCUMENT}
        return tuple(
            file for file in self.work_set.files
            if file not in blocked and read_contract(self.run_dir, file) is None
        )

    def _block_file(self, file: str, reason: str) -> None:
        _ = record_blocker(self.run_dir, Blocker(subject=file, phase=Phase.DOCUMENT, side=Side.WORKFLOW, reason=reason))

    def document_files(self, attempts: tuple[FailureTally, ...] = ()) -> Continue[...]:
        """One turn reads the next batch of files that fits and writes each one's contract."""
        pending = self._pending()
        if not pending:
            return Continue(None, self.aggregate)
        batch = next_batch(self.root, pending, attempts)
        if batch.oversized_file:
            self._block_file(batch.oversized_file, f"{batch.oversized_file} is past what one turn can read. Split it.")
            return Continue(batch.oversized_file, self.document_files, attempts=attempts)
        started = time.monotonic()
        reply = self.agent(
            "prompts/document-files.md",
            returns=ContractReply,
            args={"files": [brief.template_arg() for brief in batch.briefs], "checks": list(check_vocabulary())},
            cwd=self.root,
        )
        metric = TurnMetric(
            phase=Phase.DOCUMENT,
            node="document-files",
            subjects=batch.files,
            tokens=batch.tokens,
            minutes=(time.monotonic() - started) / 60,
        )
        return Continue(reply, self.record_document, files=batch.files, reply=reply, attempts=attempts, metric=metric)

    def record_document(
        self, files: tuple[str, ...], reply: ContractReply, attempts: tuple[FailureTally, ...], metric: TurnMetric
    ) -> Continue[...]:
        """Record the document turn before any contract it wrote is judged."""
        record_turn(self.run_dir, metric)
        return Continue(metric, self.accept_contracts, files=files, reply=reply, attempts=attempts)

    def accept_contracts(
        self, files: tuple[str, ...], reply: ContractReply, attempts: tuple[FailureTally, ...]
    ) -> Continue[...]:
        """Save each contract the file grounds, and charge every other file of the batch one failed turn."""
        given = {contract.file: contract for contract in reply.contracts if contract.file in files}
        for file in files:
            contract = given.get(file)
            problems = contract_problems(self.root, contract) if contract else (f"The reply had no contract for {file}.",)
            if contract and not problems:
                _ = save_contract(self.run_dir, contract)
                continue
            attempts = charge_failure(attempts, file, problems)
            if exhausted(attempts, file):
                self._block_file(file, " ".join(last_problems(attempts, file)))
        return Continue(len(given), self.document_files, attempts=attempts)
