"""The gate a run stops at: the command that reruns one blocker's checks, and what the run settles itself when the gate is answered."""
from __future__ import annotations

import fcntl
import logging
import shlex
import tempfile
from collections.abc import Iterable, Sequence
from pathlib import Path

from ostler.qa.attribution import Cause, Signature
from ostler.qa.verdict import Verdict
from pydantic import BaseModel, ConfigDict, TypeAdapter

from workhorse_workflows.okf_book.main.nodes.claim_snapshot import book_claims, changed_claims, read_snapshot, write_snapshot
from workhorse_workflows.okf_book.main.nodes.exercise import STACK_LOCK, exercise_book
from workhorse_workflows.okf_book.main.nodes.writer_commands import (
    WriterCommandState,
    check_command,
    exercise_command,
    write_command_state,
)
from workhorse_workflows.okf_book.main.nodes.writer_jobs import settle_jobs
from workhorse_workflows.okf_book.main.nodes.writer_stack import KeptStack
from workhorse_workflows.okf_book.shared.blockers import Blocker, Phase, Side, forget_blocker, read_blockers, record_blocker
from workhorse_workflows.okf_book.shared.book_compilation import obligation_page
from workhorse_workflows.okf_book.shared.book_run import ExerciseResult
from workhorse_workflows.okf_book.shared.entries import FEATURES_DIR
from workhorse_workflows.okf_book.shared.page_check import PageProblem, page_problems, tool_blockers
from workhorse_workflows.okf_book.shared.scenarios import PLAN_NAME, plan_scenarios

GATE_DIR = "gate"
FAILURES_FILE = "failures.json"
SNAPSHOT_FOLDER = "claims"

SIDE_BY_ESCALATED_CAUSE = {Cause.ENVIRONMENT: Side.ENVIRONMENT, Cause.APP: Side.APP, Cause.UNATTRIBUTED: Side.UNATTRIBUTED}
ESCALATED_SIDES = frozenset({*SIDE_BY_ESCALATED_CAUSE.values(), Side.OSTLER})

RunFailures = dict[str, tuple[PageProblem, ...]]

_FAILURES = TypeAdapter(RunFailures)
_LOGGER = logging.getLogger(__name__)


class GateRerun(BaseModel):
    """What one rerun of a service's blocked pages did, and each failure of it the writer can fix, by page."""

    model_config = ConfigDict(frozen=True)

    result: ExerciseResult
    failures: RunFailures = {}


def gate_folder(records_dir: Path, service: str) -> Path:
    """Where the reruns of *service*'s blockers keep their state, their jobs and their stack."""
    return records_dir / GATE_DIR / service


def rerun_command(records_dir: Path, service: str, phase: Phase, pages: Sequence[str]) -> str:
    """The command that reruns only the checks on *pages*, from any directory, or nothing when no page names them."""
    if not pages:
        return ""
    folder = gate_folder(records_dir, service)
    command = exercise_command(folder) if phase is Phase.EXERCISE else check_command(folder)
    return " ".join((command, *(shlex.quote(page) for page in pages)))


def escalation_reason(signature: Signature) -> str:
    """Why a person must act on *signature*: a capability only a person can supply, or the checks another party must fix."""
    if signature.gap:
        return (f"the stack lacks the {signature.gap}, and only a person can supply it; "
                f"the {signature.count} checks that need it pass once it is there; for example {signature.sample}")
    return f"{signature.count} checks failed this way; for example {signature.sample}"


def open_gate(root: Path, records_dir: Path, services: Sequence[str]) -> None:
    """Write the state each blocked service's reruns read, and each claim's expected outcome as the books state it now."""
    blocked = {blocker.service for blocker in read_blockers(records_dir)}
    for service in services:
        if service in blocked or "" in blocked:
            state = WriterCommandState(root=root, service=service, problems_at_turn_start=page_problems(root, service))
            _ = write_command_state(gate_folder(records_dir, service), state)
    write_snapshot(records_dir / GATE_DIR / SNAPSHOT_FOLDER, book_claims(root, services))


def take_failures(records_dir: Path, service: str) -> RunFailures:
    """The failures the last gate's settlement left for *service*'s writer, removed once taken."""
    path = gate_folder(records_dir, service) / FAILURES_FILE
    if not path.is_file():
        return {}
    failures = _FAILURES.validate_json(path.read_bytes())
    path.unlink()
    return failures


def keep_failures(records_dir: Path, service: str, failures: RunFailures) -> None:
    """Add *failures* to the ones kept for *service*'s writer, each under its page."""
    if not failures:
        return
    kept = take_failures(records_dir, service)
    _write_failures(records_dir, service, {page: (*kept.get(page, ()), *failures.get(page, ())) for page in (*kept, *(p for p in failures if p not in kept))})


def _write_failures(records_dir: Path, service: str, failures: RunFailures) -> None:
    folder = gate_folder(records_dir, service)
    folder.mkdir(parents=True, exist_ok=True)
    _ = (folder / FAILURES_FILE).write_bytes(_FAILURES.dump_json(failures))


def _writer_failures(root: Path, spec: Path, result: ExerciseResult) -> RunFailures:
    if result.summary is None:
        return {}
    scenarios, _problems = plan_scenarios(root, spec)
    plan = spec / PLAN_NAME
    return result.summary.failures_by_page(scenarios, plan.read_text(encoding="utf-8") if plan.is_file() else "")


