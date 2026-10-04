"""Regrounding a book whose cited code changed: each changed file is read once, as its diff from the version the book was stamped on, before any page is repaired.

A run of the book against the app proves the claims a scenario checks, and no others. A page
whose cited file changed since its stamp may claim what the code no longer does, and nothing
else in the run reads it again. One turn per changed file names the nodes the change bears on.
Those reach a page repair with what the turn said, and every other citation of the file is
stamped on the file as it is now. The turn changes no file: code puts back what it wrote.
"""
from __future__ import annotations

import time
from pathlib import Path

from workhorse.pyflow import AgentTimeout, AgentTurnFailed, Await, Continue, Done
from workhorse.runner.backends import AgentProfile
from workhorse.runner.failure import OutputParseError
from workhorse_workflows.okf_book.main.nodes.stale_citations import (
    Failures,
    Regrounded,
    RegroundVerdict,
    StaleFile,
    affected_problems,
    keep_old_version,
    reground_template_args,
    spared_pairs,
    stale_files,
    stamp_spared,
    stamped_text,
    unread_problems,
    with_problems,
)
from workhorse_workflows.okf_book.shared.blockers import Phase
from workhorse_workflows.okf_book.shared.book_commits import repaired_book_commit_message
from workhorse_workflows.okf_book.shared.book_flow import BookFlow
from workhorse_workflows.okf_book.shared.confine import changed_since, restore, snapshot
from workhorse_workflows.okf_book.shared.metrics import record_turn, turn_metric

REGROUND_PROMPT = "main/prompts/reground-file.md"
REGROUND_PROFILE = AgentProfile(name="okf-book-reground", confined=True)
REGROUND_TIMEOUT = 900.0
RESTAMP_DESCRIPTION = "restamp the citations a code change spares"

type Pairs = tuple[tuple[str, str], ...]


class RegroundBook(BookFlow):
    """Reads each changed file a book cites, and ends on the page problems of the nodes a change bears on."""

    service: str = ""

    def start(self) -> Continue[...]:
        """List the changed files the book cites, each with the nodes citing it."""
        files = stale_files(self.root, self.service)
        return Continue(len(files), self.read_change, files=files).because("read each changed file the book cites")

    def read_change(
        self, files: tuple[StaleFile, ...], position: int = 0, failures: Failures | None = None, spared: Pairs = (),
    ) -> Continue[...]:
        """Read one changed file. A file whose stamped version no commit holds sends every node citing it to its page repair, and a turn that ends without a verdict leaves its citations as they are."""
        kept = failures or {}
        if position >= len(files):
            return Continue(len(spared), self.stamp_spared_citations, failures=kept, spared=spared).because("every changed file is read: stamp what the changes spare")
        stale = files[position]
        if not (self.root / stale.path).is_file():
            return Continue(stale.path, self.read_change, files=files, position=position + 1, failures=kept, spared=spared).because(
                "the cited file is gone, which the page check reports"
            )
        old = stamped_text(self.root, stale.path, stale.digest)
        if old is None:
            kept = with_problems(kept, unread_problems(stale))
            return Continue(stale.path, self.read_change, files=files, position=position + 1, failures=kept, spared=spared).because(
                "no commit holds the stamped version: every citing node is read again"
            )
        verdict = self._verdict(stale, old)
        if verdict is not None:
            kept = with_problems(kept, affected_problems(stale, verdict))
            spared = (*spared, *spared_pairs(stale, verdict))
        return Continue(stale.path, self.read_change, files=files, position=position + 1, failures=kept, spared=spared).because(
            "the next changed file"
        )

    def _verdict(self, stale: StaleFile, old: str) -> RegroundVerdict | None:
        before = snapshot(self.root)
        started = time.monotonic()
        verdict: RegroundVerdict | None = None
        try:
            verdict = self.agent(
                REGROUND_PROMPT,
                returns=RegroundVerdict,
                timeout=REGROUND_TIMEOUT,
                args=reground_template_args(self.root, stale, old, keep_old_version(self.root, stale, old)),
                cwd=self.root,
                profile=REGROUND_PROFILE,
            )
        except (AgentTurnFailed, AgentTimeout, OutputParseError) as ended:
            self.logger.warning("the reading of %s ended without a verdict: %s", stale.path, ended)
        _ = restore(self.root, changed_since(self.root, before), before)
        node = Path(REGROUND_PROMPT).stem
        record_turn(self.records_dir, turn_metric(Phase.WRITE, node, (stale.path,), (time.monotonic() - started) / 60, self.turn_usage(node)))
        return verdict

    def stamp_spared_citations(self, failures: Failures, spared: Pairs = ()) -> Continue[...]:
        """Stamp each citation its file's change spares on the file as it is now."""
        pages, stamped = stamp_spared(self.root, spared)
        return Continue(stamped, self.commit_stamps, failures=failures, pages=pages, stamped=stamped).because("commit the stamped pages")

    def commit_stamps(self, failures: Failures, pages: tuple[str, ...] = (), stamped: int = 0) -> Await[...] | Done:
        """Commit the pages whose stamps changed. A commit the repo refused waits for the operator."""
        if pages:
            message = repaired_book_commit_message(self.service, RESTAMP_DESCRIPTION)
            waiting = self._commit_or_await(message, pages, self.commit_stamps, failures=failures, pages=pages, stamped=stamped)
            if waiting is not None:
                return waiting
        return Done(Regrounded(failures=failures, stamped=stamped)).because("the book is stamped on the code it cites, but the nodes a change bears on")
