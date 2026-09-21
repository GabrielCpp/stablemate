"""End-to-end tests for the `qa` flow — the gates, the four loops, and the operator."""
from __future__ import annotations

import json
import logging
import subprocess
from collections import Counter
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from workhorse import inbox
from ostler.qa import stack as qa_stack
from workhorse.artifacts import ArtifactWriter
from workhorse.cli.inbox import INBOX_FILE
from workhorse.pyflow import WorkflowFailed
from workhorse.pyflow import driver as pyflow_driver
from workhorse.pyflow.driver import read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import parse_checkpoint
from workhorse.runner.failure import BackendInvocationError

from ostler import Ostler
from ostler.qa import QaOutcome
from ostler.qa.source_context import SourceRepository

from workhorse_workflows.coder.qa import flow as qa_flow
from workhorse_workflows.coder.qa.flow import Qa
from workhorse_workflows.coder.qa.nodes import qa as qa_nodes
from workhorse_workflows.coder.qa.nodes import regression as regression_nodes
from workhorse_workflows.coder.qa.nodes.qa import QA_SCRATCH_DIRNAME
from workhorse_workflows.coder.shared import okf as okf_nodes
from workhorse_workflows.coder.shared import qa_support
from workhorse_workflows.coder.shared.dev import resolve_impl_context
from workhorse_workflows.qa import evidence as qa_evidence_mod
from workhorse_workflows.qa import runner as qa_runner_mod

STORY = "STORY-1"
EPIC = "EPIC-1"
SPEC_REL = f"docs/specs/{STORY}"
STORY_REL = f"docs/epics/{EPIC}/stories/{STORY}"
CONTEXT_REL = f"{STORY_REL}/context.md"

ESCALATION_NOTE = (
    "STATUS: AWAITING_OPERATOR\n\n"
    "Re-ran the stack twice; the emulator comes up but the suite still cannot reach it.\n"
    "Please confirm which host the suite should dial.\n"
)

RESOLVER_TRIED = (
    "ran `ostler qa run --scenario SC-1` twice — identical connection refused",
    "checked the emulator port in the runbook against the container — they match",
)

EPIC_MD = """---
title: Epic One
status: active
---

# Epic One

## Stories

### STORY-1

- title: Story One
"""

STORY_MD = """---
type: story
---

# Story One

## Dependencies

(none)

## Fixtures

(none)

## Context

Users need a thing.

## Acceptance Criteria

- the thing exists

## Non-Functional Acceptance Criteria

- the thing is fast

## Technical Notes

- the thing is a function

## Implementation Status

- **Status**: Done
"""

API_SERVICE: dict[str, Any] = {
    "repo": "api",
    "path": ".",
    "type": "go",
    "plan_file": "plan-api.md",
}

WEB_SERVICE: dict[str, Any] = {
    "repo": "web",
    "path": ".",
    "type": "web-app",
    "plan_file": "plan-web.md",
}

DRAFT_SCENARIO = "the-thing-exists"

QA_PLAN = '''from ostler_qa import Qa, plan, scenario, target

plan(run_id="qa-story", story="the-story")
api = target("api")


@scenario(target=api, mechanism="live", covers=["ac:1"])
def the_thing_exists(qa: Qa) -> None:
    """The thing exists."""
    qa.check("it exists", True)
'''




RUNBOOK_REL = "docs/features/app/ops/qa-stack.md"

RUNBOOK_MD = """---
type: runbook
title: QA stack
---

# QA stack

- driver: web

## Steps

### serve

- kind: service
- run: true
- health: true
"""


@pytest.fixture
def docs(
    repo: Path,
    write: Callable[[Path, str], Path],
    write_json: Callable[[Path, Any], Path],
) -> Path:
    """The docs repo: one epic, one built story, and the plan the dev phase left behind."""
    write(repo / "docs" / "epics" / EPIC / "epic.md", EPIC_MD)
    write(repo / STORY_REL / "story.md", STORY_MD)
    write(repo / RUNBOOK_REL, RUNBOOK_MD)
    write_json(
        repo / SPEC_REL / "plan-context.json", {"story": STORY, "services": [API_SERVICE]}
    )
    return repo


@pytest.fixture
def web(
    tmp_path: Path,
    docs: Path,
    git: Callable[..., subprocess.CompletedProcess],
    write: Callable[[Path, str], Path],
    write_json: Callable[[Path, Any], Path],
    ambient: dict[str, str],
) -> Path:
    """A real `web` repo that declares a journey suite, and a plan that names it."""
    write_json(
        docs / SPEC_REL / "plan-context.json", {"story": STORY, "services": [WEB_SERVICE]}
    )
    root = tmp_path / "ws"
    path = root / "web"
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    write(path / "agents.yml", "services:\n  web-app: {regression: 'run-journeys'}\n")
    git(path, "add", "-A")
    git(path, "commit", "-qm", "Initial commit")
    write(root / "acme.code-workspace", json.dumps({"folders": [{"name": "web", "path": "web"}]}))
    ambient["workspace_file"] = str(root / "acme.code-workspace")
    return path




class _Ostler:
    """ostler's four QA subcommands and its artifact vetter, scripted at the process edge."""

    def __init__(
        self,
        *,
        fail_runs: int = 0,
        context_invalid: int = 0,
        plan_invalid: int = 0,
        plan_invalid_passes: tuple[int, ...] = (),
        plan_invalid_stuck: bool = False,
        vet_problems: list[str] | None = None,
        blocked_problems: list[str] | None = None,
        block_runs: int = 0,
        scenarios: tuple[dict[str, Any], ...] = (),
    ) -> None:
        self.fail_runs = fail_runs
        self.block_runs = block_runs
        self.scenarios = scenarios
        self.blocked_problems = blocked_problems
        self.context_invalid = context_invalid
        self.plan_invalid = plan_invalid
        self.plan_invalid_passes = plan_invalid_passes
        self.plan_invalid_stuck = plan_invalid_stuck
        self.vet_problems = vet_problems or []
        self.runs = 0
        self.contexts = 0
        self.context_validations = 0
        self.plan_validations = 0
        self.vets = 0
        self.context_args: list[dict[str, Any]] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> _Ostler:
        """Stand in for the `Ostler` the nodes construct, in every module that does."""
        for module in (okf_nodes, qa_nodes, qa_runner_mod, qa_evidence_mod):
            monkeypatch.setattr(module, "Ostler", self._session)
        return self

    def _session(self, root: Path | str | None = None, **kwargs: Any) -> _Session:
        return _Session(self, root, **kwargs)

    def _blocked(self, problems: list[str]) -> QaOutcome:
        return QaOutcome(
            ok=False,
            message="QA run blocked",
            status="blocked",
            data={"status": "blocked", "problems": problems, "notes": "QA run blocked"},
        )

    def write_run(self, spec: Path, status: str) -> None:
        """The artifacts `ostler qa run` leaves behind, which the evidence gate reads."""
        run_id = f"run-{self.runs}"
        qa = spec / "qa"
        qa.mkdir(parents=True, exist_ok=True)
        (qa / "qa-run.ndjson").write_text(
            "".join(json.dumps(record) + "\n" for record in self._assert_records(status)),
            encoding="utf-8",
        )
        (qa / "run-manifest.json").write_text(
            json.dumps({"runId": run_id, "artifacts": []}), encoding="utf-8"
        )
        (spec / "qa-evidence.json").write_text(
            json.dumps(
                {
                    "runId": run_id,
                    "overall": "pass" if status == "passed" else "fail",
                    "qa_run_log": "qa/qa-run.ndjson",
                    "criteria": [],
                    "obligations": [],
                }
            ),
            encoding="utf-8",
        )
        (spec / "qa-report.md").write_text(
            f"# QA report\n\n<!-- run: {run_id} status: {status} -->\n", encoding="utf-8"
        )

    def _assert_records(self, status: str) -> list[dict[str, Any]]:
        """The per-assertion records of this run, labelled by scenario when there are any."""
        scenarios = self.scenarios[min(self.runs, len(self.scenarios)) - 1] if self.scenarios else {}
        if not scenarios:
            results = ["PASS", "PASS"] if status == "passed" else ["PASS", "FAIL"]
            return [{"kind": "assert", "result": r} for r in results]
        return [
            {
                "kind": "assert",
                "id": f"{name}-{n}",
                "scenario": name,
                "result": "FAIL" if n <= int(outcome.get("failures", 0)) else "PASS",
            }
            for name, outcome in scenarios.items()
            for n in range(1, int(outcome.get("assertions", 1)) + 1)
        ]