def rerun_pages(root: Path, records_dir: Path, service: str, pages: Sequence[str]) -> GateRerun:
    """Run only the scenarios *pages* name, after any rerun an attendant left running, on a stack released once it ends."""
    folder = gate_folder(records_dir, service)
    settle_jobs(folder)
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / STACK_LOCK).open("w", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with tempfile.TemporaryDirectory(prefix="okf-gate-") as spec:
            result = exercise_book(KeptStack(folder, _LOGGER), root, service, Path(spec), pages)
            failures = _writer_failures(root, Path(spec), result)
    settle_jobs(folder)
    return GateRerun(result=result, failures=failures)


def _passes(rerun: GateRerun, blocker: Blocker) -> bool:
    """Whether the rerun held every check on the blocker's pages: the whole rerun passed, or each claim on those pages passed and no failure sits on them."""
    result = rerun.result
    if result.passed:
        return True
    summary = result.summary
    if summary is None or result.stopped_at_probes:
        return False
    pages = set(blocker.pages)
    failing = set(rerun.failures).union(*(summary.signature_pages(signature) for signature in summary.signatures))
    verdicts = [verdict for claim, verdict in summary.verdicts.items() if obligation_page(claim) in pages]
    return bool(verdicts) and all(verdict is Verdict.PASS for verdict in verdicts) and not pages & failing


def _still_failing(rerun: GateRerun, blocker: Blocker) -> str:
    summary = rerun.result.summary
    signatures = summary.signatures if summary is not None else ()
    reasons = [escalation_reason(signature) for signature in signatures
               if signature.cause in SIDE_BY_ESCALATED_CAUSE and set(summary.signature_pages(signature)) & set(blocker.pages)] if summary else []
    return "the gate's rerun still fails: " + ("; ".join(reasons) or "; ".join(rerun.result.lines[:5]))


def _settle_runs(root: Path, records_dir: Path, service: str, runs: Sequence[Blocker]) -> RunFailures:
    """Rerun the blocked pages once, close each blocker whose checks now hold, and keep each escalation that still fails with the rerun's result. Return what the writer gets."""
    rerun = rerun_pages(root, records_dir, service, tuple(dict.fromkeys(page for blocker in runs for page in blocker.pages)))
    writers: list[Blocker] = []
    for blocker in runs:
        if _passes(rerun, blocker):
            forget_blocker(records_dir, blocker)
        elif blocker.side in ESCALATED_SIDES:
            _ = record_blocker(records_dir, blocker.model_copy(update={"reason": _still_failing(rerun, blocker)}))
        else:
            writers.append(blocker)
    if not writers or rerun.failures:
        return rerun.failures if writers else {}
    text = "the gate's rerun of this page's checks failed: " + "; ".join(rerun.result.lines[:5])
    return {blocker.pages[0]: (PageProblem(blocker.pages[0], text),) for blocker in writers}


def _settle_writes(root: Path, records_dir: Path, service: str, writes: Sequence[Blocker]) -> None:
    """Close each page check blocker whose pages the check no longer finds a problem on, and each tool blocker whose tool is now opted in. The other page blockers go to the writer with the book's problems."""
    failing = {problem.page for problem in page_problems(root, service)}
    unopted = {blocker.key for blocker in tool_blockers(root, service)}
    for blocker in writes:
        cleared = blocker.key not in unopted if blocker.side is Side.ENVIRONMENT else not set(blocker.pages) & failing
        if cleared:
            forget_blocker(records_dir, blocker)


def _service_of(page: str, services: Iterable[str]) -> str:
    return next((service for service in services if page.startswith(f"{(FEATURES_DIR / service).as_posix()}/")), "")


def settle_gate(root: Path, records_dir: Path, services: Sequence[str]) -> tuple[str, ...]:
    """Rerun each blocker's checks, close those that pass, keep each escalation that still fails, and leave each writer its failures and every claim an answer changed. Return the services to route again.

    A service the blockers named is routed, unless all it has left is escalations that still fail and
    nothing for its writer. A blocker that names no service routes every service.
    """
    blockers = read_blockers(records_dir)
    named = {blocker.service for blocker in blockers}
    failures: dict[str, dict[str, list[PageProblem]]] = {}
    snapshot = records_dir / GATE_DIR / SNAPSHOT_FOLDER
    before = read_snapshot(snapshot)
    if before is not None:
        for problem in changed_claims(before, book_claims(root, services)):
            failures.setdefault(_service_of(problem.page, services), {}).setdefault(problem.page, []).append(problem)
        (snapshot / "claims.json").unlink()
    for service in services:
        mine = [blocker for blocker in blockers if blocker.service == service and blocker.pages]
        writes = [blocker for blocker in mine if blocker.phase is Phase.WRITE]
        if writes:
            _settle_writes(root, records_dir, service, writes)
        runs = [blocker for blocker in mine if blocker.phase is Phase.EXERCISE]
        for page, problems in (_settle_runs(root, records_dir, service, runs) if runs else {}).items():
            failures.setdefault(service, {}).setdefault(page, []).extend(problems)
    for service, found in failures.items():
        if service:
            _write_failures(records_dir, service, {page: tuple(problems) for page, problems in sorted(found.items())})
    left = read_blockers(records_dir)
    held = {service for service in services if service not in failures and (kept := [b for b in left if b.service == service])
            and all(b.side in ESCALATED_SIDES and b.pages for b in kept)}
    return tuple(service for service in services if ("" in named or service in named or service in failures) and service not in held)
