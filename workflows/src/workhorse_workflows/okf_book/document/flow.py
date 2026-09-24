"""Phase 2's first half: every file on the work list gets a contract before any page is written."""
from __future__ import annotations

import time

from workhorse.pyflow import Continue, Done
from workhorse_workflows.okf_book.shared.blockers import Blocker, Phase, Side, record_blocker
from workhorse_workflows.okf_book.shared.book_flow import BookFlow
from workhorse_workflows.okf_book.shared.contracts import ContractReply, contract_problems, save_contract
from workhorse_workflows.okf_book.shared.attempts import FailureTally, charge_failure, exhausted, last_problems
from workhorse_workflows.okf_book.document.nodes import check_vocabulary, entry_points, next_batch
from workhorse_workflows.okf_book.shared.metrics import TurnMetric, record_turn
from workhorse_workflows.okf_book.shared.work import BLOCKED, DONE, FILE


class Document(BookFlow):
    """Phase 2's document turns: a batch of files per turn, each file at most three turns."""

    def _pending(self) -> tuple[str, ...]:
        rows = self.work.items(FILE)
        return tuple(item.id for item in sorted(rows, key=lambda item: item.order or 0) if item.status not in (DONE, BLOCKED))

    def _block_file(self, file: str, reason: str) -> None:
        _ = record_blocker(self.records_dir, Blocker(subject=file, phase=Phase.DOCUMENT, side=Side.WORKFLOW, reason=reason))
        _ = self.work.mark(file, BLOCKED, FILE)

    def start(self) -> Continue[...]:
        """Start on the first batch."""
        return Continue(None, self.document_files)

    def document_files(self, attempts: tuple[FailureTally, ...] = ()) -> Continue[...] | Done:
        """One turn reads the next batch of files that fits and writes each one's contract."""
        pending = self._pending()
        if not pending:
            return Done(len(self.work.items(FILE)))
        batch = next_batch(self.root, pending, attempts)
        if batch.oversized_file:
            self._block_file(batch.oversized_file, f"{batch.oversized_file} is past what one turn can read. Split it.")
            return Continue(batch.oversized_file, self.document_files, attempts=attempts)
        entries = entry_points(self.root)
        started = time.monotonic()
        reply = self.agent(
            "document/prompts/document-files.md",
            returns=ContractReply,
            args={
                "files": [brief.template_arg() for brief in batch.briefs],
                "entry_points": list(entries.kept),
                "entry_points_left_out": entries.left_out,
                "checks": list(check_vocabulary()),
            },
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
        record_turn(self.records_dir, metric)
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
                _ = save_contract(self.records_dir, contract)
                _ = self.work.mark(file, DONE, FILE)
                continue
            attempts = charge_failure(attempts, file, problems)
            if exhausted(attempts, file):
                self._block_file(file, " ".join(last_problems(attempts, file)))
        return Continue(len(given), self.document_files, attempts=attempts)
