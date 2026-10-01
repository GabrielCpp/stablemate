"""Phase 3 as code: compile the whole book into a plan, and read back what running it did.

No agent takes part in compilation. The plan, its context and the run's evidence live under the
run directory, so the book's repo only ever changes through a committed page.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from ostler.provenance import CONTEXT_FILE
from ostler.qa.attribution import Cause, Signature
from ostler.qa.plan import PlanDocument, load_plan
from ostler.qa.v2 import run_plan
from ostler.qa.verdict import Verdict
from workhorse_workflows.okf_book.shared.book_compilation import BookCompilation, compile_services, obligation_node, obligation_page
from workhorse_workflows.okf_book.shared.page_check import PageProblem

SPEC_DIR = "spec"
PLAN_NAME = "qa_plan.py"
RUN_NAME = "run-summary.json"
OBLIGATION_PAGE = re.compile(r"^okf:(?P<page>[^#]+?\.md)(?:[#:]|$)")
PLAN_FRAME = re.compile(rf'File "[^"]*{re.escape(PLAN_NAME)}", line (?P<line>\d+)')
CLAIM_MARK = re.compile(r"^\s*# (?P<claim>okf:\S+)")
SCENARIO_DEF = re.compile(r"^def ")


class Scenario(BaseModel):
    """One compiled scenario, and the obligations it covers."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str
    covers: tuple[str, ...] = ()

    @property
    def pages(self) -> tuple[str, ...]:
        """The repo-relative book pages that state the obligations this scenario covers."""
        return tuple(dict.fromkeys(match["page"] for obligation in self.covers if (match := OBLIGATION_PAGE.match(obligation))))


class FailedCheck(BaseModel):
    """One check that did not hold: what it asserted, what it expected, what it observed, and whose fault it is.

    A check from a run that attributed no cause is the book's to fix.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    label: str
    expected: str = ""
    actual: str = ""
    command_ending_text: str = ""
    covers: tuple[str, ...] = ()
    cause: Cause = Cause.BOOK
    precondition: str = ""
    status: str = ""
    shape: str = ""
    gap: str = ""

    @property
    def claim(self) -> str:
        """The one book claim this check was made for, or nothing when it covers none or several."""
        return self.covers[0] if len(self.covers) == 1 and obligation_page(self.covers[0]) else ""

    def failure_line(self) -> str:
        observed = f"{self.label}: expected {self.expected}, observed {self.actual}"
        return f"{observed} (the command it observed ended with {self.command_ending_text})" if self.command_ending_text else observed


class ScenarioOutcome(BaseModel):
    """How one scenario ended, as the run reports it."""

    model_config = ConfigDict(frozen=True, extra="ignore", validate_by_name=True, validate_by_alias=True)

    status: str
    assertions: int = 0
    failures: int = 0
    message: str = ""
    failed_checks: tuple[FailedCheck, ...] = ()
    unreached: tuple[str, ...] = ()

    def failure_lines(self) -> tuple[str, ...]:
        """Every failed check, then the last line of the run's own message."""
        message_last_line = self.message.strip().splitlines()[-1:]
        return (*(check.failure_line() for check in self.failed_checks), *message_last_line)

    @property
    def book_checks(self) -> tuple[FailedCheck, ...]:
        """The failed checks the book's writer can fix."""
        return tuple(check for check in self.failed_checks if check.cause is Cause.BOOK)

    @property
    def fails_the_book(self) -> bool:
        """Whether the writer has something to fix here: a failed check of the book's, or a failure no check accounts for."""
        return bool(self.book_checks) or not self.failed_checks

    def unclaimed_failure_lines(self) -> tuple[str, ...]:
        """Every failed check of the book's made for no one claim, then the last line of the run's own message."""
        message_last_line = self.message.strip().splitlines()[-1:]
        return (*(check.failure_line() for check in self.book_checks if not check.claim), *message_last_line)

    def failed_claim(self, plan_source: str) -> str:
        """The obligation whose compiled lines in *plan_source* the run's traceback stopped in, or nothing when it stopped in none.

        The search stops at the scenario's own `def`, so a scenario stopped before its first mark names no obligation of another.
        """
        stopped_at_lines = [int(frame.group(1)) for frame in PLAN_FRAME.finditer(self.message)]
        if not stopped_at_lines:
            return ""
        for line in reversed(plan_source.splitlines()[: stopped_at_lines[-1]]):
            if SCENARIO_DEF.match(line):
                return ""
            if mark := CLAIM_MARK.match(line):
                return mark["claim"]
        return ""


