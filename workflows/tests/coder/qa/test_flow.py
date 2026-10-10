"""End-to-end tests for the `qa` flow: the owner turn, the check that reruns it, and the operator."""
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
from workhorse.pyflow import park as pyflow_park
from workhorse.pyflow.driver import read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import parse_checkpoint

from ostler import Ostler
from ostler.qa import QaOutcome
from ostler.qa.source_context import SourceRepository

from workhorse_workflows.coder.shared.plan import resolve_impl_context
from workhorse_workflows.coder.qa import flow as qa_flow
from workhorse_workflows.coder.qa.flow import Qa
from workhorse_workflows.coder.qa.nodes import qa as qa_nodes
from workhorse_workflows.coder.qa.nodes import regression as regression_nodes
from workhorse_workflows.coder.qa.nodes.qa import QA_SCRATCH_DIRNAME
from workhorse_workflows.coder.shared import okf as okf_nodes
from workhorse_workflows.coder.shared import qa_support
from workhorse_workflows.kit.qa import evidence as qa_evidence_mod
from workhorse_workflows.kit.qa import runner as qa_runner_mod

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

SERVER_REL = "docs/features/app/server.md"

SERVER_MD = "---\ntype: server\ntitle: App server\n---\n\n# App server\n"


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
    write(repo / SERVER_REL, SERVER_MD)
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
    """The QA owner's turn and the resolver, scripted on the axes the flow branches on."""

    def __init__(
        self,
        docs: Path,
        *,
        statuses: tuple[str, ...] = ("passed",),
        findings: list[dict[str, str]] | None = None,
        proves: tuple[str, ...] = (),
        dry_runs: tuple[str, ...] = ("passed",),
        escalate: bool = False,
        scope: str = "story",
        explode_at: int = 0,
        touch: Path | None = None,
    ) -> None:
        self.docs = docs
        self.statuses = statuses
        self.findings = findings or []
        self.proves = proves
        self.dry_runs = dry_runs
        self.escalate = escalate
        self.scope = scope
        self.explode_at = explode_at
        self.touch = touch
        self.calls: list[str] = []
        self.args: list[dict[str, Any]] = []
        self.dirs: list[list[str]] = []
        self.powers: list[str | None] = []
        self.timeouts: list[Any] = []

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        stem = Path(node.prompt).stem
        data = ctx.as_dict()
        self.calls.append(stem)
        self.args.append(data)
        self.dirs.append(list(node.add_dirs or []))
        self.powers.append(node.power)
        self.timeouts.append(node.timeout)
        nth = self.counts()[stem]
        if stem == "qa-story" and nth == self.explode_at:
            raise RuntimeError(f"killed during {stem} turn {nth}")
        handler = getattr(self, f"_{stem.replace('-', '_')}")
        return f"(scripted) {node.prompt}", handler(data, nth)

    def counts(self) -> Counter[str]:
        return Counter(self.calls)

    def args_for(self, stem: str) -> list[dict[str, Any]]:
        return [a for s, a in zip(self.calls, self.args, strict=True) if s == stem]

    def _qa_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """Plan unless one stands, prove what it names, and return the scripted verdict."""
        status = self.statuses[min(nth, len(self.statuses)) - 1]
        if status == "blocked":
            return {
                "status": "blocked",
                "notes": f"the QA turn needs a credential this run does not hold (turn {nth})",
            }
        if self.touch is not None:
            self.touch.write_text("fixed\n", encoding="utf-8")
        if not data["standing_plan"]:
            (Path(data["spec_dir"]) / "qa_plan.py").write_text(QA_PLAN, encoding="utf-8")
        shape = self.dry_runs[min(nth, len(self.dry_runs)) - 1]
        for scenario in self.proves:
            self._prove(data, scenario, shape)
        return {
            "status": status,
            "notes": f"owner turn {nth}",
            "findings": self.findings if status == "findings" else [],
            "proved_scenarios": list(self.proves),
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
            "grounded": ["docs/decisions/which-bucket.md:3: 'QA writes go to the staging bucket'"],
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


PRODUCT_FINDING: dict[str, str] = {
    "id": "copy-link",
    "target": "acme/src/links.py:12",
    "issue": "the copied link drops the share token",
    "repair": "keep the token when the link is built",
}

_STUCK = {"copy-link": {"status": "failed", "assertions": 9, "failures": 1}}


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


def test_one_clean_pass_spends_one_owner_turn(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The owner plans and passes, and the run's own rerun clears every gate first try."""
    okf = ostler()
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert result.findings == []
    assert agent.calls == ["qa-story"], agent.calls
    assert agent.args[0]["standing_plan"] is False
    assert agent.args[0]["report"] == ""
    assert (okf.contexts, okf.runs, okf.vets) == (2, 1, 1)
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
        drive_flow(Qa(story=""), env(), agent)

    assert agent.calls == []
    assert (okf.contexts, okf.runs) == (0, 0)


def test_the_owner_turn_is_granted_only_the_repos_the_plan_touches(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The owner runs at high power with no wall clock, over the story's repos only."""
    ostler()
    agent = _Agent(docs)
    run_env = env()

    drive_flow(Qa(story=STORY), run_env, agent)

    expected = _output(run_env, resolve_impl_context)["affected_repo_paths"]
    assert expected == [str(docs)], expected
    assert agent.dirs == [expected], agent.dirs
    assert agent.powers == ["high"], agent.powers


def test_an_unmappable_packet_reaches_the_owner_and_is_rebuilt_by_the_check(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The owner's first report carries the packet failure, and the check rebuilds the packet."""
    okf = ostler(context_invalid=1)
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.calls == ["qa-story"], agent.calls
    assert "no feature node" in agent.args[0]["report"]
    assert okf.contexts == 2, okf.contexts


def test_a_packet_that_stays_unmappable_blocks_after_the_lap_budget(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Every lap rebuilds and fails the packet, so the block names the repair turns it spent."""
    okf = ostler(context_invalid=99)
    agent = _Agent(docs, escalate=True)
    seen: list[str] = []

    with (
        patch.object(pyflow_park, "wait_for_answer", _parked_at(seen)),
        pytest.raises(_Parked),
    ):
        drive_flow(Qa(story=STORY), env(), agent)

    assert agent.counts() == {
        "qa-story": qa_flow.MAX_LAPS + 1,
        "resolve-operator": 1,
    }, agent.counts()
    assert okf.runs == 0, "the packet never validated, so nothing should have run"
    assert len(seen) == 1, seen
    assert "repair turn(s)" in seen[0] and "no feature node" in seen[0], seen


def test_a_blocked_owner_is_answered_and_resumes_with_the_answer(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A grounded answer goes back into the owner's session as its operator context."""
    ostler()
    agent = _Agent(docs, statuses=("blocked", "passed"))

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.calls == ["qa-story", "resolve-operator", "qa-story"], agent.calls
    assert "needs a credential" in agent.args_for("resolve-operator")[0]["block_notes"]
    assert "staging bucket" in agent.args_for("qa-story")[1]["operator_context"]


@pytest.mark.parametrize("operator_mode", ["human", "operator"])
def test_human_operator_modes_wait_on_the_story_context_file(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    operator_mode: str,
) -> None:
    """Canonical `human` and legacy `operator` block on `<story>/context.md`."""
    ostler()
    seen: list[str] = []
    agent = _Agent(docs, statuses=("blocked", "passed"))

    with patch.object(pyflow_park, "wait_for_answer", _answers(seen)):
        result = drive_flow(Qa(story=STORY, operator_mode=operator_mode), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["resolve-operator"] == 0, agent.counts()
    assert len(seen) == 1 and "needs a credential" in seen[0], seen


def test_an_epic_scoped_answer_hands_the_story_back_to_replan(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """No amount of QA reaches a wrong premise, so the parent re-derives the epic."""
    ostler()
    agent = _Agent(docs, statuses=("blocked",), escalate=True)
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", _answers(seen, scope="epic")):
        result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "replan", result
    assert "staging bucket" in result.operator_notes
    assert agent.counts()["qa-story"] == 1, agent.counts()


def test_an_invalid_plan_goes_back_to_the_owner_before_anything_runs(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The validation refusal is the next turn's report, and the repaired plan then stands."""
    okf = ostler(plan_invalid=1)
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["qa-story"] == 2, agent.counts()
    assert "names no assertion" in agent.args[1]["report"]
    assert agent.args[1]["standing_plan"] is True
    assert okf.runs == 1, okf.runs


def test_a_proved_scenario_that_dry_ran_red_is_not_a_finished_plan(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A claimed proof is checked against its scratch log before the suite spends a run."""
    okf = ostler()
    agent = _Agent(docs, proves=(DRAFT_SCENARIO,), dry_runs=("failed", "passed"))

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["qa-story"] == 2, agent.counts()
    assert "dry runs" in agent.args[1]["report"]
    assert okf.runs == 1, okf.runs


def test_a_failed_run_with_findings_sends_them_back_as_a_refix(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """QA never fixes the product: a proved defect is the dev owner's, carried in the result."""
    okf = ostler(fail_runs=99)
    agent = _Agent(docs, statuses=("findings",), findings=[PRODUCT_FINDING])

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "refix", result
    assert result.qa.status == "failed", result
    assert [f.model_dump() for f in result.findings] == [PRODUCT_FINDING], result.findings
    assert agent.calls == ["qa-story"], agent.calls
    assert okf.runs == 1, okf.runs


def test_a_failed_run_with_no_finding_goes_back_with_its_failing_scenarios(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The next turn's worklist is the failing set itself, not a paragraph describing it."""
    okf = ostler(fail_runs=1, scenarios=(_STUCK, {}))
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.args[0]["failed_scenarios"] == []
    assert agent.args[1]["failed_scenarios"] == [
        {"id": "copy-link", "failed_assertions": ["copy-link-1"]}
    ], agent.args[1]["failed_scenarios"]
    assert "returned no finding" in agent.args[1]["report"]
    assert okf.runs == 2, okf.runs


def test_findings_beside_a_passing_run_go_back_as_unproved(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A finding stands only when a scenario fails on it."""
    okf = ostler()
    agent = _Agent(docs, statuses=("findings", "passed"), findings=[PRODUCT_FINDING])

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert result.findings == []
    assert "unproved findings" in agent.args[1]["report"]
    assert okf.runs == 2, okf.runs


def test_an_empty_manifest_splits_on_whether_the_book_serves_anything(
    docs: Path,
    write: Callable[[Path, str], Path],
) -> None:
    """`ensure_stack` reads the topology, not just the manifest, before calling it a gap."""
    log = logging.getLogger("test")
    (docs / RUNBOOK_REL).unlink()
    (docs / SERVER_REL).unlink()

    status = qa_nodes.ensure_stack(log, str(docs))
    assert status.ready == "unneeded", status
    assert "serves nothing" in status.notes

    write(docs / SERVER_REL, SERVER_MD)
    status = qa_nodes.ensure_stack(log, str(docs))
    assert status.ready == "none", status
    assert "served surface" in status.notes


def test_a_book_that_serves_nothing_needs_no_stack_beside_one_that_does(
    docs: Path,
    write: Callable[[Path, str], Path],
) -> None:
    """The served-surface question is asked of the book being run, not of the whole repository."""
    log = logging.getLogger("test")
    (docs / RUNBOOK_REL).unlink()
    features = docs / "docs" / "features"
    write(features / "tool" / "command.md", "---\ntype: concept\ntitle: Command\n---\n\n# Command\n")

    beside = qa_runner_mod.ensure_stack(log, str(docs), near=str(features / "tool"))
    served = qa_runner_mod.ensure_stack(log, str(docs), near=str(features / "app"))

    assert beside.ready == "unneeded", beside
    assert served.ready == "none", served


def test_a_book_that_serves_nothing_brings_up_none_of_its_runbooks(
    docs: Path,
    write: Callable[[Path, str], Path],
) -> None:
    """A command-line book's service runbook documents a procedure; QA invokes the commands instead."""
    log = logging.getLogger("test")
    features = docs / "docs" / "features"
    write(features / "tool" / "command.md", "---\ntype: concept\ntitle: Command\n---\n\n# Command\n")
    write(features / "tool" / "ops" / "container-job.md",
          "---\ntype: runbook\ntitle: Container job\n---\n\n# Container job\n\n- driver: cli\n\n"
          "## Steps\n\n### serve\n\n- kind: service\n- run: false\n- health: false\n")

    status = qa_runner_mod.ensure_stack(log, str(docs), near=str(features / "tool"))

    assert status.ready == "unneeded", status


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


def test_evidence_the_vetter_keeps_refusing_blocks_after_the_lap_budget(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A pass the evidence gate cannot verify is never believed, however many laps it takes."""
    ostler(vet_problems=["the report cites no evidence"])
    agent = _Agent(docs, escalate=True)
    seen: list[str] = []

    with (
        patch.object(pyflow_park, "wait_for_answer", _parked_at(seen)),
        pytest.raises(_Parked),
    ):
        drive_flow(Qa(story=STORY), env(), agent)

    assert agent.counts() == {
        "qa-story": qa_flow.MAX_LAPS + 1,
        "resolve-operator": 1,
    }, agent.counts()
    assert len(seen) == 1 and "repair turn(s)" in seen[0], seen


def test_a_dev_target_reports_findings_instead_of_refixing(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """In dev the product is someone else's, so the story passes carrying what QA found."""
    ostler(fail_runs=99)
    agent = _Agent(docs, statuses=("findings",), findings=[PRODUCT_FINDING])

    result = drive_flow(Qa(story=STORY, target_env="dev"), env(), agent)

    assert result.status == "passed", result
    assert result.qa.status == "failed", result
    assert [f.id for f in result.findings] == ["copy-link"], result.findings
    assert agent.calls == ["qa-story"], agent.calls


def test_a_dev_target_still_passes_a_green_story(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The green half of the same arm."""
    ostler()
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY, target_env="dev"), env(), agent)

    assert result.status == "passed", result
    assert result.findings == []
    assert agent.args[0]["target_env"] == "dev"


def test_a_dropped_operator_note_buys_exactly_one_re_qa(
    docs: Path,
    ostler: Callable[..., _Ostler],
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
    assert agent.counts()["qa-story"] == 2, agent.counts()
    assert okf.runs == 2, okf.runs
    assert "TODO" in agent.args[1]["report"]
    messages = inbox.all_messages(run_env.writer.run_dir / INBOX_FILE)
    assert len(messages) == 1, messages
    assert messages[0].reply, messages


def test_a_failing_journey_suite_goes_back_to_the_owner_and_the_story_is_re_qad(
    docs: Path,
    web: Path,
    ostler: Callable[..., _Ostler],
    monkeypatch: pytest.MonkeyPatch,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A regression repair is a code change, so the primary QA evidence is recaptured."""
    okf = ostler()
    suite = _Suite(fail_runs=1)
    monkeypatch.setattr(regression_nodes, "_run", suite)
    agent = _Agent(docs)
    run_env = env()

    result = drive_flow(Qa(story=STORY), run_env, agent)

    assert result.status == "passed", result
    assert agent.counts()["qa-story"] == 2, agent.counts()
    assert "regression suites" in agent.args[1]["report"]
    assert suite.calls == ["run-journeys", "run-journeys"], suite.calls
    assert okf.runs == 2, okf.runs
    assert _output(run_env, resolve_impl_context)["affected_repo_paths"] == [str(docs), str(web)]


@pytest.mark.parametrize("touched", [False, True])
def test_the_docs_are_rechecked_only_when_the_owner_moved_the_code(
    docs: Path,
    web: Path,
    ostler: Callable[..., _Ostler],
    monkeypatch: pytest.MonkeyPatch,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    touched: bool,
) -> None:
    """A repair a subagent made in a code repo can stale the docs, and a pass that made none cannot."""
    ostler()
    monkeypatch.setattr(regression_nodes, "_run", _Suite())
    agent = _Agent(docs, touch=web / "fix.txt" if touched else None)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert result.docs_recheck_required is touched


def test_a_stack_that_will_not_come_up_is_the_owners_to_repair(
    docs: Path,
    ostler: Callable[..., _Ostler],
    monkeypatch: pytest.MonkeyPatch,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The failing step's message reaches the owner, and the check brings the stack up again."""
    ostler()
    results = [
        {"ready": "no", "failed_step": "health[0]", "error": "api-test container is not running"},
        {"ready": "yes", "entry_url": "http://x"},
    ]
    monkeypatch.setattr(qa_stack, "ensure_stack", lambda *a, **k: results.pop(0))
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.calls == ["qa-story"], agent.calls
    assert "health[0]" in agent.args[0]["report"]
    assert "api-test container is not running" in agent.args[0]["report"]
    assert results == [], "the stack was never brought up a second time"


def test_a_book_that_serves_nothing_runs_qa_without_a_stack(
    docs: Path,
    ostler: Callable[..., _Ostler],
    monkeypatch: pytest.MonkeyPatch,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """An artifact-only book reaches the owner with nothing to repair and nothing to boot."""
    ostler()
    (docs / RUNBOOK_REL).unlink()
    (docs / SERVER_REL).unlink()

    def _boom(*a: Any, **k: Any) -> dict[str, Any]:
        raise AssertionError("there is no manifest, so nothing may try to bring one up")

    monkeypatch.setattr(qa_stack, "ensure_stack", _boom)
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.calls == ["qa-story"], agent.calls
    assert agent.args[0]["report"] == ""


def test_a_standing_valid_plan_is_handed_to_the_owner_to_adopt(
    docs: Path,
    ostler: Callable[..., _Ostler],
    write: Callable[[Path, str], Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A `qa_plan.py` that lints and validates is the plan, and the owner is told so."""
    ostler()
    write(docs / SPEC_REL / "qa_plan.py", QA_PLAN)
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.args[0]["standing_plan"] is True


def test_the_lane_runs_standalone_with_no_plan_context(
    docs: Path,
    ostler: Callable[..., _Ostler],
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
    assert agent.calls == ["qa-story"], agent.calls


def test_a_run_killed_mid_repair_resumes_on_the_owner_turn_with_its_report(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The lap's report and count round-trip through the checkpoint."""
    okf = ostler(fail_runs=1)
    run_env = env()
    run_dir = run_env.writer.run_dir

    with pytest.raises(RuntimeError, match="killed during qa-story turn 2"):
        drive_flow(Qa(story=STORY), run_env, _Agent(docs, explode_at=2))

    checkpoint = parse_checkpoint((run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    resume = read_resume(checkpoint)
    assert resume.state == "work", resume
    assert resume.params["laps"] == 1, resume.params
    assert "returned no finding" in resume.params["report"], resume.params

    agent = _Agent(docs)
    result = drive_flow(Qa(**resume.inputs), env(run_dir=run_dir), agent, resume)

    assert result.status == "passed", result
    assert agent.calls == ["qa-story"], agent.calls
    assert okf.runs == 2, okf.runs


def test_stop_at_first_verdict_finishes_a_green_run_in_one_turn(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A pass is still gated deterministically, and only deterministically."""
    okf = ostler()
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY, stop_at_first_verdict=True), env(), agent)

    assert result.status == "passed", result
    assert agent.calls == ["qa-story"], agent.calls
    assert (okf.runs, okf.vets) == (1, 1)


def test_stop_at_first_verdict_reports_the_first_red_without_a_repair_turn(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The first red is the verdict, carried as a refix even when the owner named no finding."""
    okf = ostler(fail_runs=99)
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY, stop_at_first_verdict=True), env(), agent)

    assert result.status == "refix", result
    assert result.qa.status == "failed", result
    assert [f.id for f in result.findings] == ["qa-run"], result.findings
    assert agent.calls == ["qa-story"], agent.calls
    assert okf.runs == 1, "the red run was retried, and stop_at_first_verdict must not repair"


def test_stop_at_first_verdict_still_repairs_the_environment(
    docs: Path,
    ostler: Callable[..., _Ostler],
    monkeypatch: pytest.MonkeyPatch,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A blocked run is a verdict about the harness, never about the product."""
    okf = ostler(block_runs=1)
    monkeypatch.setattr(
        qa_stack, "ensure_stack", lambda *a, **k: {"ready": "yes", "entry_url": "http://x"}
    )
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY, stop_at_first_verdict=True), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["qa-story"] == 2, agent.counts()
    assert "Playwright" in agent.args[1]["report"]
    assert okf.runs == 2, "the repaired run was never retried"
