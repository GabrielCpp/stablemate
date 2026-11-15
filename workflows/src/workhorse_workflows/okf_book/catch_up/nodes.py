"""The catch-up's nodes: which books are behind, what changed in them, and how each book was left."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import cast

from workhorse.worklist import WORK_FILE, JsonBackend, WorkItem, WorkList
from workhorse_workflows.kit.git import open_repo
from workhorse_workflows.okf_book.catch_up.models import CURRENT, STALE, UNJUDGED, BookOutcome, BookReport, Filed, ModuleReport
from workhorse_workflows.okf_book.catch_up.report import read_stale
from workhorse_workflows.okf_book.shared.blueprint import blueprint
from workhorse_workflows.okf_book.shared.book_gates import run_stale

BOOK = "book"
OUTCOMES_DIR = "outcomes"
DIFF_LIMIT_CHARS = 60000


def book_modules(root: Path) -> dict[str, list[str]]:
    """The modules of each service book under the book root: the package itself, or one per surface where the package has none."""
    packages = {path.relative_to(root).parts[1] for path in root.glob("services/*/service.py")}
    found = {name: [f"services.{name}"] for name in packages}
    for path in sorted(root.glob("services/*/*/service.py")):
        parts = path.relative_to(root).parts
        if parts[1] not in packages:
            found.setdefault(parts[1], []).append(".".join(parts[:-1]))
    return found


def outcome_path(run_dir: Path, service: str) -> Path:
    return run_dir / OUTCOMES_DIR / f"{service}.json"


def write_outcome(run_dir: Path, outcome: BookOutcome) -> None:
    path = outcome_path(run_dir, outcome.service)
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(outcome.model_dump_json(indent=2), encoding="utf-8")


def _one_stale_book(_logger: logging.Logger, _root: Path, _app: Path, _services: tuple[str, ...], run_dir: Path) -> Filed:
    module = ModuleReport(module="services.ledger", verdict=STALE, verified="0" * 7, elements={"Ping": ["ledger/ping.py"]}, new_files=["ledger/new.py"])
    report = BookReport(service="ledger", modules=[module])
    WorkList(JsonBackend(run_dir / WORK_FILE)).add([WorkItem(id="ledger", kind=BOOK, order=0, payload=report.model_dump(mode="json"))])
    return Filed(stale=["ledger"])


@blueprint.node(stub=_one_stale_book)
def catch_up_fill(logger: logging.Logger, root: Path, app: Path, services: tuple[str, ...], run_dir: Path) -> Filed:
    """File each book with something stale on the run's work list, and record the books that need no turn: current and first books. A book whose stale report could not be read is neither filed nor recorded, so the next visit reads it again. A book filed or recorded by an earlier visit is left alone."""
    work = WorkList(JsonBackend(run_dir / WORK_FILE))
    modules = book_modules(root)
    names = list(services) if services else sorted(modules)
    done = {item.id for item in work.items(BOOK)}
    filed = Filed()
    for order, service in enumerate(names):
        if service in done or outcome_path(run_dir, service).is_file():
            continue
        report = BookReport(service=service, modules=[_survey(logger, root, module, app) for module in modules.get(service, [])])
        if report.verdict == UNJUDGED:
            filed.unread[service] = "\n\n".join(_unread(module) for module in report.modules if module.verdict == UNJUDGED)
        elif not report.modules:
            write_outcome(run_dir, BookOutcome(service=service, verdict="first-book"))
            filed.settled.append(service)
        elif report.verdict == STALE:
            _ = work.add([WorkItem(id=service, kind=BOOK, order=order, payload=report.model_dump(mode="json"))])
            filed.stale.append(service)
        else:
            write_outcome(run_dir, _settled(report))
            filed.settled.append(service)
    logger.info("catch-up fill: %d stale, %d settled, %d unread", len(filed.stale), len(filed.settled), len(filed.unread))
    return filed


def _survey(logger: logging.Logger, root: Path, module: str, app: Path) -> ModuleReport:
    said = run_stale(logger, root, module, app)
    return read_stale(module, said.exit_code, said.output, said.error)


def _unread(module: ModuleReport) -> str:
    said = f"`python -m ostler.book stale {module.module}` exited {module.exit_code}"
    printed = "\n\n".join(text for text in (module.output, module.error) if text)
    return f"{said}:\n\n{printed}" if printed else f"{said} and printed nothing"


def _settled(report: BookReport) -> BookOutcome:
    if report.verdict == CURRENT:
        return BookOutcome(service=report.service, verdict="current")
    return BookOutcome(service=report.service, verdict="first-book")


def _empty_diff(_logger: logging.Logger, *_args: object) -> str:
    return ""


@blueprint.node(stub=_empty_diff)
def catch_up_diff(logger: logging.Logger, app: Path, verified: str, files: tuple[str, ...]) -> str:
    """The diff of the named files of the app between the commit a book was verified at and HEAD, cut where it passes the limit."""
    if not files:
        return ""
    text = cast("str", open_repo(app).git.diff(f"{verified}..HEAD", "--", *files))  # pyright: ignore[reportAny]
    if len(text) <= DIFF_LIMIT_CHARS:
        return text
    logger.warning("the diff since %s passes %d characters and was cut", verified, DIFF_LIMIT_CHARS)
    return f"{text[:DIFF_LIMIT_CHARS]}\n[the diff is cut here: read the rest with `git diff {verified}..HEAD -- <file>` in the app]"


def _recorded(_logger: logging.Logger, _run_dir: Path, outcome: BookOutcome) -> BookOutcome:
    return outcome


@blueprint.node(stub=_recorded)
def catch_up_record(logger: logging.Logger, run_dir: Path, outcome: BookOutcome) -> BookOutcome:
    """Record how the run left one book, replacing what an earlier visit recorded."""
    write_outcome(run_dir, outcome)
    logger.info("%s: %s", outcome.service, outcome.verdict)
    return outcome


def _no_outcomes(_logger: logging.Logger, *_args: object) -> list[BookOutcome]:
    return []


@blueprint.node(stub=_no_outcomes)
def catch_up_outcomes(logger: logging.Logger, run_dir: Path) -> list[BookOutcome]:
    """Every book's outcome the run recorded, by service."""
    folder = run_dir / OUTCOMES_DIR
    if not folder.is_dir():
        return []
    return [BookOutcome.model_validate_json(path.read_text(encoding="utf-8")) for path in sorted(folder.glob("*.json"))]
