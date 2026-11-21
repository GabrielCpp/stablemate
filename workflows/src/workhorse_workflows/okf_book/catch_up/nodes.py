"""The catch-up's nodes: which books are behind, what changed in them, and how each book was left."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import cast

from workhorse.worklist import WORK_FILE, JsonBackend, WorkItem, WorkList
from workhorse_workflows.kit.git import open_repo
from workhorse_workflows.okf_book.catch_up.models import CURRENT, FIRST_BOOK, STALE, UNJUDGED, BatchLog, BookOutcome, BookReport, Filed, FormatMove, ModuleCheck, ModuleReport, Roots
from workhorse_workflows.okf_book.catch_up.register import entries_for, read_register, write_register
from workhorse_workflows.okf_book.catch_up.report import read_check, read_stale
from workhorse_workflows.okf_book.shared.blueprint import blueprint
from workhorse_workflows.okf_book.shared.book_format import book_format_delta
from workhorse_workflows.okf_book.shared.book_flow import COULD_NOT_JUDGE
from workhorse_workflows.okf_book.shared.book_gates import python_book_check, run_stale

BOOK = "book"
OUTCOMES_DIR = "outcomes"
NOTES_DIR = "format-notes"
MOVES_DIR = "format-moves"
BATCHES_DIR = "batches"
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


def _one_stale_book(_logger: logging.Logger, _roots: Roots, _services: tuple[str, ...], run_dir: Path) -> Filed:
    module = ModuleReport(module="services.ledger", verdict=STALE, verified="0" * 7, elements={"Ping": ["ledger/ping.py"]}, new_files=["ledger/new.py"])
    report = BookReport(service="ledger", modules=[module])
    WorkList(JsonBackend(run_dir / WORK_FILE)).add([WorkItem(id="ledger", kind=BOOK, order=0, payload=report.model_dump(mode="json"))])
    return Filed(stale=["ledger"])


@blueprint.node(stub=_one_stale_book)
def catch_up_fill(logger: logging.Logger, roots: Roots, services: tuple[str, ...], run_dir: Path) -> Filed:
    """File each book with something stale in the app, or with nothing stale and a red check or a note its register of declined notes does not cover, on the run's work list, and record the books that need no turn: current and first books. The check runs for every filed book, and one that is red or that printed an uncovered note makes its findings and notes the book's work list for the format. The writer's history comes along as context when it can be read. A book whose stale report or check could not be read is neither filed nor recorded, so the next visit reads it again. A book filed or recorded by an earlier visit is left alone."""
    work = WorkList(JsonBackend(run_dir / WORK_FILE))
    root = roots.book
    modules = book_modules(root)
    names = list(services) if services else sorted(modules)
    done = {item.id for item in work.items(BOOK)}
    filed = Filed()
    for order, service in enumerate(names):
        if service in done or outcome_path(run_dir, service).is_file():
            continue
        report = BookReport(service=service, modules=[_survey(logger, root, module, roots.app) for module in modules.get(service, [])], declined=read_register(root, service))
        if report.verdict == UNJUDGED:
            filed.unread[service] = "\n\n".join(_unread(module) for module in report.modules if module.verdict == UNJUDGED)
        elif not report.modules:
            write_outcome(run_dir, BookOutcome(service=service, verdict="first-book"))
            filed.settled.append(service)
        elif report.verdict == FIRST_BOOK:
            write_outcome(run_dir, _settled(report))
            filed.settled.append(service)
        elif report.verdict == STALE:
            checks = [_checked(logger, root, module.module, roots.app) for module in report.modules]
            judged = [check for check in checks if check.exit_code != COULD_NOT_JUDGE]
            _ = work.add([_item(logger, report.model_copy(update={"checks": judged}), roots, order)])
            filed.stale.append(service)
        else:
            checks = [_checked(logger, root, module.module, roots.app) for module in report.modules]
            if any(check.exit_code == COULD_NOT_JUDGE for check in checks):
                filed.unread[service] = "\n\n".join(_cannot(check) for check in checks if check.exit_code == COULD_NOT_JUDGE)
            elif (checked := report.model_copy(update={"checks": checks})).for_format:
                _ = work.add([_item(logger, checked, roots, order)])
                filed.stale.append(service)
            else:
                write_outcome(run_dir, _settled(report))
                filed.settled.append(service)
    logger.info("catch-up fill: %d filed, %d settled, %d unread", len(filed.stale), len(filed.settled), len(filed.unread))
    return filed