class RunSummary(BaseModel):
    """What running the plan did: its status, each scenario's outcome, what stopped it, and the verdict each claim ended with."""

    model_config = ConfigDict(frozen=True, extra="ignore", validate_by_name=True, validate_by_alias=True)

    status: str
    scenarios: dict[str, ScenarioOutcome] = {}
    problems: tuple[str, ...] = ()
    runner_errors: tuple[str, ...] = ()
    report_path: str = Field(default="", validation_alias="report")
    signatures: tuple[Signature, ...] = ()
    verdicts: dict[str, Verdict] = {}

    @property
    def failed_scenarios(self) -> tuple[str, ...]:
        return tuple(sorted(name for name, outcome in self.scenarios.items() if outcome.status != "passed"))

    @property
    def gaps(self) -> dict[str, str]:
        """Each gapped claim and the capability the stack lacks for it, claims in order."""
        gapped = {claim for claim, verdict in self.verdicts.items() if verdict is Verdict.GAPPED}
        found = {claim: check.gap for outcome in self.scenarios.values() for check in outcome.failed_checks
                 if check.gap for claim in check.covers if claim in gapped}
        return dict(sorted(found.items()))

    def failures_by_page(self, scenarios: Iterable[Scenario], plan_source: str = "") -> dict[str, tuple[PageProblem, ...]]:
        """Each book page whose obligations a failed scenario covers, and what that scenario reported, pages in path order.

        Only a failure the book's writer can fix is reported. A check whose precondition page arranged
        it wrong is reported once per signature, on that precondition's page, naming the pages whose
        requests failed on it, and a check another party must fix is left to its escalation. A check made for one claim is reported on that claim's page alone, naming its node. A scenario
        stopped inside the compiled *plan_source* is reported at the obligation it stopped in, and on
        that obligation's page the problem names its node. A journey stopped at a step is also
        reported on the page of the node that step performs, which the scenario covers no claim of.
        """
        pages_by_scenario = {scenario.id: scenario.pages for scenario in scenarios}
        grouped: dict[str, list[PageProblem]] = {}
        requests = self._requests_by_precondition()
        for signature in self.signatures:
            if signature.cause is Cause.ARRANGEMENT and signature.precondition:
                problem = _arrangement_problem(signature, requests.get(signature.precondition, ()))
                grouped.setdefault(signature.precondition, []).append(problem)
        for name in self.failed_scenarios:
            outcome = self.scenarios[name]
            if not outcome.fails_the_book:
                continue
            claimed = _claimed_problems(name, outcome)
            for problem in claimed:
                grouped.setdefault(problem.page, []).append(problem)
            lines = outcome.unclaimed_failure_lines() or (() if claimed else (outcome.status,))
            if not lines:
                continue
            claim = outcome.failed_claim(plan_source)
            failure_prefix = f"the run of scenario {name} failed at {claim}" if claim else f"the run of scenario {name} failed"
            pages = pages_by_scenario.get(name, ())
            claim_page = obligation_page(claim)
            if claim_page and claim_page not in pages:
                pages = (*pages, claim_page)
            for page in pages:
                node = obligation_node(claim) if obligation_page(claim) == page else ""
                grouped.setdefault(page, []).extend(PageProblem(page, f"{failure_prefix}: {line}", node=node) for line in lines)
        return {page: tuple(grouped[page]) for page in sorted(grouped)}

    def _requests_by_precondition(self) -> dict[str, tuple[str, ...]]:
        """Each precondition page, and the pages of the claims whose checks failed on what it arranges, in path order."""
        found: dict[str, set[str]] = {}
        for outcome in self.scenarios.values():
            for check in outcome.failed_checks:
                page = obligation_page(check.claim)
                if check.cause is Cause.ARRANGEMENT and check.precondition and page and page != check.precondition:
                    found.setdefault(check.precondition, set()).add(page)
        return {precondition: tuple(sorted(pages)) for precondition, pages in found.items()}


def _claimed_problems(name: str, outcome: ScenarioOutcome) -> list[PageProblem]:
    """Each check of scenario *name* made for one claim, as a problem on that claim's page naming its node."""
    return [PageProblem(obligation_page(check.claim),
                        f"the run of scenario {name} failed at {check.claim}: {check.failure_line()}",
                        node=obligation_node(check.claim))
            for check in outcome.book_checks if check.claim]


