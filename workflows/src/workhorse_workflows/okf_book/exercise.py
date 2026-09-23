"""Phase 3 as code: compile the whole book into a plan, and read back what running it did.

No agent takes part in compilation. The plan, its context and the run's evidence live under the
run directory, so the book's repo only ever changes through a committed page.
"""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from ostler.qa.plan import load_plan
from ostler.qa.v2 import run_plan
from workhorse_workflows.okf_book.page_check import BookCompilation, compile_services

SPEC_DIR = "spec"
PLAN_NAME = "qa_plan.py"
RUN_NAME = "run-summary.json"


class Scenario(BaseModel):
    """One compiled scenario, and the obligations it covers."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str
    covers: tuple[str, ...] = ()


class ScenarioOutcome(BaseModel):
    """How one scenario ended, as the run reports it."""

    model_config = ConfigDict(frozen=True, extra="ignore", validate_by_name=True, validate_by_alias=True)

    status: str
    assertions: int = 0
    failures: int = 0
    message: str = ""


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