def _checked(logger: logging.Logger, root: Path, module: str, app: Path) -> ModuleCheck:
    said = python_book_check(logger, root, module, app)
    return read_check(module, said.exit_code, said.output, said.noted)


def _cannot(check: ModuleCheck) -> str:
    return f"`python -m ostler.book check {check.module}` exited {check.exit_code}:\n\n" + "\n".join(check.lines)


def _item(logger: logging.Logger, report: BookReport, roots: Roots, order: int) -> WorkItem:
    delta = book_format_delta(logger, roots.book, report.service, roots.history)
    if delta.unreadable:
        logger.info("%s: the format history was not available (%s), the check's findings are the work list", report.service, delta.unreadable)
    else:
        report = report.model_copy(update={"format": delta})
    return WorkItem(id=report.service, kind=BOOK, order=order, payload=report.model_dump(mode="json"))


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
    logger.info("%s: %s", outcome.service, outcome.status)
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


def _no_notes(_logger: logging.Logger, *_args: object) -> list[str]:
    return []


@blueprint.node(stub=_no_notes)
def catch_up_format_notes(logger: logging.Logger, run_dir: Path, service: str, lines: tuple[str, ...]) -> list[str]:
    """Merge the format lines an owner turn replied into the ones the book's earlier laps gave, a later line for a commit replacing an earlier one, and return them all."""
    path = run_dir / NOTES_DIR / f"{service}.json"
    kept = cast("dict[str, str]", json.loads(path.read_text(encoding="utf-8"))) if path.is_file() else {}
    for line in (line for line in lines if line.strip()):
        kept[line.split()[0]] = line
    if any(line.strip() for line in lines):
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(json.dumps(kept, indent=2), encoding="utf-8")
    logger.info("%s: %d format lines", service, len(kept))
    return list(kept.values())


def _move_path(run_dir: Path, service: str) -> Path:
    return run_dir / MOVES_DIR / f"{service}.json"


def _unmoved(_logger: logging.Logger, _run_dir: Path, _service: str, move: FormatMove) -> FormatMove:
    return move


@blueprint.node(stub=_unmoved)
def catch_up_move(logger: logging.Logger, run_dir: Path, service: str, move: FormatMove) -> FormatMove:
    """Merge the fields of *move* that were set into what the book's earlier laps recorded of its move onto the format, a later lap replacing an earlier one, and return all of it."""
    path = _move_path(run_dir, service)
    kept = FormatMove.model_validate_json(path.read_text(encoding="utf-8")) if path.is_file() else FormatMove()
    merged = kept.model_copy(update={name: getattr(move, name) for name in move.model_fields_set})  # pyright: ignore[reportAny]
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(merged.model_dump_json(indent=2), encoding="utf-8")
    logger.info("%s: move %s", service, move.model_dump_json(exclude_unset=True))
    return merged


def _unlogged(_logger: logging.Logger, _run_dir: Path, _service: str, update: BatchLog) -> BatchLog:
    return update


@blueprint.node(stub=_unlogged)
def catch_up_batch(logger: logging.Logger, run_dir: Path, service: str, update: BatchLog) -> BatchLog:
    """Merge the fields of *update* that were set into what the run recorded of the book's batches, the batch open and the batches committed, and return all of it."""
    path = run_dir / BATCHES_DIR / f"{service}.json"
    kept = BatchLog.model_validate_json(path.read_text(encoding="utf-8")) if path.is_file() else BatchLog()
    merged = kept.model_copy(update={name: getattr(update, name) for name in update.model_fields_set})  # pyright: ignore[reportAny]
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(merged.model_dump_json(indent=2), encoding="utf-8")
    logger.info("%s: %d batches committed", service, len(merged.done))
    return merged


def _no_declined(_logger: logging.Logger, _root: Path, _service: str, _lines: tuple[str, ...], _notes: tuple[str, ...]) -> list[str]:
    return []


@blueprint.node(stub=_no_declined)
def catch_up_declined(logger: logging.Logger, root: Path, service: str, lines: tuple[str, ...], notes: tuple[str, ...]) -> list[str]:
    """Write the lines an owner turn declined notes with into the book's register, `services/<service>/DECLINED.md`, read against the notes the check prints, a later line for the same element and kind replacing an earlier one, and return every entry the register holds."""
    fresh = entries_for(lines, notes)
    kept = write_register(root, service, fresh) if fresh else read_register(root, service)
    logger.info("%s: %d notes declined", service, len(kept))
    return kept