def _arrangement_problem(signature: Signature, requests: tuple[str, ...]) -> PageProblem:
    """Every check one precondition arranged wrong, as one problem on the precondition's page that names the pages whose requests failed on it."""
    return PageProblem(
        signature.precondition,
        f"{signature.count} checks failed on what this page arranges ({signature.text()}); for example {signature.sample}",
        requests=requests,
    )


_SCENARIOS = TypeAdapter(tuple[Scenario, ...])


def spec_dir(run_dir: Path) -> Path:
    return run_dir / SPEC_DIR


def compile_book(root: Path, services: Iterable[str], spec: Path) -> BookCompilation:
    """Compile every obligation the services' books state, and write the plan when one compiled."""
    compiled = compile_services(root, services, spec)
    if compiled.plan is None:
        return compiled
    _ = (spec / PLAN_NAME).write_text(compiled.plan.source, encoding="utf-8")
    for name, text in compiled.plan.files.items():
        target = spec / name
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_text(text, encoding="utf-8")
    return compiled


_PlanKey = tuple[Path, Path, str, tuple[int, int]]
_LOADED: dict[_PlanKey, tuple[PlanDocument | None, tuple[str, ...]]] = {}


def _plan_key(root: Path, spec: Path) -> _PlanKey:
    plan, context = spec / PLAN_NAME, spec / CONTEXT_FILE
    digest = hashlib.sha256(plan.read_bytes()).hexdigest() if plan.is_file() else ""
    stamp = (context.stat().st_mtime_ns, context.stat().st_size) if context.is_file() else (0, -1)
    return root.resolve(), spec.resolve(), digest, stamp


def loaded_plan(root: Path, spec: Path) -> tuple[PlanDocument | None, tuple[str, ...]]:
    """The compiled plan in `spec` for the app at `root`, or the problems that stop it from loading.

    Loading describes the plan in a subprocess, which costs seconds. The last plan loaded is kept,
    so a check that picks its scenarios and then runs them describes the plan once, until the
    plan or its context is written again.
    """
    key = _plan_key(root, spec)
    if key not in _LOADED:
        document, problems = load_plan(spec / PLAN_NAME, spec, root)
        _LOADED.clear()
        _LOADED[key] = (document, tuple(problems))
    return _LOADED[key]


def plan_scenarios(root: Path, spec: Path) -> tuple[tuple[Scenario, ...], tuple[str, ...]]:
    """The compiled plan's scenarios, or the problems that stop the plan from loading."""
    document, problems = loaded_plan(root, spec)
    if document is None:
        return (), problems
    return _SCENARIOS.validate_python(document.data.get("scenarios", [])), problems


class Selection(BaseModel):
    """The scenarios some target pages name, and the targets that name none."""

    model_config = ConfigDict(frozen=True)

    scenarios: tuple[str, ...] = ()
    unmatched: tuple[str, ...] = ()


def select_scenarios(scenarios: Sequence[Scenario], arranging: Mapping[str, Sequence[str]], targets: Sequence[str]) -> Selection:
    """The scenarios that cover each target page, or for a fixture page the first scenario that arranges its fixture."""
    chosen: dict[str, None] = {}
    unmatched: list[str] = []
    for target in targets:
        named = [scenario.id for scenario in scenarios if target in scenario.pages]
        if not named:
            arranged = set(arranging.get(PurePosixPath(target).stem, ()))
            named = [scenario.id for scenario in scenarios if arranged.intersection(scenario.covers)][:1]
        if not named:
            unmatched.append(target)
        chosen.update(dict.fromkeys(named))
    return Selection(scenarios=tuple(chosen), unmatched=tuple(unmatched))


def run_scenarios(root: Path, spec: Path, only: Iterable[str], lap: Path | None = None) -> RunSummary:
    """Run the named scenarios of the compiled plan, all of them when none is named, building each precondition once in the lap *lap* records."""
    document, problems = loaded_plan(root, spec)
    if document is None:
        return RunSummary(status="invalid", problems=problems)
    _status, _message, summary = run_plan(document, root=root, only=list(only) or None, lap=lap)
    return RunSummary.model_validate(summary)


def write_run(run_dir: Path, summary: RunSummary) -> None:
    _ = (run_dir / RUN_NAME).write_text(summary.model_dump_json(indent=2), encoding="utf-8")


def read_run(run_dir: Path) -> RunSummary | None:
    path = run_dir / RUN_NAME
    return RunSummary.model_validate_json(path.read_text(encoding="utf-8")) if path.is_file() else None
