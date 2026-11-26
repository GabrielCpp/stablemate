"""End-to-end tests for the `qa` flow: the owner turn, the check that reruns it, and the operator."""
from __future__ import annotations

import json
import logging
import os
import subprocess
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from workhorse import inbox
from workhorse._vendor.stablemate_core import config as core_config
from workhorse.artifacts import ArtifactWriter
from workhorse.cli.inbox import INBOX_FILE
from workhorse.pyflow import WorkflowFailed
from workhorse.pyflow import park as pyflow_park
from workhorse.pyflow.driver import read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import parse_checkpoint
from workhorse.runner.failure import TurnDeadlineExceeded

from ostler import Ostler
from ostler.environments import commands as env_commands
from ostler.environments import runtime
from ostler.environments.render import SHARED as SHARED_COPY
from ostler.qa import QaOutcome

from workhorse_workflows.coder.shared.plan import resolve_impl_context
from workhorse_workflows.coder.shared import qa_owner
from workhorse_workflows.coder.qa.flow import Qa
from workhorse_workflows.coder.qa.nodes import qa as qa_nodes
from workhorse_workflows.coder.qa.nodes import regression as regression_nodes
from workhorse_workflows.coder.qa.nodes.qa import QA_SCRATCH_DIRNAME
from workhorse_workflows.kit.qa import evidence as qa_evidence_mod
from workhorse_workflows.kit.qa import runner as qa_runner_mod
from _epics import epics_root

if TYPE_CHECKING:
    from coder.qa.conftest import BooksLeft

STORY = "STORY-1"
EPIC = "EPIC-1"


def spec_dir() -> Path:
    """The story's spec folder under this test's artifacts dir."""
    return core_config.resolve_artifacts_dir() / "specs" / STORY

STORY_REL = f"{EPIC}/stories/{STORY}"
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
id: STORY-1
type: story
services: [app]
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




@pytest.fixture
def docs(
    repo: Path,
    write: Callable[[Path, str], Path],
    write_json: Callable[[Path, Any], Path],
) -> Path:
    """The docs repo: one epic, one built story, and the plan the dev phase left behind."""
    write(epics_root() / EPIC / "epic.md", EPIC_MD)
    write(epics_root() / STORY_REL / "story.md", STORY_MD)
    write(repo / "services" / "app" / "service.py", "SERVICE = 1\n")
    write_json(
        repo / spec_dir() / "plan-context.json", {"story": STORY, "services": [API_SERVICE]}
    )
    return repo


@pytest.fixture
def web(
    tmp_path: Path,
    docs: Path,
    git: Callable[..., subprocess.CompletedProcess],
    write: Callable[[Path, str], Path],
    write_json: Callable[[Path, Any], Path],
    name_workspace: Callable[[dict[str, Path]], None],
) -> Path:
    """A real `web` repo that declares a journey suite, and a plan that names it."""
    write_json(
        docs / spec_dir() / "plan-context.json", {"story": STORY, "services": [WEB_SERVICE]}
    )
    root = tmp_path / "ws"
    path = root / "web"
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    write(path / "agents.yml", "services:\n  web-app: {regression: 'run-journeys'}\n")
    git(path, "add", "-A")
    git(path, "commit", "-qm", "Initial commit")
    git(path, "commit", "-q", "--allow-empty", "-m", f"feat: seed\n\nStory: {STORY}")
    name_workspace({"web": path})
    return path




