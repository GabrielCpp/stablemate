"""Phase 2's second half: write each page from the contracts that reach it, check it, have it judged, and commit it.

A job that fails three turns has the book put back and goes to the operator.
"""
from __future__ import annotations

import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ostler.stamp import stamp_page
from workhorse.pyflow import Continue, Done, Transition
from workhorse.worklist import WorkItem
from workhorse_workflows.kit import commit_paths
from workhorse_workflows.okf_book.shared.blockers import Blocker, Phase, Side, record_blocker
from workhorse_workflows.okf_book.shared.book_flow import BookFlow
from workhorse_workflows.okf_book.shared.budget import (
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
from workhorse_workflows.okf_book.shared.attempts import JobLedger
from workhorse_workflows.okf_book.aggregate.nodes.check_pages import CHECK_RUNS, JobCheck, check_command, write_job_check
from workhorse_workflows.okf_book.shared.citations import book_pages
from workhorse_workflows.okf_book.shared.confine import (
    book_changes,
    confine,
    judged_pages,
    new_since_head,
    revert,
    snapshot,
)
from workhorse_workflows.okf_book.shared.contracts import Contract
from workhorse_workflows.okf_book.aggregate.nodes.garbage import collectable, delete_book_pages
from workhorse_workflows.okf_book.aggregate.nodes.job_inputs import job_contracts, job_stories
from workhorse_workflows.okf_book.shared.entries import FEATURES_DIR
from workhorse_workflows.okf_book.shared.jobs import (
    Job,
    job_of,
    listed_pages,
    queue_rows,
    service_folder,
    unowned_page_rows,
)
from workhorse_workflows.okf_book.shared.metrics import TurnMetric, record_turn
from workhorse_workflows.okf_book.shared.page_kinds import JobKind
from workhorse_workflows.okf_book.shared.page_check import charged_pages, inherited_gaps, page_problems, unreached, unreached_problems
from workhorse_workflows.okf_book.shared.work import BLOCKED, DONE, JOB, UNQUEUED, seed

PAGES_BUDGET_TOKENS = 3_000
VERIFY_PROMPT = "aggregate/prompts/verify-page.md"
UNJUDGED_PROBLEM = "The changed pages are too large for any turn to judge. Split the page, or cut what it repeats."
WRITE_PROMPTS = {
    JobKind.PAGE: "aggregate/prompts/write-page.md",
    JobKind.OPERATIONS: "aggregate/prompts/write-operations.md",
    JobKind.FLOWS: "aggregate/prompts/write-flows.md",
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


def _service_of(page: str) -> str:
    return Path(page).relative_to(FEATURES_DIR).parts[0]


def _contract_tokens(contracts: tuple[Contract, ...]) -> int:
    return estimated_tokens(sum(len(c.model_dump_json()) for c in contracts))


class Aggregate(BookFlow):
    """Phase 2's aggregation: one job at a time, nearest the root first, until none is left."""

    services: tuple[str, ...] = ()

    def start(self) -> Continue[...]:
        """Seed the queue from the book as it stands, then the snapshot of what it leaves unowned, once."""
        seed(self.work, JOB, queue_rows(self.root, self.services))
        queued = tuple(job_of(item) for item in self.work.items(JOB))
        seed(self.work, UNQUEUED, unowned_page_rows(self.root, self.services, queued))
        return Continue(None, self.aggregate)

    def aggregate(self) -> Transition:
        """Take the next job the queue has not settled. With none left, aggregation is done."""
        items = self.work.claim(1, kind=JOB)
        if not items:
            return Done(len(self.work.items(JOB)))
        return self._begin_job(items)

    def _begin_job(self, items: list[WorkItem]) -> Continue[...]:
        job = job_of(items[0])
        gaps = inherited_gaps(self.root, job.service, job.owned_pages)
        ledger = JobLedger(job=job, before=snapshot(self.root), inherited_gaps=gaps)
        _ = write_job_check(self.records_dir, JobCheck(
            root=self.root, service=job.service, before=ledger.before, owned_pages=tuple(sorted(job.owned_pages)), inherited_gaps=gaps
        ))
        return Continue(job, self.write_job, ledger=ledger)

    def _rewrite(self, ledger: JobLedger) -> Continue[...]:
        return Continue(ledger.attempts, self.write_job, ledger=ledger)

    def _next_job(self, result: object) -> Continue[...]:
        return Continue(result, self.aggregate)

    def _retry(self, ledger: JobLedger) -> Continue[...]:
        if ledger.exhausted:
            return Continue(ledger.attempts, self.abandon_job, ledger=ledger)
        return self._rewrite(ledger)

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
        contracts = job_contracts(root, self.records_dir, job, budget=TURN_BUDGET_TOKENS - fixed)
        started = time.monotonic()
        written = self.agent(
            "aggregate/prompts/write-page.md" if job.kind is JobKind.PAGE
            else "aggregate/prompts/write-operations.md" if job.kind is JobKind.OPERATIONS
            else "aggregate/prompts/write-flows.md",
            returns=Written,
            args={
                "service": job.service,
                "folder": service_folder(job.service),
                "page": job.page,
                "pages": list(pages.kept),
                "contracts": _contract_args(contracts),
                "stories": list(stories),
                "problems": list(problems.kept),
                "check": check_command(self.records_dir),
                "check_runs": CHECK_RUNS,
            },
            cwd=root,
        )
        metric = _turn_metric(f"write-{job.kind.value}", job.subject, fixed + _contract_tokens(contracts), started)
        return Continue(written, self.record_write, ledger=ledger, metric=metric)

    def record_write(self, ledger: JobLedger, metric: TurnMetric) -> Continue[...]:
        """Record the writing turn before anything it changed is put back."""
        record_turn(self.records_dir, metric)
        return Continue(metric, self.confine_job, ledger=ledger)

    def confine_job(self, ledger: JobLedger) -> Continue[...]:
        """Put back what the writing turn may not change."""
        confined = confine(self.root, ledger.job, ledger.before, self.records_dir)
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
        """Charge the turn with each page deleted as unreachable, and each doctor error and compile gap on the job's pages and the rest it changed."""
        job = ledger.job
        changed = book_changes(self.root, job.service, ledger.before)
        charged = charged_pages(self.root, changed, job.owned_pages)
        problems = (*unreached_problems(deleted), *page_problems(self.root, job.service, charged, ledger.inherited_gaps))
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
        contracts = job_contracts(root, self.records_dir, job, budget=TURN_BUDGET_TOKENS - fixed - judged.tokens)
        started = time.monotonic()
        verdict = self.agent(
            "aggregate/prompts/verify-page.md",
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
        record_turn(self.records_dir, metric)
        if verdict.passed:
            return Continue(verdict, self.stamp_job, ledger=ledger)
        return self._retry(ledger.charged(verdict.problems or ("The verifier rejected the pages without naming a problem.",)))

    def abandon_job(self, ledger: JobLedger) -> Continue[...]:
        """Three failed turns: put the book back as it was."""
        reverted = revert(self.root, ledger.before, self.records_dir)
        return Continue(reverted, self.block_job, ledger=ledger)

    def block_job(self, ledger: JobLedger) -> Continue[...]:
        """Hand the abandoned job to the operator, and settle it as blocked so no later turn reopens it."""
        reason = " ".join(ledger.problems)
        _ = record_blocker(self.records_dir, Blocker(subject=ledger.job.subject, phase=Phase.AGGREGATE, side=Side.BOOK, reason=reason))
        _ = self.work.mark(ledger.job.subject, BLOCKED, JOB)
        return self._next_job(ledger.job.subject)

    def stamp_job(self, ledger: JobLedger) -> Continue[...]:
        """Stamp each written page with its cited files' digests, and note the pages the job created."""
        root = self.root
        changed = book_changes(root, ledger.job.service, ledger.before)
        for page in changed:
            if page.endswith(".md") and (root / page).is_file():
                _ = stamp_page(root, root / FEATURES_DIR, page)
        created = new_since_head(root, changed)
        return Continue(changed, self.commit_job, ledger=ledger, created=created)

    def commit_job(self, ledger: JobLedger, created: tuple[str, ...]) -> Continue[...]:
        """Commit each file the job changed on its own, and settle the job as done."""
        root, job = self.root, ledger.job
        changed = book_changes(root, job.service, ledger.before)
        for path in changed:
            verb = "write" if (root / path).exists() else "delete"
            _ = commit_paths(root, f"docs({job.service}): {verb} {Path(path).stem}", path)
        _ = self.work.mark(job.subject, DONE, JOB)
        return Continue(changed, self.pick_garbage, job=job, created=created)

    def pick_garbage(self, job: Job, created: tuple[str, ...]) -> Continue[...]:
        """Pick each page nothing reaches now that the job may delete, as `garbage` rules."""
        dead = tuple(page.rel for page in collectable(self.root, job, created))
        return Continue(dead, self.delete_garbage, dead=dead)

    def delete_garbage(self, dead: tuple[str, ...]) -> Continue[...]:
        """Delete each picked page. The commit is the next state, so a failed commit retries alone. A retry skips the pages already gone."""
        delete_book_pages(self.root, dead)
        return Continue(dead, self.commit_garbage, dead=dead)

    def commit_garbage(self, dead: tuple[str, ...]) -> Continue[...]:
        """Commit each deleted page on its own. A retry finds the committed ones done."""
        for page in dead:
            _ = commit_paths(self.root, f"docs({_service_of(page)}): delete {Path(page).stem}, nothing reaches it", page)
        return self._next_job(dead)
