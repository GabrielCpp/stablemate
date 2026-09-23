"""Phase 2's second half: write each page from the contracts that reach it, check it, and have it judged."""
from __future__ import annotations

import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from workhorse.pyflow import Continue
from workhorse_workflows.okf_book.blockers import Phase, read_blockers
from workhorse_workflows.okf_book.budget import (
    PROBLEMS_BUDGET_TOKENS,
    TURN_BUDGET_TOKENS,
    estimated_tokens,
    file_tokens,
    name_tokens,
    pack_problems,
    pack_read,
    pack_told,
    page_bodies,
    prompt_tokens,
    total_text_tokens,
)
from workhorse_workflows.okf_book.attempts import JobLedger
from workhorse_workflows.okf_book.check_pages import CHECK_RUNS, check_command, waived_path, write_waived
from workhorse_workflows.okf_book.citations import book_pages
from workhorse_workflows.okf_book.confine import (
    book_changes,
    confine,
    judged_pages,
    new_since_head,
    snapshot,
)
from workhorse_workflows.okf_book.contracts import Contract
from workhorse_workflows.okf_book.garbage import delete_book_pages
from workhorse_workflows.okf_book.job_inputs import job_contracts, job_stories
from workhorse_workflows.okf_book.flow_retry import Retry
from workhorse_workflows.okf_book.jobs import freeze_queue, listed_pages, service_folder
from workhorse_workflows.okf_book.metrics import TurnMetric, record_turn
from workhorse_workflows.okf_book.page_kinds import JobKind
from workhorse_workflows.okf_book.page_check import inherited_gaps, page_problems, unreached, unreached_problems
from workhorse_workflows.okf_book.settled import next_job

PAGES_BUDGET_TOKENS = 3_000
VERIFY_PROMPT = "prompts/verify-page.md"
UNJUDGED_PROBLEM = "The changed pages are too large for any turn to judge. Split the page, or cut what it repeats."
WRITE_PROMPTS = {
    JobKind.PAGE: "prompts/write-page.md",
    JobKind.OPERATIONS: "prompts/write-operations.md",
    JobKind.FLOWS: "prompts/write-flows.md",
}


class Written(BaseModel):
    """A writing turn's account of what it changed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    summary: str


class Verdict(BaseModel):
    """A later turn's judgement of the pages another turn wrote."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    passed: bool
    problems: tuple[str, ...] = ()


def _turn_metric(node: str, subject: str, tokens: int, started: float) -> TurnMetric:
    minutes = (time.monotonic() - started) / 60
    return TurnMetric(phase=Phase.AGGREGATE, node=node, subjects=(subject,), tokens=tokens, minutes=minutes)


def _book_pages_besides(root: Path, service: str, judged: tuple[str, ...]) -> tuple[str, ...]:
    rels = (page.relative_to(root).as_posix() for page in book_pages(root, service))
    return tuple(rel for rel in rels if rel not in judged)


def _contract_args(contracts: tuple[Contract, ...]) -> list[dict[str, object]]:
    return [contract.model_dump() for contract in contracts]


def _contract_tokens(contracts: tuple[Contract, ...]) -> int:
    return estimated_tokens(sum(len(c.model_dump_json()) for c in contracts))


