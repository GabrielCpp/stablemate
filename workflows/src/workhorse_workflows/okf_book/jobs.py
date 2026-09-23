"""The aggregation queue: which page a turn writes next.

The queue is frozen when aggregation starts and lives on disk, so a resume walks the same jobs in
the same order. Entry pages go first, then each service's operations and flows, then every other
reachable page nearest the root first. An operations page or a flow page is its kind's job, and no
job of its own. A kind job owns its kind's pages as the queue froze them. A page a turn writes or links later joins no queue: the turn that wrote it had it
judged, and the report names any other page that became reachable.
"""
from __future__ import annotations

import hashlib
from collections import deque
from collections.abc import Iterable, Iterator
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ostler import links as ostler_links
from ostler.model import read_links
from workhorse_workflows.okf_book.citations import book_pages
from workhorse_workflows.okf_book.entries import FEATURES_DIR, entries_path
from workhorse_workflows.okf_book.page_kinds import JobKind, page_kind, pages_of_kind
from workhorse_workflows.okf_book.production import entry_pages

QUEUE_NAME = "queue.json"


class Job(BaseModel):
    """One aggregation turn's subject: a service, what it writes, and the page, when it writes one.

    An operations or flows job carries its kind's pages as the queue froze them. A page of that kind written later is not its own.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    service: str
    kind: JobKind
    page: str = ""
    kind_pages: tuple[str, ...] = ()

    @property
    def subject(self) -> str:
        return self.page or f"{self.service}:{self.kind.value}"

    @property
    def key(self) -> str:
        return hashlib.sha256(self.subject.encode()).hexdigest()[:16]

    @property
    def owned_pages(self) -> frozenset[str]:
        """The pages the job writes: its page, or its kind's pages as the queue froze them."""
        return frozenset({self.page}) if self.kind is JobKind.PAGE else frozenset(self.kind_pages)


def listed_pages(root: Path, job: Job) -> tuple[str, ...]:
    """The pages a writing turn is told of: every page of its kind now, or its kind's pages as the queue froze them."""
    if job.kind is JobKind.PAGE:
        return pages_of_kind(root, job.service, job.kind)
    return job.kind_pages


class JobQueue(BaseModel):
    """The jobs aggregation works through, in order, and every book page present when it started."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    jobs: tuple[Job, ...]
    present_pages: tuple[str, ...]

    @property
    def page_job_pages(self) -> frozenset[str]:
        """The page of each page job. A kind job's pages are not among them."""
        return frozenset(job.page for job in self.jobs if job.page)

    @property
    def frozen_pages(self) -> frozenset[str]:
        """Every page a queued job writes: each page job's page, and each kind job's pages."""
        return frozenset(page for job in self.jobs for page in job.owned_pages)


def _rel(root: Path, page: Path) -> str:
    return page.resolve().relative_to(root.resolve()).as_posix()


def _linked(page: Path, pages: frozenset[Path]) -> Iterator[Path]:
    for _text, href, _line in read_links(page):
        target = href.strip().split("#", 1)[0].split("?", 1)[0]
        if ostler_links.is_doc_link(href) and target:
            resolved = (page.parent / target).resolve()
            if resolved in pages:
                yield resolved


def pages_by_depth(root: Path, service: str) -> tuple[str, ...]:
    """Every page the service's entries page reaches, nearest first, the entries page itself left out."""
    pages = frozenset(page.resolve() for page in book_pages(root, service))
    start = entries_path(root, service).resolve()
    seen = {start}
    queue = deque([start])
    order: list[str] = []
    while queue:
        for target in _linked(queue.popleft(), pages):
            if target not in seen:
                seen.add(target)
                queue.append(target)
                order.append(_rel(root, target))
    return tuple(order)


def _candidates(root: Path, services: Iterable[str]) -> Iterator[Job]:
    names = tuple(services)
    for service in names:
        for page in entry_pages(root, service):
            yield Job(service=service, kind=JobKind.PAGE, page=_rel(root, page))
    for kind in (JobKind.OPERATIONS, JobKind.FLOWS):
        for service in names:
            yield Job(service=service, kind=kind, kind_pages=pages_of_kind(root, service, kind))
    for service in names:
        for page in pages_by_depth(root, service):
            if page_kind((root / page).read_text(encoding="utf-8")) is JobKind.PAGE:
                yield Job(service=service, kind=JobKind.PAGE, page=page)


def read_queue(run_dir: Path) -> JobQueue | None:
    path = run_dir / QUEUE_NAME
    return JobQueue.model_validate_json(path.read_text(encoding="utf-8")) if path.is_file() else None


def freeze_queue(root: Path, run_dir: Path, services: Iterable[str]) -> JobQueue:
    """The run's queue: read back when it was frozen before, computed and written otherwise."""
    frozen = read_queue(run_dir)
    if frozen is not None:
        return frozen
    names = tuple(services)
    present = sorted(_rel(root, page) for service in names for page in book_pages(root, service))
    queue = JobQueue(jobs=tuple(dict.fromkeys(_candidates(root, names))), present_pages=tuple(present))
    run_dir.mkdir(parents=True, exist_ok=True)
    _ = (run_dir / QUEUE_NAME).write_text(queue.model_dump_json(), encoding="utf-8")
    return queue


def service_folder(service: str) -> str:
    return (FEATURES_DIR / service).as_posix()
