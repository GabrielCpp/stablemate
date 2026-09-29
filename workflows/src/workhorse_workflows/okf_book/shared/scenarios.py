"""Phase 3 as code: compile the whole book into a plan, and read back what running it did.

No agent takes part in compilation. The plan, its context and the run's evidence live under the
run directory, so the book's repo only ever changes through a committed page.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from ostler.qa.plan import load_plan
from ostler.qa.v2 import run_plan
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
    """One check that did not hold: what it asserted, what it expected, and what it observed."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    label: str
    expected: str = ""
    actual: str = ""
    command_ending_text: str = ""
    covers: tuple[str, ...] = ()

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

    def failure_lines(self) -> tuple[str, ...]:
        """Every failed check, then the last line of the run's own message."""
        message_last_line = self.message.strip().splitlines()[-1:]
        return (*(check.failure_line() for check in self.failed_checks), *message_last_line)

    def unclaimed_failure_lines(self) -> tuple[str, ...]:
        """Every failed check made for no one claim, then the last line of the run's own message."""
        message_last_line = self.message.strip().splitlines()[-1:]
        return (*(check.failure_line() for check in self.failed_checks if not check.claim), *message_last_line)

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
    """What running the plan did: its status, each scenario's outcome, and what stopped it."""

    model_config = ConfigDict(frozen=True, extra="ignore", validate_by_name=True, validate_by_alias=True)

    status: str
    scenarios: dict[str, ScenarioOutcome] = {}
    problems: tuple[str, ...] = ()
    runner_errors: tuple[str, ...] = ()
    report_path: str = Field(default="", validation_alias="report")

    @property
    def failed_scenarios(self) -> tuple[str, ...]:
        return tuple(sorted(name for name, outcome in self.scenarios.items() if outcome.status != "passed"))

    def failures_by_page(self, scenarios: Iterable[Scenario], plan_source: str = "") -> dict[str, tuple[PageProblem, ...]]:
        """Each book page whose obligations a failed scenario covers, and what that scenario reported, pages in path order.

        A check made for one claim is reported on that claim's page alone, naming its node. A scenario
        stopped inside the compiled *plan_source* is reported at the obligation it stopped in, and on
        that obligation's page the problem names its node. A journey stopped at a step is also
        reported on the page of the node that step performs, which the scenario covers no claim of.
        """
        pages_by_scenario = {scenario.id: scenario.pages for scenario in scenarios}
        grouped: dict[str, list[PageProblem]] = {}
        for name in self.failed_scenarios:
            outcome = self.scenarios[name]
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


def _claimed_problems(name: str, outcome: ScenarioOutcome) -> list[PageProblem]:
    """Each check of scenario *name* made for one claim, as a problem on that claim's page naming its node."""
    return [PageProblem(obligation_page(check.claim),
                        f"the run of scenario {name} failed at {check.claim}: {check.failure_line()}",
                        node=obligation_node(check.claim))
            for check in outcome.failed_checks if check.claim]


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


def plan_scenarios(root: Path, spec: Path) -> tuple[tuple[Scenario, ...], tuple[str, ...]]:
    """The compiled plan's scenarios, or the problems that stop the plan from loading."""
    document, problems = load_plan(spec / PLAN_NAME, spec, root)
    if document is None:
        return (), tuple(problems)
    return _SCENARIOS.validate_python(document.data.get("scenarios", [])), tuple(problems)


def run_scenarios(root: Path, spec: Path, only: Iterable[str]) -> RunSummary:
    """Run the named scenarios of the compiled plan, all of them when none is named."""
    document, problems = load_plan(spec / PLAN_NAME, spec, root)
    if document is None:
        return RunSummary(status="invalid", problems=tuple(problems))
    _status, _message, summary = run_plan(document, root=root, only=list(only) or None)
    return RunSummary.model_validate(summary)


def write_run(run_dir: Path, summary: RunSummary) -> None:
    _ = (run_dir / RUN_NAME).write_text(summary.model_dump_json(indent=2), encoding="utf-8")


def read_run(run_dir: Path) -> RunSummary | None:
    path = run_dir / RUN_NAME
    return RunSummary.model_validate_json(path.read_text(encoding="utf-8")) if path.is_file() else None
