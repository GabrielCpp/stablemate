"""Phase 2's aggregation once a job's pages pass: stamp them, commit them, and collect the pages nothing reaches."""
from __future__ import annotations

from pathlib import Path

from ostler.stamp import stamp_page
from workhorse.pyflow import Continue
from workhorse_workflows.kit import commit_paths
from workhorse_workflows.okf_book.attempts import JobLedger
from workhorse_workflows.okf_book.confine import book_changes, new_since_head
from workhorse_workflows.okf_book.entries import FEATURES_DIR
from workhorse_workflows.okf_book.flow_exercise import Exercise
from workhorse_workflows.okf_book.garbage import collectable, delete_book_pages
from workhorse_workflows.okf_book.jobs import Job
from workhorse_workflows.okf_book.settled import settle_job


def _service_of(page: str) -> str:
    return Path(page).relative_to(FEATURES_DIR).parts[0]


class Collect(Exercise):
    """A passed job's pages go in, one commit per file, then each page nothing reaches that the job may delete goes out."""

    def _next_job(self, result: object) -> Continue[...]:
        raise NotImplementedError

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
        """Commit each file the job changed on its own, and settle the job as committed."""
        root, job = self.root, ledger.job
        changed = book_changes(root, job.service, ledger.before)
        for path in changed:
            verb = "write" if (root / path).exists() else "delete"
            _ = commit_paths(root, f"docs({job.service}): {verb} {Path(path).stem}", path)
        settle_job(self.run_dir, job, committed=True)
        return Continue(changed, self.pick_garbage, job=job, created=created)

    def pick_garbage(self, job: Job, created: tuple[str, ...]) -> Continue[...]:
        """Pick each page nothing reaches now that the job may delete, as `garbage` rules."""
        dead = tuple(page.rel for page in collectable(self.root, job, created))
        return Continue(dead, self.delete_garbage, dead=dead)

    def delete_garbage(self, dead: tuple[str, ...]) -> Continue[...]:
        """Delete each picked page and commit it on its own. A retry skips the pages already gone, and finds the committed ones done."""
        delete_book_pages(self.root, dead)
        for page in dead:
            _ = commit_paths(self.root, f"docs({_service_of(page)}): delete {Path(page).stem}, nothing reaches it", page)
        return self._next_job(dead)