class _Session(Ostler):
    """One `Ostler(...)` a node constructed, answering out of the script it was given."""

    def __init__(self, script: _Ostler, root: Path | str | None = None, **kwargs: Any) -> None:
        super().__init__(root, **kwargs)
        self.script = script


    def qa_context(
        self,
        *,
        base: str,
        spec: str | Path,
        head: str = "WORKTREE",
        source_roots: dict[str, list[str]] | None = None,
        features_root: str = "",
        story_file: str | Path | None = None,
        exclude_paths: Iterable[str] = (),
        repositories: Iterable[SourceRepository] = (),
    ) -> QaOutcome:
        self.script.contexts += 1
        self.script.context_args.append(
            {
                "base": base,
                "head": head,
                "story_file": str(story_file or ""),
                "source_roots": dict(source_roots or {}),
                "exclude_paths": list(exclude_paths),
            }
        )
        spec_dir = Path(spec)
        spec_dir.mkdir(parents=True, exist_ok=True)
        (spec_dir / "qa-okf-context.json").write_text(
            json.dumps({"status": "passed", "obligations": [], "verificationIndex": []}),
            encoding="utf-8",
        )
        return QaOutcome(ok=True, message=f"wrote {spec_dir}", data={"status": "passed"})

    def qa_context_validate(self, *, spec: str | Path) -> QaOutcome:
        self.script.context_validations += 1
        if self.script.context_validations <= self.script.context_invalid:
            return QaOutcome(
                ok=False,
                message="context is invalid",
                status="invalid",
                data={"notes": "two changed files map to no feature node"},
            )
        return QaOutcome(ok=True, message="Context is valid.", data={"problems": []})


    def qa_validate(
        self, plan_file: str | Path, *, spec: str | Path | None = None
    ) -> QaOutcome:
        self.script.plan_validations += 1
        assert Path(plan_file).is_file(), f"the plan turn wrote no {plan_file}"
        if (
            self.script.plan_validations <= self.script.plan_invalid
            or self.script.plan_validations in self.script.plan_invalid_passes
        ):
            step = 3 if self.script.plan_invalid_stuck else self.script.plan_validations
            return QaOutcome(
                ok=False,
                message="plan is invalid",
                status="invalid",
                data={"notes": f"step {step} names no assertion"},
            )
        return QaOutcome(ok=True, message="Plan is valid.", data={})


    def qa_run(
        self,
        plan_file: str | Path,
        *,
        spec: str | Path | None = None,
        stop_on_fail: bool = False,
        only: list[str] | None = None,
        label: str | None = None,
    ) -> QaOutcome:
        script = self.script
        script.runs += 1
        if script.runs <= script.block_runs:
            return script._blocked(["target 'web' requires the Playwright Python package"])
        if script.blocked_problems is not None:
            return script._blocked(list(script.blocked_problems))
        status = "failed" if script.runs <= script.fail_runs else "passed"
        script.write_run(Path(str(spec)), status)
        data: dict[str, Any] = {
            "status": status,
            "notes": f"run {script.runs} reported {status}",
        }
        if script.scenarios:
            data["scenarios"] = script.scenarios[min(script.runs, len(script.scenarios)) - 1]
        return QaOutcome(ok=status == "passed", message=str(data["notes"]), data=data,
                         status=status)


    def artifact_vet(self, kind: str, spec: str | Path) -> QaOutcome:
        self.script.vets += 1
        problems = list(self.script.vet_problems)
        status = "problems" if problems else "clean"
        return QaOutcome(
            ok=not problems,
            message="\n".join(problems) or f"{kind}: clean",
            status=status,
            data={"kind": kind, "path": str(spec), "status": status, "problems": problems},
        )


@pytest.fixture
def ostler(monkeypatch: pytest.MonkeyPatch) -> Callable[..., _Ostler]:
    """Install a scripted ostler; the default one passes every gate it is asked about."""

    def _install(**kwargs: Any) -> _Ostler:
        return _Ostler(**kwargs).install(monkeypatch)

    return _install


class _Suite:
    """The declared journey command, scripted."""

    def __init__(self, *, fail_runs: int = 0) -> None:
        self.fail_runs = fail_runs
        self.calls: list[str] = []

    def __call__(self, command: str, cwd: Path, timeout: int) -> regression_nodes._Outcome:
        self.calls.append(command)
        if len(self.calls) <= self.fail_runs:
            return regression_nodes._Outcome(1, "FAIL journeys/login.spec.ts › logs a user in\n")
        return regression_nodes._Outcome(0, "12 passed\n")




