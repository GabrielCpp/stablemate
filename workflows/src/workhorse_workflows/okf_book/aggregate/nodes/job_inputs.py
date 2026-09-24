"""What a job's turn reads: the contracts of the files its page reaches, and the stories that link to it."""
from __future__ import annotations

from pathlib import Path

from ostler import links as ostler_links
from ostler.model import read_links
from workhorse_workflows.okf_book.shared.budget import TURN_BUDGET_TOKENS, estimated_tokens
from workhorse_workflows.okf_book.shared.citations import page_citations
from workhorse_workflows.okf_book.shared.contracts import Contract, read_contracts
from workhorse_workflows.okf_book.shared.imports import reached_files
from workhorse_workflows.okf_book.shared.jobs import Job
from workhorse_workflows.okf_book.shared.page_kinds import JobKind, is_concept
from workhorse_workflows.okf_book.shared.production import production_files
from workhorse_workflows.okf_book.shared.stack import stack_files

EPICS_DIR = Path("docs") / "epics"
STORY_BUDGET_TOKENS = 6_000


def _page_files(root: Path, job: Job) -> tuple[str, ...]:
    """What the job's page reaches: its cited files and their imports, or the whole service when it cites nothing."""
    service_files = production_files(root, job.service)
    if job.kind is JobKind.OPERATIONS:
        stack = stack_files(root, job.service, service_files)
        return (*sorted(stack), *sorted(service_files - stack))
    if job.kind is JobKind.FLOWS or not job.page:
        return tuple(sorted(service_files))
    cited = [c.path for c in page_citations(root / job.page) if (root / c.path).is_file()]
    return reached_files(root, cited) if cited else tuple(sorted(service_files))


def _contract_tokens(contract: Contract) -> int:
    return estimated_tokens(len(contract.model_dump_json()))


def job_contracts(root: Path, run_dir: Path, job: Job, budget: int = TURN_BUDGET_TOKENS) -> tuple[Contract, ...]:
    """The saved contracts of the files the job's page reaches, nearest first, while they fit `budget`."""
    kept: list[Contract] = []
    spent = 0
    for contract in read_contracts(run_dir, _page_files(root, job)):
        tokens = _contract_tokens(contract)
        if spent + tokens > budget:
            break
        kept.append(contract)
        spent += tokens
    return tuple(kept)


def owed_contracts(root: Path, job: Job, contracts: tuple[Contract, ...]) -> tuple[Contract, ...]:
    """The contracts whose claims the job's pages must state. A page owes all it reads.

    The operations job reads the whole service and owes the stack's files. The flows job reads it too and owes none.
    A claim of a file a page cites is that page's to state.
    """
    if job.kind is JobKind.FLOWS:
        return ()
    if job.kind is JobKind.OPERATIONS:
        stack = stack_files(root, job.service, production_files(root, job.service))
        return tuple(contract for contract in contracts if contract.file in stack)
    return contracts


def _links_to(story: Path, page: Path) -> bool:
    return any(
        (story.parent / href.strip().split("#", 1)[0]).resolve() == page
        for _text, href, _line in read_links(story)
        if ostler_links.is_doc_link(href) and href.strip().split("#", 1)[0]
    )


def job_stories(root: Path, job: Job, budget: int = STORY_BUDGET_TOKENS) -> tuple[str, ...]:
    """The text of each story that links to the job's page, when the page is a concept, while they fit `budget`."""
    page = (root / job.page).resolve()
    epics = root / EPICS_DIR
    if not job.page or not page.is_file() or not epics.is_dir():
        return ()
    if not is_concept(page.read_text(encoding="utf-8")):
        return ()
    kept: list[str] = []
    spent = 0
    for story in sorted(epics.rglob("*.md")):
        if not _links_to(story, page):
            continue
        text = story.read_text(encoding="utf-8")
        if spent + estimated_tokens(len(text)) > budget:
            break
        kept.append(text)
        spent += estimated_tokens(len(text))
    return tuple(kept)