class Aggregate(Retry):
    """Phase 2's aggregation: one job at a time, nearest the root first, until none is left, then phase 3."""

    def aggregate(self) -> Continue[...]:
        """Take the next unsettled job of the queue frozen at the start. With none left, phase 3 starts."""
        skip = {b.subject for b in read_blockers(self.run_dir) if b.phase is Phase.AGGREGATE}
        queue = freeze_queue(self.root, self.run_dir, self.work_set.services)
        job = next_job(self.run_dir, queue, skip)
        if job is None:
            return Continue(None, self.bring_up)
        gaps = inherited_gaps(self.root, job.service, job.owned_pages)
        _ = write_waived(self.run_dir, gaps)
        ledger = JobLedger(job=job, before=snapshot(self.root), inherited_gaps=gaps)
        return Continue(job, self.write_job, ledger=ledger)

    def _rewrite(self, ledger: JobLedger) -> Continue[...]:
        return Continue(ledger.attempts, self.write_job, ledger=ledger)

    def _next_job(self, result: object) -> Continue[...]:
        return Continue(result, self.aggregate)

    def write_job(self, ledger: JobLedger) -> Continue[...]:
        """One turn writes the job's pages from the contracts that reach them, and the last check's problems.

        The prompt, the pages list, the problems and the stories are sized first. The contracts get what is left.
        """
        root, job = self.root, ledger.job
        pages = pack_told(name_tokens(listed_pages(root, job)), PAGES_BUDGET_TOKENS)
        problems = pack_problems(ledger.problems)
        stories = job_stories(root, job)
        told = pages.tokens + problems.tokens + CHECK_RUNS * PROBLEMS_BUDGET_TOKENS
        fixed = prompt_tokens(WRITE_PROMPTS[job.kind]) + told + total_text_tokens(stories)
        contracts = job_contracts(root, self.run_dir, job, budget=TURN_BUDGET_TOKENS - fixed)
        started = time.monotonic()
        written = self.agent(
            "prompts/write-page.md" if job.kind is JobKind.PAGE
            else "prompts/write-operations.md" if job.kind is JobKind.OPERATIONS
            else "prompts/write-flows.md",
            returns=Written,
            args={
                "service": job.service,
                "folder": service_folder(job.service),
                "page": job.page,
                "pages": list(pages.kept),
                "contracts": _contract_args(contracts),
                "stories": list(stories),
                "problems": list(problems.kept),
                "check": check_command(job.service, waived_path(self.run_dir)),
                "check_runs": CHECK_RUNS,
            },
            cwd=root,
        )
        metric = _turn_metric(f"write-{job.kind.value}", job.subject, fixed + _contract_tokens(contracts), started)
        return Continue(written, self.record_write, ledger=ledger, metric=metric)

    def record_write(self, ledger: JobLedger, metric: TurnMetric) -> Continue[...]:
        """Record the writing turn before anything it changed is put back."""
        record_turn(self.run_dir, metric)
        return Continue(metric, self.confine_job, ledger=ledger)

    def confine_job(self, ledger: JobLedger) -> Continue[...]:
        """Put back what the writing turn may not change."""
        confined = confine(self.root, ledger.job, ledger.before, self.run_dir)
        if confined.put_back:
            self.logger.warning("restored %d paths the turn may not change: %s", len(confined.put_back), confined.put_back)
        return Continue(confined.kept, self.pick_unreached, ledger=ledger, kept=confined.kept)

    def pick_unreached(self, ledger: JobLedger, kept: tuple[str, ...]) -> Continue[...]:
        """Pick each page the turn wrote new that nothing reaches. A committed page it only added to is left for garbage collection."""
        dead = tuple(page.rel for page in unreached(self.root, new_since_head(self.root, kept)))
        return Continue(dead, self.delete_unreached, ledger=ledger, dead=dead)

    def delete_unreached(self, ledger: JobLedger, dead: tuple[str, ...]) -> Continue[...]:
        """Delete the picked pages. A retry deletes the same list, and skips each page already gone."""
        delete_book_pages(self.root, dead)
        return Continue(dead, self.check_job, ledger=ledger, deleted=dead)

    def check_job(self, ledger: JobLedger, deleted: tuple[str, ...]) -> Continue[...]:
        """Charge the turn with each page deleted as unreachable, and each doctor error and compile gap on the rest."""
        changed = book_changes(self.root, ledger.job.service, ledger.before)
        problems = (*unreached_problems(deleted), *page_problems(self.root, ledger.job.service, changed, ledger.inherited_gaps))
        if problems:
            return self._retry(ledger.charged(problems))
        return Continue(changed, self.verify_job, ledger=ledger)

    def verify_job(self, ledger: JobLedger) -> Continue[...]:
        """A turn that wrote none of the pages judges them against the contracts they were written from.

        The job's own pages come first, and the pages take up to half of what the prompt leaves. A first page over that goes alone,
        and the contracts get the rest. A page past the ceiling cannot be judged, and charges the job a turn.
        """
        root, job = self.root, ledger.job
        judged_rels = judged_pages(root, job, ledger.before)
        other_pages = pack_told(name_tokens(_book_pages_besides(root, job.service, judged_rels)), PAGES_BUDGET_TOKENS)
        fixed = prompt_tokens(VERIFY_PROMPT) + other_pages.tokens
        judged = pack_read(file_tokens(root, judged_rels), (TURN_BUDGET_TOKENS - fixed) // 2)
        if not judged.kept:
            return self._retry(ledger.charged((UNJUDGED_PROBLEM,)))
        if judged.left_out:
            self.logger.warning("%d changed pages are past the verify turn's budget and go unjudged", judged.left_out)
        contracts = job_contracts(root, self.run_dir, job, budget=TURN_BUDGET_TOKENS - fixed - judged.tokens)
        started = time.monotonic()
        verdict = self.agent(
            "prompts/verify-page.md",
            returns=Verdict,
            args={
                "pages": [body.template_arg() for body in page_bodies(root, judged.kept)],
                "contracts": _contract_args(contracts),
                "other_pages": list(other_pages.kept),
                "other_pages_left_out": other_pages.left_out,
                "kind": job.kind.value,
            },
            cwd=root,
        )
        metric = _turn_metric("verify-page", job.subject, fixed + judged.tokens + _contract_tokens(contracts), started)
        return Continue(verdict, self.settle_verdict, ledger=ledger, verdict=verdict, metric=metric)

    def settle_verdict(self, ledger: JobLedger, verdict: Verdict, metric: TurnMetric) -> Continue[...]:
        """Record the verify turn. A pass goes on to the stamp, and a rejection charges the job a turn."""
        record_turn(self.run_dir, metric)
        if verdict.passed:
            return Continue(verdict, self.stamp_job, ledger=ledger)
        return self._retry(ledger.charged(verdict.problems or ("The verifier rejected the pages without naming a problem.",)))