class _Agent:
    """The flow's eleven prompts, scripted on the axes its states branch on."""

    def __init__(
        self,
        docs: Path,
        *,
        repair: str = "repaired",
        disposition: str = "confirmed",
        repair_plans: int = 0,
        failure_class: str = "none",
        objective: bool = True,
        assessment_class: str = "none",
        assessment_findings: list[dict[str, str]] | None = None,
        audit: tuple[str, str] = ("stands", "none"),
        audit_findings: list[dict[str, str]] | None = None,
        triage: tuple[str, str] = ("qa_fix", "code"),
        setup: str = "ready",
        qa_fix: str = "passed",
        escalate: bool = False,
        scope: str = "story",
        explode: set[str] | None = None,
        cut: set[str] | None = None,
        dry_run: str = "passed",
        plan_dry_run: str = "passed",
        plan_proves: tuple[str, ...] = (DRAFT_SCENARIO,),
        item_dry_run: str | tuple[str, ...] = "passed",
        refuses: set[str] | None = None,
    ) -> None:
        self.docs = docs
        self.dry_run = dry_run
        self.plan_dry_run = plan_dry_run
        self.plan_proves = plan_proves
        self.item_dry_run = (
            (item_dry_run,) if isinstance(item_dry_run, str) else item_dry_run
        )
        self.repair = repair
        self.disposition = disposition
        self.repair_plans = repair_plans
        self.failure_class = failure_class
        self.objective = objective
        self.assessment_class = assessment_class
        self.assessment_findings = assessment_findings or []
        self.audit = audit
        self.audit_findings = audit_findings or []
        self.triage = triage
        self.setup = setup
        self.qa_fix = qa_fix
        self.escalate = escalate
        self.scope = scope
        self.explode = explode or set()
        self.cut = cut or set()
        self.refuses = refuses or set()
        self.calls: list[str] = []
        self.args: list[dict[str, Any]] = []
        self.dirs: list[list[str]] = []
        self.powers: list[str | None] = []


    PLAN_STEMS = ("plan-qa", "repair-qa-plan")

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        stem = Path(node.prompt).stem
        data = ctx.as_dict()
        self.calls.append(stem)
        self.args.append(data)
        self.dirs.append(list(node.add_dirs or []))
        self.powers.append(node.power)
        if stem in self.explode:
            raise RuntimeError(f"killed during {stem}")
        nth = self.planned() if stem in self.PLAN_STEMS else self.counts()[stem]
        if stem in self.refuses:
            answer: dict[str, Any] = {
                "status": "blocked",
                "notes": f"{stem} needs a credential this run does not hold (pass {nth})",
            }
        else:
            handler = getattr(self, f"_{stem.replace('-', '_')}")
            answer = handler(data, nth)
        if stem in self.cut:
            raise BackendInvocationError(f"timed out after {node.timeout}s", timed_out=True)
        return f"(scripted) {node.prompt}", answer

    def counts(self) -> Counter[str]:
        return Counter(self.calls)

    def planned(self) -> int:
        """How many plan-authoring turns have run, across the draft and every repair."""
        return sum(self.counts()[stem] for stem in self.PLAN_STEMS)

    def args_for(self, stem: str) -> list[dict[str, Any]]:
        return [a for s, a in zip(self.calls, self.args, strict=True) if s == stem]

    def powers_for(self, stem: str) -> list[str | None]:
        return [p for s, p in zip(self.calls, self.powers, strict=True) if s == stem]

    def plan_args(self) -> list[dict[str, Any]]:
        """Every plan turn's brief in order, whichever of its two prompts served it."""
        return [a for s, a in zip(self.calls, self.args, strict=True) if s in self.PLAN_STEMS]

    def fix_args(self) -> list[dict[str, Any]]:
        """Every unaided lap of the code-fix loop, whichever fixer prompt served it."""
        return [
            a
            for s, a in zip(self.calls, self.args, strict=True)
            if s == "fix-qa-scenario"
            or (s == "apply-qa-fixes" and "operator_feedback" not in a)
        ]


    def _repair_qa_context(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """One key: did the packet heal?"""
        return {
            "status": self.repair,
            "notes": f"the diff touches code no feature node owns (pass {nth})",
        }

    def _plan_qa(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """The draft, and the proof of the scenarios it nominated as its riskiest."""
        (Path(data["spec_dir"]) / "qa_plan.py").write_text(QA_PLAN, encoding="utf-8")
        for scenario in self.plan_proves:
            self._prove(data, scenario, self.plan_dry_run)
        return {
            "status": "done",
            "notes": f"plan pass {nth}",
            "proved_scenarios": list(self.plan_proves),
        }

    def _prove(self, data: dict[str, Any], scenario: str, shape: str) -> None:
        """Write one scenario's scratch dry-run log, in whichever of the four shapes."""
        if shape == "missing":
            return
        out = Path(data["spec_dir"]) / QA_SCRATCH_DIRNAME / scenario
        out.mkdir(parents=True, exist_ok=True)
        records = [] if shape == "empty" else [
            {"kind": "assert", "id": f"{scenario}-1", "result": (
                "FAIL" if shape == "failed" else "PASS"
            )}
        ]
        (out / qa_support.QA_RUN_LOG).write_text(
            "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8"
        )

    def _repair_qa_plan(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """The repair turn rewrites the plan *and* proves it, exactly as its prompt demands."""
        (Path(data["spec_dir"]) / "qa_plan.py").write_text(QA_PLAN, encoding="utf-8")
        scenarios = [str(s["id"]) for s in data.get("failed_scenarios") or []]
        for scenario in scenarios:
            self._prove(data, scenario, self.dry_run)
        return {
            "status": "done",
            "notes": f"plan pass {nth}",
            "repaired_scenarios": scenarios,
        }

    def _qa_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        failed = data["runner_status"] == "failed"
        plan_lap = failed and nth <= self.repair_plans
        return {
            "status": "assessed",
            "disposition": "repair_plan" if plan_lap else self.disposition,
            "failure_class": ("plan" if plan_lap else self.assessment_class)
            if failed
            else self.failure_class,
            "objective_reached": False if failed else self.objective,
            "findings": self.assessment_findings,
            "notes": f"assessment pass {nth}",
        }

    def _audit_qa(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        verdict, refutation = self.audit
        return {
            "status": "audited",
            "verdict": verdict,
            "refutation_class": refutation,
            "findings": self.audit_findings,
            "notes": f"audit pass {nth}",
        }

    def _triage_qa(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        action, failure_class = self.triage
        return {
            "status": "triaged",
            "triage_action": action,
            "qa_failure_class": failure_class,
        }

    def _apply_qa_fixes(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return {"status": self.qa_fix, "notes": f"fix pass {nth}"}

    def _fix_qa_scenario(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """One scenario's fixer, which proves its own item exactly as its prompt demands."""
        scenario = str(data["scenario"])
        self._prove(data, scenario, self.item_dry_run[min(nth, len(self.item_dry_run)) - 1])
        return {"status": self.qa_fix, "notes": f"scenario {scenario} pass {nth}"}

    def _fix_regression(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return {"status": "attempted", "notes": f"regression fix pass {nth}"}

    def _setup_fix(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return {"status": self.setup, "notes": f"setup pass {nth}"}

    def _report_qa_dev(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return {"status": "reported", "notes": "filed with the upstream tracker"}

    def _report_qa_dev_pass(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return {"status": "reported", "notes": "told the tracker it passed"}

    def _resolve_operator(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if self.escalate:
            self._escalate()
            return {
                "decision": "escalated",
                "summary": "only a person can decide this",
                "tried": list(RESOLVER_TRIED),
            }
        self._answer()
        return {
            "decision": "answered",
            "summary": "use the staging bucket",
            "grounded": ["docs/decisions/which-bucket.md:3 — 'QA writes go to the staging bucket'"],
            "record": "which-bucket",
        }

    def _answer(self) -> None:
        """Write the answer where `read_operator_context` reads it back out of."""
        (self.docs / CONTEXT_REL).write_text(
            f"STATUS: ANSWERED\nSCOPE: {self.scope}\n\nUse the staging bucket.\n",
            encoding="utf-8",
        )

    def _escalate(self) -> None:
        """An escalating resolver writes its note into the same file, it does not write nothing."""
        (self.docs / CONTEXT_REL).write_text(ESCALATION_NOTE, encoding="utf-8")





def _answers(seen: list[str], *, scope: str = "story") -> Callable[..., None]:
    """A stand-in for the human an `Await` is waiting on, patched over `wait_for_answer`."""

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text(encoding="utf-8"))
        path.write_text(
            f"STATUS: ANSWERED\nSCOPE: {scope}\n\nUse the staging bucket.\n", encoding="utf-8"
        )

    return answered


class _Parked(Exception):
    """Raised by the patched `wait_for_answer` to stop a run right at its `Await`."""


def _parked_at(seen: list[str]) -> Callable[..., None]:
    """Capture the escalation body the `Await` wrote, then stop the run there."""

    def stop(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text(encoding="utf-8"))
        raise _Parked

    return stop


def _output(run_env: RunEnv, node: Any) -> dict[str, Any]:
    """A node's recorded output — the artifact, not the return value the flow saw."""
    path = run_env.writer.run_dir / node.__name__ / "output.json"
    return json.loads(path.read_text(encoding="utf-8"))




def test_one_clean_pass_through_every_gate(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Context, plan, run, evidence, audit, sentinels — all first try, no assessment."""
    okf = ostler()
    agent = _Agent(docs)
    run_env = env()

    result = drive_flow(Qa(story=STORY), run_env, agent)

    assert result.status == "passed", result
    assert result.qa_rework == 0
    assert result.docs_recheck_required is False
    assert agent.counts() == {
        "plan-qa": 1,
        "audit-qa": 1,
    }, agent.counts()
    assert agent.planned() == 1, agent.counts()
    assert (okf.contexts, okf.runs, okf.vets) == (1, 1, 1)
    assert (docs / SPEC_REL / "qa-evidence.json").is_file()
    assert (docs / SPEC_REL / "qa" / "qa-run.ndjson").is_file()


def test_a_story_that_cannot_be_resolved_fails_the_run_without_spending_a_turn(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """An unresolvable story is a defect in whatever asked for this slug, and fails as one."""
    okf = ostler()
    agent = _Agent(docs)

    with pytest.raises(WorkflowFailed, match="no story path"):
        drive_flow(Qa(story="", triage_scope=1), env(), agent)

    assert agent.calls == []
    assert (okf.contexts, okf.runs) == (0, 0)


def test_every_agent_turn_is_granted_only_the_repos_the_plan_touches(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The port's one deliberate `add_dirs` divergence, asserted off the node the engine built."""
    ostler()
    agent = _Agent(docs)
    run_env = env()

    drive_flow(Qa(story=STORY), run_env, agent)

    expected = _output(run_env, resolve_impl_context)["affected_repo_paths"]
    assert expected == [str(docs)], expected
    assert agent.dirs == [expected] * len(agent.calls), agent.dirs




def test_an_unmappable_packet_is_repaired_and_rebuilt(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """One repair spends one context rework and rejoins at `build_context`."""
    okf = ostler(context_invalid=1)
    agent = _Agent(docs, repair="repaired")

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert result.docs_recheck_required is True
    assert agent.counts()["repair-qa-context"] == 1, agent.counts()
    assert agent.powers_for("repair-qa-context") == ["low"]
    assert okf.contexts == 2, okf.contexts
    assert "no feature node" in agent.args_for("repair-qa-context")[0]["context_notes"]


def test_a_gate_that_passed_hands_the_plan_turn_no_diagnostics(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A pass is not a finding, so it must not reach `plan_qa` as one."""
    ostler(context_invalid=1)
    agent = _Agent(docs, repair="repaired")

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    plan_args = agent.args_for("plan-qa")[0]
    assert plan_args["context_status"] == "passed", plan_args
    assert plan_args["context_notes"] == "", plan_args
    assert all(
        plan_args[key] == ""
        for key in ("plan_validation_notes", "run_assessment_notes", "audit_notes")
    ), plan_args
    assert plan_args["qa_tools"] == [], plan_args


def test_the_context_repair_loop_is_bounded_at_three(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A repairer that claims success on a packet that stays unmappable costs three passes, then escalates — there is no cap on re-escalation, only on the repair loop itself."""
    okf = ostler(context_invalid=9)
    agent = _Agent(docs, repair="repaired", escalate=True)
    seen: list[str] = []

    with (
        patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)),
        pytest.raises(_Parked),
    ):
        drive_flow(Qa(story=STORY), env(), agent)

    assert agent.counts() == {"repair-qa-context": 3, "resolve-operator": 1}, agent.counts()
    assert okf.runs == 0, "the plan was never reached, so nothing should have run"
    assert len(seen) == 1 and "context repair" in seen[0], seen


def test_an_unrepairable_packet_goes_to_the_auto_operator(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`blocked` skips the rework and takes the gate; the answer is applied as a QA fix."""
    ostler(context_invalid=1)
    agent = _Agent(docs, repair="blocked")
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen)):
        result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    assert agent.counts()["apply-qa-fixes"] == 1, agent.counts()
    assert agent.powers_for("apply-qa-fixes") == ["low"]
    assert result.qa_rework == 1
    assert "the diff touches code" in agent.args_for("resolve-operator")[0]["block_notes"]


@pytest.mark.parametrize("operator_mode", ["human", "operator"])
def test_human_operator_modes_wait_on_the_story_context_file(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    operator_mode: str,
) -> None:
    """Canonical `human` and legacy `operator` block on `<story>/context.md`."""
    ostler(context_invalid=1)
    seen: list[str] = []
    agent = _Agent(docs, repair="blocked")

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen)):
        result = drive_flow(Qa(story=STORY, operator_mode=operator_mode), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["resolve-operator"] == 0, agent.counts()
    assert len(seen) == 1 and "the diff touches code" in seen[0], seen


def test_an_epic_scoped_answer_hands_the_story_back_to_replan(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """No amount of QA fixing reaches a wrong premise, so the parent re-derives the epic."""
    ostler(context_invalid=1)
    agent = _Agent(docs, repair="blocked", escalate=True)
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen, scope="epic")):
        result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "replan", result
    assert "staging bucket" in result.operator_notes
    assert agent.counts()["apply-qa-fixes"] == 0, agent.counts()




def test_a_plan_that_never_parses_spends_only_the_schema_budget(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Three schema repairs buy four plan turns and never reach the stack, then escalate."""
    okf = ostler(plan_invalid=9)
    agent = _Agent(docs, escalate=True)
    seen: list[str] = []

    with (
        patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)),
        pytest.raises(_Parked),
    ):
        drive_flow(Qa(story=STORY), env(), agent)

    assert agent.counts() == {
        "plan-qa": 1,
        "repair-qa-plan": 3,
        "resolve-operator": 1,
    }, agent.counts()
    assert okf.runs == 0, "an invalid plan must never be executed"


def test_two_identical_schema_refusals_block_instead_of_buying_a_third_lap(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The lap-discipline rule, on the gate that had only a count bounding it."""
    okf = ostler(plan_invalid=99, plan_invalid_stuck=True)
    agent = _Agent(docs, escalate=True)
    seen: list[str] = []

    with (
        patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)),
        pytest.raises(_Parked),
    ):
        drive_flow(Qa(story=STORY), env(), agent)

    assert agent.counts()["repair-qa-plan"] == 1, agent.counts()
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    assert okf.runs == 0, "the lane never reached the runner"
    assert len(seen) == 1, seen


def test_distinct_schema_refusals_still_spend_the_whole_schema_budget(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The other half of the rule: a lane that is still moving keeps its laps."""
    ostler(plan_invalid=99)
    agent = _Agent(docs, escalate=True)
    seen: list[str] = []

    with (
        patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)),
        pytest.raises(_Parked),
    ):
        drive_flow(Qa(story=STORY), env(), agent)

    assert agent.counts()["repair-qa-plan"] == qa_flow.MAX_PLAN_VALIDATION_REWORKS, agent.counts()


def test_validation_and_judgement_spend_separate_plan_budgets(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Two schema repairs cost the judgement budget nothing."""
    okf = ostler(plan_invalid=2, fail_runs=1)
    agent = _Agent(docs, repair_plans=1)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert okf.runs == 2
    assert okf.plan_validations == 4


def test_the_repair_turn_is_told_which_scenarios_failed_and_on_which_assertions(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The repair's worklist is the failing set itself, not a paragraph describing it."""
    ostler(fail_runs=1, scenarios=(_STUCK, {}))
    agent = _Agent(docs, repair_plans=1)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    brief = agent.args_for("repair-qa-plan")[0]
    assert brief["failed_scenarios"] == [
        {"id": "copy-link", "failed_assertions": ["copy-link-1"]}
    ], brief["failed_scenarios"]


def test_the_first_draft_carries_no_failing_scenarios_and_proves_its_own(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The draft has no *failing* set — but it does have scenarios it nominated and ran."""
    okf = ostler()
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert okf.runs == 1, "a proven draft goes straight to the runner"
    assert agent.args_for("plan-qa")[0]["failed_scenarios"] == []
    assert agent.counts()["repair-qa-plan"] == 0, agent.counts()


def test_a_draft_that_did_not_run_what_it_named_is_repaired_before_any_suite_run(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The lever: the first draft is proof-gated too, and its refusal costs no suite run."""
    okf = ostler()
    agent = _Agent(docs, plan_dry_run="missing")

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.calls[:2] == ["plan-qa", "repair-qa-plan"], agent.calls
    assert okf.runs == 1, "the refusal must not have cost a suite run of its own"


def test_a_draft_whose_named_scenario_dry_ran_red_is_not_a_finished_plan(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The other refusal: it ran, and it failed."""
    okf = ostler()
    agent = _Agent(docs, plan_dry_run="failed")

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["repair-qa-plan"] == 1, agent.counts()
    assert okf.runs == 1, okf.runs


def test_a_draft_that_nominates_nothing_is_not_gated(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A plan with nothing worth proving must still reach the runner."""
    okf = ostler()
    agent = _Agent(docs, plan_dry_run="missing", plan_proves=())

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["repair-qa-plan"] == 0, agent.counts()
    assert okf.runs == 1, okf.runs


def test_a_repair_that_never_dry_ran_is_repaired_again_and_costs_no_suite_run(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The point of the gate: an unproven repair is refused where the refusal is cheap."""
    okf = ostler(fail_runs=99, scenarios=(_STUCK,))
    agent = _Agent(docs, repair_plans=99, escalate=True, dry_run="missing")
    seen: list[str] = []

    with (
        patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)),
        pytest.raises(_Parked),
    ):
        drive_flow(Qa(story=STORY), env(), agent)

    assert okf.runs == 1, "a refused repair must not buy another suite run"
    assert agent.counts()["repair-qa-plan"] > 1, agent.counts()
    assert agent.counts()["repair-qa-plan"] == 2, agent.counts()
    assert len(seen) == 1 and "plan repair" in seen[0], seen


def test_a_repair_whose_dry_run_is_still_red_is_not_a_finished_repair(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The turn ran the scenario and left it failing — which is the answer, honestly come by, and still not a repair."""
    okf = ostler(fail_runs=99, scenarios=(_STUCK,))
    agent = _Agent(docs, repair_plans=99, escalate=True, dry_run="failed")
    seen: list[str] = []

    with (
        patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)),
        pytest.raises(_Parked),
    ):
        drive_flow(Qa(story=STORY), env(), agent)

    assert okf.runs == 1, okf.runs
    brief = agent.args_for("repair-qa-plan")[1]
    assert "still fails" in brief["plan_validation_notes"], brief["plan_validation_notes"]


def test_a_plan_turn_cut_at_its_budget_is_repaired_rather_than_failing_the_run(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """An overrun `plan-qa` lands on the repair lane, because its deliverable is a file."""
    ostler(plan_invalid=1)
    agent = _Agent(docs, cut={"plan-qa"})

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["repair-qa-plan"] == 1, agent.counts()
    brief = agent.args_for("repair-qa-plan")[0]
    assert "stopped at its wall-clock budget" in brief["plan_validation_notes"], brief


def test_a_plan_lane_past_its_wall_clock_budget_carries_on(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A spent wall-clock budget is advisory: the lane behaves exactly as if it had room."""
    okf = ostler()
    agent = _Agent(docs)

    with patch.object(qa_flow, "PLAN_LANE_BUDGET_S", 0):
        result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["repair-qa-plan"] == 0, agent.counts()
    assert okf.runs == 1, "the plan is still the one that ran"


def test_a_plan_lane_past_its_budget_still_repairs_a_plan_that_will_not_import(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Past the budget with a plan that will not import, the schema repairs still run."""
    ostler(plan_invalid=99)
    agent = _Agent(docs, escalate=True)
    seen: list[str] = []

    with (
        patch.object(qa_flow, "PLAN_LANE_BUDGET_S", 0),
        patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)),
        pytest.raises(_Parked),
    ):
        drive_flow(Qa(story=STORY), env(), agent)

    assert agent.counts()["repair-qa-plan"] == qa_flow.MAX_PLAN_VALIDATION_REWORKS, agent.counts()


def test_a_context_rebuild_past_the_plan_budget_still_authors_against_it(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The join point is an entry into the plan lane, bounded by `MAX_CONTEXT_REWORKS`."""
    okf = ostler(fail_runs=1)
    agent = _Agent(docs, assessment_class="product")

    with patch.object(qa_flow, "PLAN_LANE_BUDGET_S", 0):
        result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["apply-qa-fixes"] == 1, agent.counts()
    assert agent.planned() == 1, "the plan still validating against the rebuilt packet is adopted"
    assert okf.runs == 2, agent.counts()


def test_a_spent_plan_budget_after_the_run_still_repairs_the_failing_plan(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Reached from `_guard_plan`, a spent clock no longer skips `repair_plan`."""
    ostler(fail_runs=99)
    agent = _Agent(docs, repair_plans=99, escalate=True)
    seen: list[str] = []

    with (
        patch.object(qa_flow, "PLAN_LANE_BUDGET_S", 0),
        patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)),
        pytest.raises(_Parked),
    ):
        drive_flow(Qa(story=STORY), env(), agent)

    assert agent.counts()["repair-qa-plan"] == qa_flow.MAX_PLAN_REWORKS, agent.counts()
    assert len(seen) == 1 and "plan repair" in seen[0], seen


def test_only_the_first_draft_is_authored_and_every_lap_after_it_repairs(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Both guards land on `repair_plan`, whichever of them fired."""
    ostler(plan_invalid_passes=(1, 3), fail_runs=1)
    agent = _Agent(docs, repair_plans=1)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["plan-qa"] == 1, agent.counts()
    assert agent.counts()["repair-qa-plan"] == 3, agent.counts()
    assert agent.calls[0] == "plan-qa", agent.calls


def test_a_plan_loop_that_never_converges_escalates_with_the_refusal_that_spent_it(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The gate's diagnosis reaches the escalation, not just an aggregate attempt count."""
    ostler(fail_runs=99)
    agent = _Agent(docs, repair_plans=99, escalate=True)
    seen: list[str] = []

    with (
        patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)),
        pytest.raises(_Parked),
    ):
        drive_flow(Qa(story=STORY), env(), agent)

    assert not (docs / SPEC_REL / "qa.md").exists(), "there is no give-up marker to write"
    assert len(seen) == 1 and "plan repair" in seen[0], seen




def test_the_stack_is_standing_before_the_plan_is_written(
    docs: Path,
    ostler: Callable[..., _Ostler],
    write: Callable[[Path, str], Path],
    monkeypatch: pytest.MonkeyPatch,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The reorder, stated as the thing the planner can rely on."""
    ostler()
    agent = _Agent(docs)
    turns_before: list[int] = []

    def _up(*a: Any, **k: Any) -> dict[str, Any]:
        turns_before.append(len(agent.calls))
        return {"ready": "yes", "entry_url": "http://x"}

    monkeypatch.setattr(qa_stack, "ensure_stack", _up)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert turns_before == [0], (turns_before, agent.calls)
    assert agent.calls[0] == "plan-qa", agent.calls
    assert agent.planned() == 1, agent.counts()


def test_an_empty_manifest_splits_on_whether_the_book_serves_anything(
    docs: Path,
    write: Callable[[Path, str], Path],
) -> None:
    """`ensure_stack` reads the topology, not just the manifest, before calling it a gap."""
    log = logging.getLogger("test")
    (docs / RUNBOOK_REL).unlink()

    status = qa_nodes.ensure_stack(log, str(docs))
    assert status.ready == "unneeded", status
    assert "serves nothing" in status.notes

    write(
        docs / "docs" / "features" / "app" / "server.md",
        "---\ntype: server\ntitle: App server\n---\n\n# App server\n",
    )
    status = qa_nodes.ensure_stack(log, str(docs))
    assert status.ready == "none", status
    assert "served surface" in status.notes


def _stack_runbook(root: Path, write: Callable[[Path, str], Path], *, name: str, port: int,
                   env_href: str = "") -> None:
    """A second stack runbook under `app/ops`, distinct from the `docs` fixture's own."""
    environment = f"- environment: [{env_href}]({env_href}.md)\n" if env_href else ""
    write(
        root / "docs" / "features" / "app" / "ops" / f"{name}.md",
        f"---\ntype: runbook\ntitle: {name}\n---\n\n# {name}\n\n- driver: web\n"
        f"- entry-url: http://localhost:{port}\n{environment}\n"
        "## Steps\n\n### serve\n\n- kind: service\n- run: true\n- health: true\n",
    )


def test_a_refusal_says_what_the_book_declares_not_to_author_one(
    docs: Path,
    write: Callable[[Path, str], Path],
) -> None:
    """Several stack runbooks and no name given is a refusal, not an absence."""
    log = logging.getLogger("test")
    write(
        docs / "docs" / "features" / "app" / "server.md",
        "---\ntype: server\ntitle: App server\n---\n\n# App server\n",
    )
    _stack_runbook(docs, write, name="second-stack", port=2222)

    status = qa_nodes.ensure_stack(log, str(docs))

    assert status.ready == "none", status
    assert "Author the runbook" not in status.notes
    assert "qa-stack" in status.notes or "second-stack" in status.notes


def test_a_shared_environment_brings_both_runbooks_up_together(
    docs: Path,
    write: Callable[[Path, str], Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two stack runbooks bound to one `environment:` node have a manifest each, not none."""
    log = logging.getLogger("test")
    write(
        docs / "docs" / "features" / "app" / "server.md",
        "---\ntype: server\ntitle: App server\n---\n\n# App server\n",
    )
    write(
        docs / "docs" / "features" / "app" / "ops" / "local.md",
        "---\ntype: environment\ntitle: local\n---\n\n# local\n\n- local-only: true\n",
    )
    write(
        docs / RUNBOOK_REL,
        "---\ntype: runbook\ntitle: QA stack\n---\n\n# QA stack\n\n- driver: web\n"
        "- environment: [local](local.md)\n\n"
        "## Steps\n\n### serve\n\n- kind: service\n- run: true\n- health: true\n",
    )
    _stack_runbook(docs, write, name="second-stack", port=2222, env_href="local")

    calls: list[str] = []

    def _up(manifest: dict[str, Any], *, repo_root: str, logger: logging.Logger) -> dict[str, Any]:
        calls.append(manifest["source"])
        return {"ready": "yes", "entry_url": manifest.get("entry_url", "http://x")}

    monkeypatch.setattr(qa_stack, "ensure_stack", _up)

    status = qa_nodes.ensure_stack(log, str(docs))

    assert status.ready == "yes", status
    assert len(calls) == 2, calls
    assert "(2 services)" in status.notes, status.notes


def test_a_book_that_serves_nothing_runs_qa_without_a_stack(
    docs: Path,
    ostler: Callable[..., _Ostler],
    write: Callable[[Path, str], Path],
    monkeypatch: pytest.MonkeyPatch,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """An artifact-only book proceeds straight to planning — no fixer, no gate, no boot."""
    ostler()
    (docs / RUNBOOK_REL).unlink()

    def _boom(*a: Any, **k: Any) -> dict[str, Any]:
        raise AssertionError("there is no manifest, so nothing may try to bring one up")

    monkeypatch.setattr(qa_stack, "ensure_stack", _boom)
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert "setup-fix" not in agent.counts(), agent.counts()
    assert agent.calls[0] == "plan-qa", agent.calls


def test_a_setup_repair_mid_run_returns_to_the_runner_not_to_a_second_plan(
    docs: Path,
    ostler: Callable[..., _Ostler],
    write: Callable[[Path, str], Path],
    monkeypatch: pytest.MonkeyPatch,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`plan_authored`: `stack` is two entries, and only one of them authors."""
    okf = ostler(block_runs=1)
    monkeypatch.setattr(
        qa_stack, "ensure_stack", lambda *a, **k: {"ready": "yes", "entry_url": "http://x"}
    )
    agent = _Agent(docs, setup="ready")

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["setup-fix"] == 1, agent.counts()
    assert okf.runs == 2, "the repaired run was never retried"
    assert agent.planned() == 1, agent.counts()


def test_a_stack_that_will_not_come_up_is_repaired_and_retried(
    docs: Path,
    ostler: Callable[..., _Ostler],
    write: Callable[[Path, str], Path],
    monkeypatch: pytest.MonkeyPatch,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`ensure_stack` reaches docker, so docker is the seam and the manifest is real."""
    ostler()
    results = [{"ready": "no", "failed_step": "health"}, {"ready": "yes", "entry_url": "http://x"}]
    monkeypatch.setattr(qa_stack, "ensure_stack", lambda *a, **k: results.pop(0))
    agent = _Agent(docs, setup="ready")

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert result.docs_recheck_required is True
    assert agent.counts()["setup-fix"] == 1, agent.counts()
    assert results == [], "the stack was never brought up a second time"
    assert "stack_manifest" not in agent.args_for("setup-fix")[0]


def test_the_setup_fixer_is_briefed_with_why_the_stack_would_not_come_up(
    docs: Path,
    ostler: Callable[..., _Ostler],
    write: Callable[[Path, str], Path],
    monkeypatch: pytest.MonkeyPatch,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A stack failure is the running verdict, so the failing step's message reaches the fixer."""
    ostler()
    results = [
        {"ready": "no", "failed_step": "health[0]", "error": "api-test container is not running"},
        {"ready": "yes", "entry_url": "http://x"},
    ]
    monkeypatch.setattr(qa_stack, "ensure_stack", lambda *a, **k: results.pop(0))
    agent = _Agent(docs, setup="ready")

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    notes = agent.args_for("setup-fix")[0]["qa_notes"]
    assert "health[0]" in notes
    assert "api-test container is not running" in notes


def test_a_stack_nobody_can_repair_gives_up_instead_of_spinning(
    docs: Path,
    ostler: Callable[..., _Ostler],
    write: Callable[[Path, str], Path],
    monkeypatch: pytest.MonkeyPatch,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The YAML cycle with no terminal — the ledger's C3 finding — never gets a give-up either."""
    ostler()
    monkeypatch.setattr(
        qa_stack, "ensure_stack", lambda *a, **k: {"ready": "no", "failed_step": "health"}
    )
    monkeypatch.setenv("WORKHORSE_MAX_TRANSITIONS", "60")
    agent = _Agent(docs, setup="unfixable")
    seen: list[str] = []

    with (
        patch.object(pyflow_driver, "wait_for_answer", _answers(seen)),
        pytest.raises(WorkflowFailed, match="transition budget exhausted"),
    ):
        drive_flow(Qa(story=STORY), env(), agent)

    assert agent.counts()["setup-fix"] == qa_flow.MAX_SETUP_REWORKS, agent.counts()
    assert agent.counts()["resolve-operator"] > 1, agent.counts()
    assert all("setup repair" in body for body in seen), seen


def test_a_setup_fix_that_changes_nothing_is_not_asked_a_second_time(
    docs: Path,
    ostler: Callable[..., _Ostler],
    monkeypatch: pytest.MonkeyPatch,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """An identical blocked bundle is an operator question, not another repair attempt."""
    ostler(blocked_problems=["target 'web' requires the Playwright Python package"])
    monkeypatch.setenv("WORKHORSE_MAX_TRANSITIONS", "60")
    agent = _Agent(docs, setup="ready", escalate=True)
    seen: list[str] = []

    with (
        patch.object(pyflow_driver, "wait_for_answer", _answers(seen)),
        pytest.raises(WorkflowFailed, match="transition budget exhausted"),
    ):
        drive_flow(Qa(story=STORY), env(), agent)

    counts = agent.counts()
    assert counts["setup-fix"] == 1, counts
    assert counts["setup-fix"] < qa_flow.MAX_SETUP_REWORKS, counts
    assert counts["resolve-operator"] > 1, counts
    assert len(seen) > 1, "the identical bundle must escalate more than once"


def test_a_packet_that_stays_unmappable_bounds_the_operator_gate(
    docs: Path,
    ostler: Callable[..., _Ostler],
    monkeypatch: pytest.MonkeyPatch,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The same hole, entered from the context loop rather than the stack loop."""
    ostler(context_invalid=99)
    monkeypatch.setenv("WORKHORSE_MAX_TRANSITIONS", "60")
    agent = _Agent(docs, repair="blocked", escalate=True)
    seen: list[str] = []

    with (
        patch.object(pyflow_driver, "wait_for_answer", _answers(seen)),
        pytest.raises(WorkflowFailed, match="transition budget exhausted"),
    ):
        drive_flow(Qa(story=STORY), env(), agent)

    counts = agent.counts()
    assert counts["apply-qa-fixes"] >= qa_flow.MAX_QA_REWORKS, counts
    assert counts["resolve-operator"] == qa_flow.MAX_QA_BLOCKS, counts
    assert counts["repair-qa-context"] < counts["apply-qa-fixes"], counts
    assert len(seen) > 1, "the identical block must escalate more than once"


def test_a_fixer_that_reports_blocked_reaches_the_operator(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`blocked` is the fixer saying nothing it does in this repo can help — so ask a person."""
    ostler(fail_runs=99)
    monkeypatch.setenv("WORKHORSE_MAX_TRANSITIONS", "60")
    seen: list[str] = []
    agent = _Agent(docs, assessment_class="product", qa_fix="blocked", escalate=True)

    with (
        patch.object(pyflow_driver, "wait_for_answer", _answers(seen)),
        pytest.raises(WorkflowFailed, match="transition budget exhausted"),
    ):
        drive_flow(Qa(story=STORY), env(), agent)

    counts = agent.counts()
    assert counts["qa-story"] == 1, counts
    assert counts["plan-qa"] + counts["repair-qa-plan"] == 1, counts
    assert len(seen) == counts["apply-qa-fixes"], counts
    assert counts["resolve-operator"] == qa_flow.MAX_QA_BLOCKS, counts
    assert [f"**Escalation #{n} " in body for n, body in enumerate(seen, 1)] == [
        True
    ] * len(seen), seen
    assert all(ESCALATION_NOTE.strip() in body for body in seen[: qa_flow.MAX_QA_BLOCKS]), seen


def test_a_resolver_that_grounds_its_answer_settles_a_qa_block(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The `answered` arm, which lands on the same `read_operator` an escalation does."""
    ostler(context_invalid=1)
    agent = _Agent(docs, repair="blocked")

    def never(path: Path, **kwargs: Any) -> None:
        raise AssertionError(f"a grounded answer must not park on {path}")

    with patch.object(pyflow_driver, "wait_for_answer", never):
        result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    assert "STATUS: CONSUMED" in (docs / CONTEXT_REL).read_text()


def test_an_escalating_resolver_hands_the_block_to_a_person(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The auto-operator's one honest answer: it waits on the same file a human mode does."""
    ostler(context_invalid=1)
    seen: list[str] = []
    agent = _Agent(docs, repair="blocked", escalate=True)

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen)):
        result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    (gate,) = seen
    assert "**Escalation #1 " in gate, gate
    assert all(line in gate for line in RESOLVER_TRIED), gate
    assert "only a person can decide this" in gate, gate
    assert ESCALATION_NOTE.strip() in gate, gate




def test_the_evidence_gate_invalidates_a_pass_it_cannot_verify(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A runner pass whose artifact contract fails is `invalid`, never `failed`."""
    ostler(vet_problems=["criterion AC-1 cites an artifact this run did not produce"])
    agent = _Agent(docs, escalate=True)
    seen: list[str] = []

    with pytest.raises(_Parked), patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)):
        drive_flow(Qa(story=STORY), env(), agent)

    assert agent.counts()["audit-qa"] == 0, agent.counts()
    assert agent.counts()["apply-qa-fixes"] == 0, agent.counts()
    assert agent.planned() == qa_flow.MAX_PLAN_REWORKS + 1, agent.counts()
    assert len(seen) == 1 and "plan repair" in seen[0], seen


def test_an_audit_that_refutes_the_pass_turns_it_into_a_product_failure(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`mark-qa-audit-failed.py`: a product contradiction is a fix, not a replan."""
    ostler()
    agent = _Agent(docs, audit=("refuted", "product-contradiction"), escalate=True)
    seen: list[str] = []

    with pytest.raises(_Parked), patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)):
        drive_flow(Qa(story=STORY), env(), agent)

    assert agent.counts()["apply-qa-fixes"] == qa_flow.MAX_QA_REWORKS, agent.counts()
    assert agent.counts()["triage-qa"] == qa_flow.MAX_QA_REWORKS + 1, agent.counts()
    assert len(seen) == 1 and "code rework" in seen[0], seen




def test_a_product_defect_is_triaged_fixed_and_re_qad(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """One failing run, one fix, and the second pass is clean."""
    okf = ostler(fail_runs=1)
    agent = _Agent(docs, assessment_class="product")

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert result.qa_rework == 1
    assert result.docs_recheck_required is True
    assert agent.counts()["triage-qa"] == 1, agent.counts()
    assert agent.counts()["apply-qa-fixes"] == 1, agent.counts()
    assert okf.runs == 2, okf.runs
    assert agent.args_for("apply-qa-fixes")[0]["qa_notes"] == "assessment pass 1"


_STUCK = {"copy-link": {"status": "failed", "assertions": 9, "failures": 1}}


def test_a_fix_that_leaves_the_run_failing_identically_is_not_repeated(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The `setup_problems` detector, one loop over — and the loop that cost the most."""
    ostler(fail_runs=99, scenarios=(_STUCK,))
    agent = _Agent(docs, assessment_class="product", triage=("qa_fix", "code"), escalate=True)
    seen: list[str] = []

    with pytest.raises(_Parked), patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)):
        drive_flow(Qa(story=STORY), env(), agent)

    unaided = agent.fix_args()
    assert len(unaided) < qa_flow.MAX_QA_REWORKS, agent.counts()
    assert agent.counts()["repair-qa-plan"] == 1, agent.counts()
    assert len(seen) == 1, seen


def test_a_stalled_plan_repair_tries_the_other_hypothesis_before_the_operator(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The defect this whole switch exists for, in the direction it actually happened."""
    ostler(fail_runs=99, scenarios=(_STUCK,))
    agent = _Agent(docs, repair_plans=99, escalate=True)
    seen: list[str] = []

    with pytest.raises(_Parked), patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)):
        drive_flow(Qa(story=STORY), env(), agent)

    unaided = agent.fix_args()
    assert len(unaided) >= 1, agent.counts()
    assert "the other side" in unaided[0]["qa_notes"], unaided[0]["qa_notes"]


def test_the_hypothesis_switch_happens_at_most_once_per_story(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`class_switched` is monotone, and that is the whole termination argument."""
    ostler(fail_runs=99, scenarios=(_STUCK,))
    agent = _Agent(docs, repair_plans=99, escalate=True)
    seen: list[str] = []

    with pytest.raises(_Parked), patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)):
        drive_flow(Qa(story=STORY), env(), agent)

    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    assert len(seen) == 1, seen


def test_a_dev_target_switching_to_the_product_reports_instead_of_fixing(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The switch routes through `_fixable`, not `apply_fixes`."""
    ostler(fail_runs=99, scenarios=(_STUCK,))
    agent = _Agent(docs, repair_plans=99, escalate=True)

    result = drive_flow(Qa(story=STORY, target_env="dev"), env(), agent)

    assert result.status == "inconclusive", result
    assert agent.counts()["apply-qa-fixes"] == 0, agent.counts()
    assert agent.counts()["report-qa-dev"] == 1, agent.counts()
    assert "resolve-operator" not in agent.counts(), agent.counts()


def test_a_fix_that_gets_the_run_further_still_earns_its_next_lap(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The other half: the detector must not stop a loop that is converging."""
    ostler(
        fail_runs=99,
        scenarios=tuple(
            {"copy-link": {"status": "failed", "assertions": depth, "failures": 1}}
            for depth in range(3, 3 + 2 * (qa_flow.MAX_QA_REWORKS + 1), 2)
        ),
    )
    agent = _Agent(docs, assessment_class="product", triage=("qa_fix", "code"), escalate=True)
    seen: list[str] = []

    with pytest.raises(_Parked), patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)):
        drive_flow(Qa(story=STORY), env(), agent)

    assert len(agent.fix_args()) == qa_flow.MAX_QA_REWORKS, agent.counts()
    assert len(seen) == 1, seen


_TWO_FAILED = {
    "copy-link": {"status": "failed", "assertions": 9, "failures": 1},
    "share-note": {"status": "failed", "assertions": 4, "failures": 2},
}


def test_a_failing_run_is_fixed_one_scenario_at_a_time(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The lever this split exists for: one brief per failing scenario, not one per report."""
    ostler(fail_runs=1, scenarios=(_TWO_FAILED, {}))
    agent = _Agent(docs, assessment_class="product", triage=("qa_fix", "code"))

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    briefs = agent.args_for("fix-qa-scenario")
    assert [b["scenario"] for b in briefs] == ["copy-link", "share-note"], agent.counts()
    assert agent.counts()["apply-qa-fixes"] == 0, agent.counts()
    assert briefs[0]["remaining_scenarios"] == ["share-note"], briefs[0]
    assert briefs[1]["remaining_scenarios"] == [], briefs[1]


def test_each_scenario_fix_is_proved_by_its_own_dry_run_before_the_next(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A per-item gate, so a fix that did not take is caught by the item that made it."""
    ostler(fail_runs=1, scenarios=(_TWO_FAILED, {}))
    agent = _Agent(docs, assessment_class="product", triage=("qa_fix", "code"),
                   item_dry_run=("missing", "failed", "passed", "passed"))

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    briefs = agent.args_for("fix-qa-scenario")
    assert [b["scenario"] for b in briefs] == [
        "copy-link", "copy-link", "share-note"
    ], agent.counts()


def test_a_scenario_that_spends_its_budget_is_carried_into_the_scored_run(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The per-item budget is not a give-up: an unproved item goes to the run, not the wall."""
    ostler(fail_runs=1, scenarios=(_STUCK, {}))
    agent = _Agent(docs, assessment_class="product", triage=("qa_fix", "code"),
                   item_dry_run=("missing", "failed"))

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["fix-qa-scenario"] == qa_flow.MAX_FIX_ITEM_REWORKS, agent.counts()
    assert "resolve-operator" not in agent.counts(), agent.counts()


def test_a_scenario_refused_twice_for_the_identical_reason_reaches_the_operator(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Sameness at item granularity, and the same conclusion `_repeating` draws at run level."""
    ostler(fail_runs=99, scenarios=(_STUCK,))
    agent = _Agent(docs, assessment_class="product", triage=("qa_fix", "code"),
                   item_dry_run="failed", escalate=True)
    seen: list[str] = []

    with pytest.raises(_Parked), patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)):
        drive_flow(Qa(story=STORY), env(), agent)

    assert agent.counts()["fix-qa-scenario"] == 2, agent.counts()
    assert len(seen) == 1, seen


def test_a_product_class_triage_returns_the_story_to_the_dev_lane(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A defect in the product is the dev lane's work, and the QA lane stops owning it."""
    ostler(fail_runs=99, scenarios=(_STUCK,))
    agent = _Agent(docs, assessment_class="product", triage=("qa_fix", "product"))

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "refix", result
    assert result.triage_scope == 1, result
    assert "fix-qa-scenario" not in agent.counts(), agent.counts()
    assert agent.counts()["apply-qa-fixes"] == 0, agent.counts()


def test_a_product_class_triage_past_its_budget_stops_bouncing_to_dev(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The termination argument: `triage_scope` is spent, and past it the lane escalates."""
    ostler(fail_runs=99, scenarios=(_STUCK,))
    agent = _Agent(docs, assessment_class="product", triage=("qa_fix", "product"),
                   escalate=True)
    seen: list[str] = []

    with pytest.raises(_Parked), patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)):
        drive_flow(Qa(story=STORY, triage_scope=qa_flow.MAX_TRIAGE_SCOPES), env(), agent)

    assert len(seen) == 1, seen




def test_a_spent_budget_asks_the_operator_before_abandoning_the_story(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A give-up is where an operator's one sentence is worth the most, and was where nobody asked."""
    ostler(fail_runs=99)
    monkeypatch.setenv("WORKHORSE_MAX_TRANSITIONS", "60")
    agent = _Agent(docs, assessment_class="product", triage=("qa_fix", "code"))
    seen: list[str] = []

    with (
        patch.object(pyflow_driver, "wait_for_answer", _answers(seen)),
        pytest.raises(WorkflowFailed, match="transition budget exhausted"),
    ):
        drive_flow(Qa(story=STORY), env(), agent)

    assert agent.counts()["resolve-operator"] >= 1, agent.counts()
    guided = [a for a in agent.args_for("apply-qa-fixes") if "operator_feedback" in a]
    assert len(guided) >= 1, agent.args_for("apply-qa-fixes")
    assert "staging bucket" in guided[0]["operator_feedback"]


def test_an_escalating_resolver_gives_up_now_rather_than_halting_the_drain(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A spent code-fix budget escalates and keeps escalating — a workflow blocks, not gives up."""
    ostler(fail_runs=99)
    monkeypatch.setenv("WORKHORSE_MAX_TRANSITIONS", "60")
    seen: list[str] = []
    agent = _Agent(docs, assessment_class="product", triage=("qa_fix", "code"), escalate=True)

    with (
        patch.object(pyflow_driver, "wait_for_answer", _answers(seen)),
        pytest.raises(WorkflowFailed, match="transition budget exhausted"),
    ):
        drive_flow(Qa(story=STORY), env(), agent)

    assert agent.counts()["resolve-operator"] > 1, agent.counts()
    assert len(seen) > 1, "the spent budget must escalate more than once"


def test_the_operator_is_asked_again_after_a_guided_lap_that_does_not_clear_the_run(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guided lap can exhaust a second time, and that is another ask, not a give-up."""
    ostler(context_invalid=9)
    monkeypatch.setenv("WORKHORSE_MAX_TRANSITIONS", "60")
    agent = _Agent(docs, repair="repaired", escalate=True)
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen)):
        result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["resolve-operator"] == qa_flow.MAX_QA_BLOCKS, agent.counts()
    assert len(seen) >= agent.counts()["resolve-operator"], seen


def test_a_human_operator_mode_still_waits_on_a_spent_budget(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Somebody who asked to be asked is still asked directly — `human` mode skips the resolver."""
    ostler(context_invalid=9)
    seen: list[str] = []
    agent = _Agent(docs, repair="repaired")

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen)):
        result = drive_flow(Qa(story=STORY, operator_mode="human"), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["resolve-operator"] == 0, agent.counts()
    assert len(seen) >= 1, seen


def test_triage_can_hand_the_scope_back_to_the_author(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`rescope` is the one exit that leaves the story unfinished on purpose."""
    ostler(fail_runs=99)
    agent = _Agent(docs, assessment_class="product", triage=("rescope", "code"))

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "rescope", result
    assert result.triage_scope == 1
    assert agent.counts()["triage-qa"] == 1, agent.counts()
    assert agent.counts()["apply-qa-fixes"] == 0, agent.counts()


def test_a_spent_rescope_budget_makes_triage_fix_in_place(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`guard_triage` runs *before* the decision, so a spent budget ignores `rescope`."""
    ostler(fail_runs=99)
    agent = _Agent(
        docs, assessment_class="product", triage=("rescope", "code"), escalate=True
    )
    seen: list[str] = []

    with (
        pytest.raises(_Parked),
        patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)),
    ):
        drive_flow(Qa(story=STORY, triage_scope=2), env(), agent)

    assert agent.counts()["triage-qa"] == qa_flow.MAX_QA_REWORKS + 1, agent.counts()
    assert agent.counts()["apply-qa-fixes"] == qa_flow.MAX_QA_REWORKS, agent.counts()




def _a_product_test_finding(handle: str = "A1") -> dict[str, str]:
    """The finding that livelocked a live story: a gap only a code edit can close."""
    return {
        "id": handle,
        "scope": "product-test",
        "target": "`AC9` / `editor-shell.browser.test.tsx`",
        "issue": "AC9's no-network clause is proved only by a static read of `exportDraft()`",
        "repair": "assert zero fetches around the export action",
    }


def test_an_audit_refuting_on_a_product_test_gap_sends_the_fixer_not_the_planner(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The `coder-qafix2` regression: three gates, one missing assertion, nobody who could add it."""
    ostler()
    agent = _Agent(
        docs,
        audit=("refuted", "evidence-defect"),
        audit_findings=[_a_product_test_finding()],
        escalate=True,
    )

    seen: list[str] = []

    with (
        pytest.raises(_Parked),
        patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)),
    ):
        drive_flow(Qa(story=STORY), env(), agent)

    assert f"{qa_flow.MAX_QA_REWORKS} code rework" in seen[0], seen
    assert agent.counts()["apply-qa-fixes"] == qa_flow.MAX_QA_REWORKS, agent.counts()
    assert agent.counts()["repair-qa-plan"] == 0, agent.counts()
    brief = agent.args_for("apply-qa-fixes")[0]["qa_notes"]
    assert "AC9" in brief and "fetch" in brief, brief


def test_an_extend_plan_naming_a_product_test_gap_sends_the_fixer(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The same gap found one gate earlier, by the post-run assessment."""
    ostler(fail_runs=99)
    agent = _Agent(
        docs,
        disposition="extend_plan",
        assessment_findings=[_a_product_test_finding("S1")],
        escalate=True,
    )

    seen: list[str] = []
    with (
        pytest.raises(_Parked),
        patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)),
    ):
        drive_flow(Qa(story=STORY), env(), agent)

    assert f"{qa_flow.MAX_QA_REWORKS} code rework" in seen[0], seen
    assert agent.counts()["apply-qa-fixes"] == qa_flow.MAX_QA_REWORKS, agent.counts()
    assert agent.counts()["repair-qa-plan"] == 0, agent.counts()


def test_a_plan_scoped_audit_finding_still_goes_to_the_plan_author(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Routing is by scope, not by gate: the audit's own plan defects are unaffected."""
    ostler()
    agent = _Agent(
        docs,
        audit=("refuted", "plan-defect"),
        audit_findings=[
            {
                "id": "A1",
                "scope": "plan",
                "target": "scenario `export-draft` / covers `AC9`",
                "issue": "the terminal assertion does not prove its `covers` claim",
                "repair": "assert the exported file's contents, not that the dialog closed",
            }
        ],
        escalate=True,
    )

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["repair-qa-plan"] == qa_flow.MAX_BLOCKING_AUDITS, agent.counts()
    assert agent.counts()["apply-qa-fixes"] == 0, agent.counts()


def test_a_refutation_naming_no_findings_still_takes_the_prose_path(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The fall-through the change must not remove."""
    ostler()
    agent = _Agent(docs, audit=("refuted", "evidence-defect"), escalate=True)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["repair-qa-plan"] == qa_flow.MAX_BLOCKING_AUDITS, agent.counts()
    assert agent.counts()["apply-qa-fixes"] == 0, agent.counts()


def test_an_audit_refuting_on_plan_scope_forever_stops_blocking(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The other half of the `coder-qafix2` regression: the gate with nothing downstream."""
    ostler()
    agent = _Agent(
        docs,
        audit=("refuted", "plan-defect"),
        audit_findings=[
            {
                "id": "A1",
                "scope": "plan",
                "target": "scenario `publish-draft` / covers `AC3`",
                "issue": "the assertion does not prove the claim it covers",
                "repair": "assert the published record, not that the request returned 200",
            }
        ],
        escalate=True,
    )

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["audit-qa"] == qa_flow.MAX_BLOCKING_AUDITS + 1, agent.counts()
    assert agent.counts()["repair-qa-plan"] == qa_flow.MAX_BLOCKING_AUDITS, agent.counts()


def test_a_dev_target_reports_a_product_test_finding_rather_than_fixing_it(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The route goes through `_fixable`, so `dev`'s "we do not own this code" still holds."""
    ostler()
    agent = _Agent(
        docs,
        audit=("refuted", "evidence-defect"),
        audit_findings=[_a_product_test_finding()],
    )

    result = drive_flow(Qa(story=STORY, target_env="dev"), env(), agent)

    assert result.status == "inconclusive", result
    assert agent.counts()["apply-qa-fixes"] == 0, agent.counts()
    assert agent.counts()["report-qa-dev"] == 1, agent.counts()




def test_a_dev_target_reports_findings_instead_of_fixing_them(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """We do not own the code, so the flow files what it found and stops."""
    ostler(fail_runs=99)
    agent = _Agent(docs, assessment_class="product")

    result = drive_flow(Qa(story=STORY, target_env="dev"), env(), agent)

    assert result.status == "inconclusive", result
    assert agent.counts()["report-qa-dev"] == 1, agent.counts()
    assert agent.powers_for("report-qa-dev") == ["low"]
    assert agent.counts()["apply-qa-fixes"] == 0, agent.counts()


def test_a_dev_target_still_reports_a_pass(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The green half of the same arm — the story passes and the tracker is told so."""
    ostler()
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY, target_env="dev"), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["report-qa-dev-pass"] == 1, agent.counts()
    assert agent.powers_for("report-qa-dev-pass") == ["low"]




def test_a_dropped_operator_note_buys_exactly_one_re_qa(
    docs: Path,
    ostler: Callable[..., _Ostler],
    write: Callable[[Path, str], Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Reading the inbox consumes it, so the second pass finds nothing and finishes."""
    okf = ostler()
    run_env = env()
    inbox.append(
        run_env.writer.run_dir / INBOX_FILE,
        id="note-1",
        body="The empty state still says 'TODO'.",
        at="2024-01-01T00:00:00+00:00",
    )
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY), run_env, agent)

    assert result.status == "passed", result
    assert agent.counts()["apply-qa-fixes"] == 1, agent.counts()
    assert agent.powers_for("apply-qa-fixes") == ["low"]
    assert okf.runs == 2, okf.runs
    assert result.qa_rework == 0
    assert result.docs_recheck_required is True
    assert "TODO" in agent.args_for("apply-qa-fixes")[0]["operator_feedback"]
    messages = inbox.all_messages(run_env.writer.run_dir / INBOX_FILE)
    assert len(messages) == 1, messages
    assert messages[0].reply, messages




def test_a_failing_journey_suite_is_fixed_and_the_story_is_re_qad(
    docs: Path,
    web: Path,
    ostler: Callable[..., _Ostler],
    monkeypatch: pytest.MonkeyPatch,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A regression fix is a code change, so the primary QA evidence has to be recaptured."""
    okf = ostler()
    suite = _Suite(fail_runs=1)
    monkeypatch.setattr(regression_nodes, "_run", suite)
    agent = _Agent(docs)
    run_env = env()

    result = drive_flow(Qa(story=STORY), run_env, agent)

    assert result.status == "passed", result
    assert result.docs_recheck_required is True
    assert agent.counts()["fix-regression"] == 1, agent.counts()
    assert len(suite.calls) == 3, suite.calls
    assert suite.calls[0] == "run-journeys", suite.calls
    assert okf.runs == 2, okf.runs
    assert _output(run_env, resolve_impl_context)["affected_repo_paths"] == [str(docs), str(web)]


def test_a_journey_suite_that_stays_red_falls_into_the_qa_fix_loop(
    docs: Path,
    web: Path,
    ostler: Callable[..., _Ostler],
    monkeypatch: pytest.MonkeyPatch,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`mark-regression-unresolved.py`: three fix attempts, then it joins the ordinary QA-fix loop."""
    ostler()
    monkeypatch.setattr(regression_nodes, "_run", _Suite(fail_runs=99))
    agent = _Agent(docs, escalate=True)
    seen: list[str] = []

    with (
        pytest.raises(_Parked),
        patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)),
    ):
        drive_flow(Qa(story=STORY), env(), agent)

    assert agent.counts()["fix-regression"] == 3, agent.counts()
    assert agent.counts()["apply-qa-fixes"] >= 1, agent.counts()




def test_a_run_killed_mid_audit_resumes_on_the_audit(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The whole eighteen-field loop carrier round-trips through one checkpoint parameter."""
    okf = ostler()
    run_env = env()
    run_dir = run_env.writer.run_dir

    with pytest.raises(RuntimeError, match="killed during audit-qa"):
        drive_flow(Qa(story=STORY), run_env, _Agent(docs, explode={"audit-qa"}))

    checkpoint = parse_checkpoint((run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    resume = read_resume(checkpoint)
    assert resume.state == "audit", resume
    assert resume.flow == "Qa", resume
    assert resume.params["loop"]["qa"]["status"] == "passed", resume.params

    agent = _Agent(docs)
    result = drive_flow(Qa(**resume.inputs), env(run_dir=run_dir), agent, resume)

    assert result.status == "passed", result
    assert agent.counts() == {"audit-qa": 1}, agent.counts()
    assert okf.runs == 1, "the resumed run must not re-run the QA suite"


def test_the_lane_runs_standalone_with_no_plan_context(
    docs: Path,
    ostler: Callable[..., _Ostler],
    write: Callable[[Path, str], Path],
    monkeypatch: pytest.MonkeyPatch,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """QA against someone else's checkout: no dev lane ran, so there is no `plan-context.json`."""
    (docs / SPEC_REL / "plan-context.json").unlink()
    ostler()
    monkeypatch.setattr(
        qa_stack, "ensure_stack", lambda *a, **k: {"ready": "yes", "entry_url": "http://x"}
    )
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.planned() == 1, agent.counts()





@pytest.mark.parametrize("stem", ["plan-qa", "qa-story", "audit-qa"])
def test_a_turn_that_says_it_cannot_proceed_reaches_the_operator(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    stem: str,
) -> None:
    """Every binding turn on the clean path can refuse, and the refusal is a block."""
    ostler(fail_runs=99 if stem == "qa-story" else 0)
    agent = _Agent(docs, refuses={stem})
    seen: list[str] = []

    with pytest.raises(_Parked), patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)):
        drive_flow(Qa(story=STORY, operator_mode="human"), env(), agent)

    assert agent.counts()[stem] == 1, agent.counts()
    assert len(seen) == 1, seen
    assert "needs a credential this run does not hold" in seen[0], seen


def test_a_triage_that_cannot_proceed_reaches_the_operator(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Triage is only reached by a failing run, so it needs one to refuse on."""
    ostler(fail_runs=1)
    agent = _Agent(docs, assessment_class="product", refuses={"triage-qa"})
    seen: list[str] = []

    with pytest.raises(_Parked), patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)):
        drive_flow(Qa(story=STORY, operator_mode="human"), env(), agent)

    assert agent.counts()["triage-qa"] == 1, agent.counts()
    assert agent.counts()["apply-qa-fixes"] == 0, agent.counts()
    assert len(seen) == 1 and "needs a credential this run does not hold" in seen[0], seen




def test_a_standing_valid_plan_is_adopted_without_an_authoring_turn(
    docs: Path,
    ostler: Callable[..., _Ostler],
    write: Callable[[Path, str], Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A `qa_plan.py` that lints and validates goes to the runner with no plan turn at all."""
    ostler()
    write(docs / SPEC_REL / "qa_plan.py", QA_PLAN)
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.planned() == 0, agent.counts()
    assert agent.args_for("plan-qa") == [], agent.counts()


def test_stop_at_first_verdict_finishes_a_green_run_with_no_post_run_agent_turns(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`stop_at_first_verdict`: a pass is still gated deterministically, and only deterministically."""
    okf = ostler()
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY, stop_at_first_verdict=True), env(), agent)

    assert result.status == "passed", result
    assert agent.counts() == {"plan-qa": 1}, agent.counts()
    assert (okf.contexts, okf.runs, okf.vets) == (1, 1, 1)


def test_stop_at_first_verdict_reports_the_first_red_without_entering_repair(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`stop_at_first_verdict`: the first red is the report, and no agent reads it first."""
    okf = ostler(fail_runs=99)
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY, stop_at_first_verdict=True), env(), agent)

    assert result.status == "inconclusive", result
    assert result.qa.status == "failed", result
    assert agent.counts() == {"plan-qa": 1}, agent.counts()
    assert okf.runs == 1, "the red run was retried — stop_at_first_verdict must not repair"


def test_stop_at_first_verdict_still_repairs_the_environment(
    docs: Path,
    ostler: Callable[..., _Ostler],
    write: Callable[[Path, str], Path],
    monkeypatch: pytest.MonkeyPatch,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`stop_at_first_verdict` reports verdicts about the product, never about the harness."""
    okf = ostler(block_runs=1)
    write(docs / "qa-stack.yml", "app_cwd: .\nhealth:\n  - run: true\n")
    monkeypatch.setattr(
        qa_stack, "ensure_stack", lambda *a, **k: {"ready": "yes", "entry_url": "http://x"}
    )
    agent = _Agent(docs, setup="ready")

    result = drive_flow(Qa(story=STORY, stop_at_first_verdict=True), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["setup-fix"] == 1, agent.counts()
    assert agent.counts()["qa-story"] == 1, agent.counts()
    assert okf.runs == 2, "the repaired run was never retried"