class _Ostler:
    """ostler's QA lint and run subcommands and its artifact vetter, scripted at the process edge."""

    def __init__(
        self,
        *,
        fail_runs: int = 0,
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
        self.plan_invalid = plan_invalid
        self.plan_invalid_passes = plan_invalid_passes
        self.plan_invalid_stuck = plan_invalid_stuck
        self.vet_problems = vet_problems or []
        self.runs = 0
        self.plan_lints = 0
        self.vets = 0
        self.only: list[list[str] | None] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> _Ostler:
        """Stand in for the `Ostler` the nodes construct, in every module that does."""
        for module in (qa_nodes, qa_runner_mod, qa_evidence_mod):
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


    def qa_lint(self, plan_file: str | Path) -> QaOutcome:
        self.script.plan_lints += 1
        assert Path(plan_file).is_file(), f"the plan turn wrote no {plan_file}"
        if (
            self.script.plan_lints <= self.script.plan_invalid
            or self.script.plan_lints in self.script.plan_invalid_passes
        ):
            step = 3 if self.script.plan_invalid_stuck else self.script.plan_lints
            return QaOutcome(
                ok=False,
                message="plan lint failed",
                status="invalid",
                data={"notes": f"step {step} names no assertion"},
            )
        return QaOutcome(ok=True, message="QA plan lint passed.", data={})


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
        script.only.append(only)
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
        claims: tuple[str, ...] = (),
        escalate: bool = False,
        scope: str = "story",
        explode_at: int = 0,
        touch: Path | None = None,
        items: tuple[dict[str, Any], ...] = (),
        same: dict[str, str] | None = None,
        cut: tuple[str, ...] = (),
    ) -> None:
        self.cut = set(cut)
        self.nodes: list[Any] = []
        self.kwargs: list[dict[str, Any]] = []
        self.docs = docs
        self.items = items
        self.same = same or {}
        self.statuses = statuses
        self.findings = findings or []
        self.claims = claims
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
        self.nodes.append(node)
        self.kwargs.append(kwargs)
        if stem in self.cut:
            self.cut.discard(stem)
            raise TurnDeadlineExceeded(stem, node.deadline, node.deadline + 1.0)
        if stem == "qa-story" and nth == self.explode_at:
            raise RuntimeError(f"killed during {stem} turn {nth}")
        handler = getattr(self, f"_{stem.replace('-', '_')}")
        return f"(scripted) {node.prompt}", handler(data, nth)

    def counts(self) -> Counter[str]:
        return Counter(self.calls)

    def args_for(self, stem: str) -> list[dict[str, Any]]:
        return [a for s, a in zip(self.calls, self.args, strict=True) if s == stem]

    def _qa_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """Plan unless one stands, and return the scripted verdict."""
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
        if self.items:
            (Path(data["spec_dir"]) / "backlog-items.json").write_text(
                json.dumps(list(self.items)), encoding="utf-8"
            )
        return {
            "status": status,
            "notes": f"owner turn {nth}",
            "findings": self.findings if status == "findings" else [],
            "proved_scenarios": list(self.claims),
        }

    def _judge(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """The judge's ruling: each subject `same` names to its bullet, the rest left new."""
        subjects = json.loads(str(data["subjects"]))
        return {"answers": {k: v for k, v in self.same.items() if k in subjects}}

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
            "grounded": ["product/which-bucket.md:5: 'QA writes go to the staging bucket'"],
            "record": "which-bucket",
        }

    def _answer(self) -> None:
        """Write the answer where `read_operator_context` reads it back out of."""
        (epics_root() / CONTEXT_REL).write_text(
            f"STATUS: ANSWERED\nSCOPE: {self.scope}\n\nUse the staging bucket.\n",
            encoding="utf-8",
        )

    def _escalate(self) -> None:
        """An escalating resolver writes its note into the same file, it does not write nothing."""
        (epics_root() / CONTEXT_REL).write_text(ESCALATION_NOTE, encoding="utf-8")


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
    assert (okf.runs, okf.vets) == (1, 1)
    assert (docs / spec_dir() / "qa-evidence.json").is_file()
    assert (docs / spec_dir() / "qa" / "qa-run.ndjson").is_file()


def test_a_backlog_item_an_open_qa_record_holds_is_dropped_and_a_new_one_is_filed(
    docs: Path,
    web: Path,
    ostler: Callable[..., _Ostler],
    monkeypatch: pytest.MonkeyPatch,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The judge reads one item as the open `qa` record and the other as new, so only the new one lands, shelved under the workspace repo the item names."""
    monkeypatch.setattr(regression_nodes, "_run", _Suite())
    ostler()
    held = Ostler(docs).file_record(
        repo="web", area="reports", pattern="clear-state", filed_by="qa",
        summary="Sign-out leaves the saved report snapshots in the browser.",
    )
    assert held.record is not None, held.message
    agent = _Agent(
        docs,
        items=(
            {"id": "drop-snapshots-on-logout", "description": "Logging out keeps cached report snapshots."},
            {
                "id": "paginate-audit-log",
                "description": "The audit log loads every row at once.",
                "repo": "web",
                "area": "audit",
                "pattern": "paginate",
            },
        ),
        same={"drop-snapshots-on-logout": held.record.id},
    )

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    filed = {r.summary: r for r in Ostler(docs).records().records}
    assert sorted(filed) == [
        "Sign-out leaves the saved report snapshots in the browser.",
        "The audit log loads every row at once.",
    ], sorted(filed)
    new = filed["The audit log loads every row at once."]
    assert (new.repo, new.area, new.pattern, new.filed_by, new.source_story) == (
        "web", "audit", "paginate", "qa", STORY)
    assert agent.powers[agent.calls.index("judge")] == "low", agent.powers
    assert not (docs / spec_dir() / "backlog-items.json").exists()


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
    assert okf.runs == 0


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


def test_the_owner_is_told_the_plan_s_shared_packages_then_the_check_set_s_without_repeats(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    check_set: Any,
) -> None:
    """Plan-declared shared directories come first, and a directory both name is listed once."""
    ostler()
    run_env = env()
    agent = _Agent(docs)
    check_set.shared = ["acme::packages/shared/auth", "acme::packages/shared/auth", "acme::lib"]

    drive_flow(Qa(story=STORY), run_env, agent)

    (call,) = check_set.calls
    assert call["story_id"] == STORY, call
    (turn,) = agent.args_for("qa-story")
    impl = _output(run_env, resolve_impl_context)
    assert turn["shared_packages"] == list(
        dict.fromkeys([*impl["shared_packages"], "acme::packages/shared/auth", "acme::lib"])
    ), turn["shared_packages"]
    assert turn["shared_packages"][-2:] == ["acme::packages/shared/auth", "acme::lib"]


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


def test_a_qa_turn_cut_at_its_deadline_parks_and_resumes_on_the_same_session(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    ostler()
    seen: list[str] = []
    agent = _Agent(docs, cut=("qa-story",))

    with patch.object(pyflow_park, "wait_for_answer", _answers(seen)):
        result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.calls == ["qa-story", "qa-story"], agent.calls
    (gate,) = seen
    assert "was cut after 180 minutes" in gate, gate
    assert "Its session is kept" in gate, gate
    first, second = agent.kwargs
    assert first["session_chain"] == second["session_chain"] != ""
    assert second["resume_session"] is True
    assert "staging bucket" in agent.args_for("qa-story")[1]["operator_context"]
    assert agent.nodes[0].deadline == agent.nodes[0].timeout == 10800.0


def test_a_cut_resolver_turn_lands_on_the_gate(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    ostler()
    seen: list[str] = []
    agent = _Agent(docs, statuses=("blocked", "passed"), cut=("resolve-operator",))

    with patch.object(pyflow_park, "wait_for_answer", _answers(seen)):
        result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    (gate,) = seen
    assert "needs a credential" in gate, gate
    assert "The resolver turn was cut after 180 minutes" in gate, gate


def test_turn_minutes_sets_the_owner_deadline(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    ostler()
    agent = _Agent(docs)

    drive_flow(Qa(story=STORY, turn_minutes=7), env(), agent)

    assert agent.nodes[0].deadline == agent.nodes[0].timeout == 420.0


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


def test_a_passing_scored_run_passes_with_no_dry_run_ledger_on_disk(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The scored run is the verdict: a scenario the owner names as proved, with no scratch log, does not hold the story back."""
    okf = ostler()
    agent = _Agent(docs, claims=(DRAFT_SCENARIO,))

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["qa-story"] == 1, agent.counts()
    assert okf.runs == 1, okf.runs
    assert not (Path(agent.args[0]["spec_dir"]) / QA_SCRATCH_DIRNAME / DRAFT_SCENARIO).exists()


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


def test_a_run_names_its_copy_with_what_a_container_name_takes() -> None:
    """The story id and the run id, joined, lowercased, and stripped of anything Docker refuses."""
    assert qa_runner_mod.copy_lease("PRED-01X", "20261010-1-ab") == "pred-01x-20261010-1-ab"
    assert qa_runner_mod.copy_lease("", "_Run 1") == "run-1"


def test_a_shared_stack_outlives_the_run(docs: Path) -> None:
    """With no per-run environment, the stack other runs adopt is never torn down at the end."""
    log = logging.getLogger("test")

    released = qa_nodes.release_copy(log, str(docs), lease="story-1-run")

    assert released.torn_down == "skipped", released


def _stack_copy(docs: Path, write: Callable[[Path, str], Path], monkeypatch: pytest.MonkeyPatch,
                tmp_path: Path, started_by: dict[str, Any]) -> list[str]:
    write(docs / "services" / "app" / "ops" / "stack.yml",
          "services:\n  web:\n    about: the web app\n    define: web.yml.j2\n    address: web\n    port: 80\n")
    monkeypatch.setenv(runtime.HOME_ENV, str(tmp_path / "env-home"))
    copy = runtime.copy_for(docs, SHARED_COPY)
    runtime.write_manifest(copy, {"repo": str(docs), "copy": SHARED_COPY, "started_by": started_by,
                                  "holder": runtime.holder_stamp(os.getpid())})
    copies: list[str] = []

    def _copy_down(_root: Path, *, copy_name: str, **_kw: Any) -> env_commands.EnvOutcome:
        copies.append(copy_name)
        return env_commands.EnvOutcome(True, f"tore {copy_name} down", {"ok": True})

    monkeypatch.setattr(env_commands, "cmd_down", _copy_down)
    return copies


def test_the_run_end_tears_down_the_stack_yml_copy_it_started(
    docs: Path,
    write: Callable[[Path, str], Path],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The run that brought the shared `stack.yml` copy up takes it down at its end."""
    log = logging.getLogger("test")
    copies = _stack_copy(docs, write, monkeypatch, tmp_path, runtime.holder_stamp(os.getpid()))

    torn = qa_nodes.teardown_stack(log, str(docs))

    assert torn.torn_down == "yes", torn
    assert copies == [SHARED_COPY]


def test_the_run_end_leaves_a_shared_copy_it_did_not_start(
    docs: Path,
    write: Callable[[Path, str], Path],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A copy up before the run, or started by hand, stays serving, and the run lets go of it."""
    log = logging.getLogger("test")
    for started_by in ({}, {"pid": 1, "started": "0"}):
        copies = _stack_copy(docs, write, monkeypatch, tmp_path, started_by)

        torn = qa_nodes.teardown_stack(log, str(docs))

        assert torn.torn_down == "skipped", torn
        assert copies == []
        manifest = runtime.read_manifest(runtime.copy_for(docs, SHARED_COPY).directory)
        assert manifest["holder"] == {}


def test_the_run_releases_the_copy_it_named_when_it_finishes(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The lease carries the story and the run, and the release at the end uses that same lease."""
    ostler()
    run_env = env()

    drive_flow(Qa(story=STORY), run_env, _Agent(docs))

    lease = _output(run_env, qa_nodes.stack_target)["lease"]
    assert lease.startswith("story-1-"), lease
    assert _output(run_env, qa_nodes.release_copy)["torn_down"] == "skipped"
    assert (run_env.writer.run_dir / qa_nodes.hold_copy.__name__).is_dir()


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
        "qa-story": qa_owner.MAX_LAPS + 1,
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
        QaOutcome(ok=False, message="service api-test is not running"),
        QaOutcome(ok=True, message="stack up", data={"entry_url": "http://x"}),
    ]
    monkeypatch.setattr(qa_runner_mod.leases, "up", lambda *a, **k: results.pop(0))
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.calls == ["qa-story"], agent.calls
    assert "stack.yml" in agent.args[0]["report"]
    assert "service api-test is not running" in agent.args[0]["report"]
    assert results == [], "the stack was never brought up a second time"


def test_no_stack_file_is_unneeded_not_a_runbook_refusal(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A book with no `ops/stack.yml` reaches the owner with nothing to repair and nothing to boot."""
    ostler()
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
    """A `qa_plan.py` that lints is the plan, and the owner is told so."""
    ostler()
    write(docs / spec_dir() / "qa_plan.py", QA_PLAN)
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.args[0]["standing_plan"] is True


BOOK_CALLS = [{"service": "api", "calls": ["ListX"]}]

def test_the_owner_is_told_which_books_judged_and_which_claims_they_left(
    qa_after_books: Callable[[dict[str, Any]], BooksLeft],
) -> None:
    """The seat covers each unreached claim by a scenario or reports it out of reach."""
    unreached = ["no request reaches the report service"]
    agent = qa_after_books({"unreached": unreached}).agent

    assert agent.args[0]["book_services"] == ["api"]
    assert agent.args[0]["book_unreached"] == unreached


JUDGED_NOTE = "every obligation of this story was judged by a service book"


def test_a_story_every_obligation_of_which_a_book_judged_passes_with_no_seat_turn(
    docs: Path,
    qa_after_books: Callable[[dict[str, Any]], BooksLeft],
) -> None:
    """With nothing left for a scenario to prove, a seat turn buys nothing."""
    agent, _, result, okf = qa_after_books({})

    assert result.status == "passed", result
    assert result.qa.notes == JUDGED_NOTE, result.qa
    assert agent.calls == [], agent.calls
    assert okf.runs == 0
    assert not (docs / spec_dir() / "qa_plan.py").exists()


def test_a_reprove_of_a_fully_book_judged_story_passes_with_no_plan_and_no_lint(
    docs: Path,
    ostler: Callable[..., _Ostler],
    write_json: Callable[[Path, Any], Path],
    monkeypatch: pytest.MonkeyPatch,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The rerun that follows leftovers must not need a plan file the first visit never wrote."""
    okf = ostler()
    write_json(docs / spec_dir() / "book-qa.json", {"services": BOOK_CALLS})
    linted: list[str] = []
    original = _Session.qa_lint if hasattr(_Session, "qa_lint") else Ostler.qa_lint

    def lint(self: Any, plan_file: Any) -> Any:
        linted.append(str(plan_file))
        return original(self, plan_file)

    monkeypatch.setattr(_Session, "qa_lint", lint, raising=False)
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY, rerun=True), env(), agent)

    assert result.status == "passed", result
    assert result.qa.notes == JUDGED_NOTE, result.qa
    assert agent.calls == [] and linted == [], (agent.calls, linted)
    assert okf.runs == 0


def test_one_unreached_claim_keeps_the_seat_turn(
    qa_after_books: Callable[[dict[str, Any]], BooksLeft],
) -> None:
    """A claim the book could not state is the scenario lane's even when every obligation is deferred."""
    agent, _, result, _ = qa_after_books({"unreached": ["no request reaches the report service"]})

    assert result.status == "passed", result
    assert agent.calls == ["qa-story"], agent.calls


def test_the_lane_runs_standalone_with_no_plan_context(
    docs: Path,
    ostler: Callable[..., _Ostler],
    monkeypatch: pytest.MonkeyPatch,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """QA against someone else's checkout: no dev lane ran, so there is no `plan-context.json`."""
    (docs / spec_dir() / "plan-context.json").unlink()
    ostler()
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
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY, stop_at_first_verdict=True), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["qa-story"] == 2, agent.counts()
    assert "Playwright" in agent.args[1]["report"]
    assert okf.runs == 2, "the repaired run was never retried"


def test_a_rerun_of_the_whole_plan_spends_no_owner_turn(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The standing plan is rerun and gated, and no model is asked anything."""
    okf = ostler()
    agent = _Agent(docs)
    (docs / spec_dir() / "qa_plan.py").write_text(QA_PLAN, encoding="utf-8")

    result = drive_flow(Qa(story=STORY, rerun=True), env(), agent)

    assert result.status == "passed", result
    assert agent.calls == [], agent.calls
    assert okf.only == [None], okf.only
    assert (okf.runs, okf.vets) == (1, 1)
    assert (docs / spec_dir() / "qa-evidence.json").is_file()


def test_a_red_rerun_goes_back_as_a_refix_without_an_owner_turn(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A rerun that fails is judged like a red QA: the dev owner gets it."""
    okf = ostler(fail_runs=99)
    agent = _Agent(docs)
    (docs / spec_dir() / "qa_plan.py").write_text(QA_PLAN, encoding="utf-8")

    result = drive_flow(Qa(story=STORY, rerun=True), env(), agent)

    assert result.status == "refix", result
    assert result.qa.status == "failed", result
    assert agent.calls == [], agent.calls
    assert okf.runs == 1, okf.runs


FIXTURE_PAGE = "docs/services/web-app/fixtures/well-stocked.md"


def _red(sid: str, *causes: str) -> dict[str, Any]:
    """One failed scenario whose failed checks carry the causes ostler gave them."""
    checks = [
        {
            "label": f"{sid} check {n}",
            "expected": "true",
            "actual": "false",
            "cause": cause,
            "precondition": FIXTURE_PAGE,
        }
        for n, cause in enumerate(causes, 1)
    ]
    return {sid: {"status": "failed", "assertions": 9, "failures": 1, "failed_checks": checks}}


def test_a_scenario_past_its_wall_clock_ceiling_parks_at_the_operator(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    overran = {"copy-link": {"status": "failed", "assertions": 9, "failures": 1, "overran": True}}
    okf = ostler(fail_runs=1, scenarios=(overran, {}))
    agent = _Agent(docs)
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", _parked_at(seen)), pytest.raises(_Parked):
        drive_flow(Qa(story=STORY), env(), agent)

    assert agent.calls == ["qa-story"], agent.calls
    assert len(seen) == 1 and "copy-link" in seen[0], seen
    assert "wall-clock ceiling" in seen[0] and "60 minutes" in seen[0], seen
    assert "too long" in seen[0] and "hangs" in seen[0], seen
    assert okf.runs == 1, okf.runs


def test_an_environment_red_stops_at_the_operator_gate_without_a_refix(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A fixture that cannot start says nothing about the product or the book."""
    okf = ostler(fail_runs=1, scenarios=(_red("copy-link", "environment", "app"),))
    agent = _Agent(docs)
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", _parked_at(seen)), pytest.raises(_Parked):
        drive_flow(Qa(story=STORY), env(), agent)

    assert agent.calls == ["qa-story"], agent.calls
    assert len(seen) == 1 and "the QA environment" in seen[0], seen
    assert "copy-link check 1" in seen[0] and FIXTURE_PAGE in seen[0], seen
    assert okf.runs == 1, okf.runs


@pytest.mark.parametrize("cause", ["book", "arrangement"])
def test_a_book_side_red_goes_back_to_the_owner_to_repair_the_book(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    cause: str,
) -> None:
    """A scenario that never reached its claim is the book's to repair, not a finding."""
    okf = ostler(fail_runs=1, scenarios=(_red("copy-link", cause), {}))
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    report = agent.args[1]["report"]
    assert "Check: the book" in report and FIXTURE_PAGE in report, report
    assert "returned no finding" not in report, report
    assert agent.args[1]["failed_scenarios"] == [
        {"id": "copy-link", "failed_assertions": ["copy-link-1"]}
    ], agent.args[1]["failed_scenarios"]
    assert okf.runs == 2, okf.runs


def test_a_product_red_goes_to_dev_as_a_finding_named_for_its_scenario(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A claim that failed on a held condition reaches the developer on the next lap."""
    okf = ostler(fail_runs=99, scenarios=(_red("copy-link", "app"),))
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "refix", result
    assert [f.id for f in result.findings] == ["copy-link"], result.findings
    assert "copy-link check 1" in result.findings[0].issue, result.findings
    assert agent.calls == ["qa-story"], agent.calls
    assert okf.runs == 1, okf.runs


def test_a_product_red_beside_a_book_red_goes_to_dev_first(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The defect reaches the builder now, and the book's repair waits for the next QA."""
    scenarios = {**_red("copy-link", "app"), **_red("share-link", "book")}
    ostler(fail_runs=99, scenarios=(scenarios,))
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "refix", result
    assert [f.id for f in result.findings] == ["copy-link"], result.findings
    assert agent.calls == ["qa-story"], agent.calls


def test_an_unattributed_red_is_still_the_owner_s_to_classify(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """With no side named, the owner reads the failure and decides whose it is."""
    ostler(fail_runs=1, scenarios=(_red("copy-link", "unattributed"), {}))
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    report = agent.args[1]["report"]
    assert "returned no finding" in report and "copy-link" in report, report
    assert "Check: the book" not in report, report


def test_stop_at_first_verdict_repairs_a_book_side_red(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A red that never tested the product is not a verdict on it."""
    okf = ostler(fail_runs=1, scenarios=(_red("copy-link", "arrangement"), {}))
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY, stop_at_first_verdict=True), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["qa-story"] == 2, agent.counts()
    assert "Check: the book" in agent.args[1]["report"]
    assert okf.runs == 2, okf.runs


def test_a_red_rerun_on_the_book_side_takes_an_owner_turn(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A rerun hands the developer only what the product failed."""
    okf = ostler(fail_runs=1, scenarios=(_red("copy-link", "book"), {}))
    agent = _Agent(docs)
    (docs / spec_dir() / "qa_plan.py").write_text(QA_PLAN, encoding="utf-8")

    result = drive_flow(Qa(story=STORY, rerun=True), env(), agent)

    assert result.status == "passed", result
    assert agent.calls == ["qa-story"], agent.calls
    assert "Check: the book" in agent.args[0]["report"]
    assert okf.runs == 2, okf.runs


UNREACHED_CLAIMS = ["no request reaches the report service", "the audit line names the actor"]


def test_a_story_whose_services_all_have_a_book_owes_the_scenario_seat_only_the_unreached_claims(
    qa_after_books: Callable[[dict[str, Any]], BooksLeft],
) -> None:
    agent, owed, _, _ = qa_after_books({"unreached": UNREACHED_CLAIMS})

    assert owed == UNREACHED_CLAIMS
    assert agent.args[0]["lease"]
    assert agent.args[0]["book_unreached"] == UNREACHED_CLAIMS


def test_the_claims_file_of_a_book_judged_story_with_a_defect_holds_no_claim(
    qa_after_books: Callable[[dict[str, Any]], BooksLeft],
) -> None:
    finding = {"id": "f", "target": "acme/x:1", "issue": "the list drops the token", "repair": "keep it"}

    assert qa_after_books({"findings": [finding], "unreached": UNREACHED_CLAIMS}).owed == []


def test_a_story_naming_no_service_gets_a_seat_turn_and_an_empty_claims_file(
    docs: Path,
    ostler: Callable[..., _Ostler],
    write: Callable[[Path, str], Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    ostler()
    write(epics_root() / STORY_REL / "story.md", STORY_MD.replace("services: [app]\n", ""))
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.calls == ["qa-story"], agent.calls
    assert agent.args[0]["book_services"] == []
    assert json.loads((docs / spec_dir() / "qa-unreached.json").read_text(encoding="utf-8")) == []


def test_a_qa_run_never_creates_docs_services(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    ostler()

    result = drive_flow(Qa(story=STORY), env(), _Agent(docs))

    assert result.status == "passed", result
    assert not (docs / "docs" / "services").exists()
    assert not (docs / spec_dir() / "qa-okf-context.json").exists()
