"""End-to-end tests for the `qa` flow — the gates, the four loops, and the operator.

Ninety-one YAML nodes became twenty-five states holding five bounded loops that all rejoin
at `build_context`: the context repair, the plan rework, the QA fix, the setup repair and
the regression fix. What is worth testing is which arm each verdict takes, what makes each
loop terminate, and — above all — that the evidence gate cannot be talked past.

**Five seams, all of them a process boundary.** `ostler qa context|validate|run`, `ostler
artifact vet`, `ostler.qa.stack.ensure_stack` (docker) and the regression suite's
`subprocess.run` are the only things patched, because they are the only things that leave
the filesystem. Everything else is the real node: `clear_qa_evidence` really deletes last
pass's `qa/`, `resolve_impl_context` really decodes the plan against a real workspace,
`stamp_specs` really stamps, `check_feedback` really consumes the inbox, and — the point of
the flow — `verify_qa_evidence` really reads the artifacts off disk and really decides. The
scripted `qa_run` writes what the runner writes, so a pass here is a pass the gate had to be
convinced of rather than one it was told about.
"""
from __future__ import annotations

import json
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

from workhorse_workflows.coder.qa import flow as qa_flow
from workhorse_workflows.coder.qa.flow import Qa
from workhorse_workflows.coder.qa.nodes import evidence as evidence_nodes
from workhorse_workflows.coder.qa.nodes import qa as qa_nodes
from workhorse_workflows.coder.qa.nodes import regression as regression_nodes
from workhorse_workflows.coder.qa.nodes.qa import QA_SCRATCH_DIRNAME
from workhorse_workflows.coder.shared import okf as okf_nodes
from workhorse_workflows.coder.shared import qa_support
from workhorse_workflows.coder.shared.dev import resolve_impl_context

STORY = "STORY-1"
EPIC = "EPIC-1"
SPEC_REL = f"docs/specs/{STORY}"
STORY_REL = f"docs/epics/{EPIC}/stories/{STORY}"
CONTEXT_REL = f"{STORY_REL}/context.md"

#: What an escalating resolver leaves in `context.md` before handing the block to a person —
#: the shape `shared/prompts/resolve-operator.md` mandates for the escalated arm.
ESCALATION_NOTE = (
    "STATUS: AWAITING_OPERATOR\n\n"
    "Re-ran the stack twice; the emulator comes up but the suite still cannot reach it.\n"
    "Please confirm which host the suite should dial.\n"
)

#: What that resolver reports it ruled out, which the composed gate publishes verbatim.
RESOLVER_TRIED = (
    "ran `ostler qa run --scenario SC-1` twice — identical connection refused",
    "checked the emulator port in the runbook against the container — they match",
)

#: The epic index ostler parses to learn the story exists — same shape the `dev` suite uses.
EPIC_MD = """---
title: Epic One
status: active
---

# Epic One

## Stories

### STORY-1

- title: Story One
"""

#: An *authored, built* story. `prepare_story` refuses an unauthored one, and QA runs after
#: the dev phase, so the implementation status is the one line that differs from `dev`'s.
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

## Implementation Status

- **Status**: Done
"""

#: The dev phase's plan, decoded by `resolve_impl_context` for the repo grant and the QA
#: source roots. This service declares no `regression:` command, so `detect_regression_suites`
#: resolves nothing and the regression loop is out of the way of every test not about it.
API_SERVICE: dict[str, Any] = {
    "repo": "api",
    "path": ".",
    "type": "go",
    "plan_file": "plan-api.md",
}

#: The same plan with a second service, one that *does* declare a `regression:` command —
#: which is the only thing that puts a committed journey suite at risk. The type is a
#: placeholder on purpose: what selects the suite is the declaration, never the stack.
WEB_SERVICE: dict[str, Any] = {
    "repo": "web",
    "path": ".",
    "type": "web-app",
    "plan_file": "plan-web.md",
}

#: The one scenario `QA_PLAN` declares, and therefore the one the draft nominates as its
#: riskiest when the fake author answers.
DRAFT_SCENARIO = "the-thing-exists"

QA_PLAN = '''from ostler_qa import Qa, plan, scenario, target

plan(run_id="qa-story", story="the-story")
api = target("api")


@scenario(target=api, mechanism="live", covers=["ac:1"])
def the_thing_exists(qa: Qa) -> None:
    """The thing exists."""
    qa.check("it exists", True)
'''


# --------------------------------------------------------------------------- fixtures


RUNBOOK_REL = "docs/features/app/ops/qa-stack.md"

#: The smallest runbook `load_stack` returns a manifest for: a driver and one `service` step
#: whose health gate proves it. Deliberately **no** `entry-url:` — a test that reaches the real
#: `ensure_stack` would then open an HTTP readiness probe against a host that does not resolve
#: and poll it until the boot timeout, once per test. `run: true`/`health: true` are the two
#: cheapest possible recipes, which is what keeps this fixture runnable as well as readable.
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
    # Every repo that reaches QA declares how its stack comes up; a repo that does not is
    # the `ready="none"` case, which has its own test and deletes this node to reach it.
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
    """A real `web` repo that declares a journey suite, and a plan that names it.

    `detect_regression_suites` resolves nothing for a service that declares no `regression:`
    command, so the regression tests need a repo whose `agents.yml` names one — the command
    itself is the seam, and `_run` is what the fake replaces.
    """
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


# --------------------------------------------------------------------------- the seams


class _Ostler:
    """ostler's four QA subcommands and its artifact vetter, scripted at the process edge.

    Every knob is a count of *leading* calls that misbehave, so a test says "the packet is
    unmappable twice" rather than scripting a whole sequence. `qa_run` writes the four files
    a real runner writes — the evidence, the run log, the run manifest, the report — because
    the evidence gate below it is real and reads all of them.
    """

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
        #: A count of *leading* runs that come back `blocked` and then recover — the shape a
        #: real environment fault takes when the setup fixer actually repairs it.
        #: `blocked_problems` is the other shape: blocked for good.
        self.block_runs = block_runs
        #: The per-scenario payload a real run reports, entry *i* for run *i*, the last one
        #: repeating. Empty — the default — omits the key entirely, which is every test that
        #: does not care: the flow's repeat detector reads it and is inert without it.
        self.scenarios = scenarios
        #: When set, every run comes back `blocked` naming these runtime requirements — the
        #: shape `check_runtime_requirements` produces for a missing Playwright or ffmpeg.
        self.blocked_problems = blocked_problems
        self.context_invalid = context_invalid
        #: A count of *leading* schema failures. `plan_invalid_passes` is the other shape:
        #: which validation passes fail, for interleaving schema and judgement laps.
        self.plan_invalid = plan_invalid
        self.plan_invalid_passes = plan_invalid_passes
        #: Whether every schema refusal says the *identical* thing. A validator re-reading a
        #: file it already refused really does repeat itself, and the flow now reads that
        #: repetition as a repair that answered nothing — so the default varies the finding
        #: per pass, which is what a lane still moving looks like, and the tests about
        #: *identical* refusals set this.
        self.plan_invalid_stuck = plan_invalid_stuck
        self.vet_problems = vet_problems or []
        self.runs = 0
        self.contexts = 0
        self.context_validations = 0
        self.plan_validations = 0
        self.vets = 0
        self.context_args: list[dict[str, Any]] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> _Ostler:
        """Stand in for the `Ostler` the nodes construct, in all three modules that do.

        A session subclasses the real facade rather than replacing it, so the methods this
        script says nothing about — `qa_lint`, `qa_tools_catalog` — still run for real
        against the repo under test, and a signature that drifts from the API fails at
        type-check rather than passing a test that no longer describes anything.
        """
        for module in (okf_nodes, qa_nodes, evidence_nodes):
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
        """The artifacts `ostler qa run` leaves behind, which the evidence gate reads.

        An un-modeled surface: no OKF criteria and no obligations, proving itself on the run
        log's command assertions. That is the cheapest *legitimate* passing shape, so a gate
        that rejects it is broken and a gate that accepts a fabricated one is too.
        """
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
        """The per-assertion records of this run, labelled by scenario when there are any.

        A test that scripts `scenarios` is describing a run at scenario granularity, and the
        run log is where that granularity is readable — `_plan_args` mines it for the ids of
        the assertions each failing scenario left red, and hands them to the repair turn as
        its worklist. Leaving the label off would make every failing scenario's worklist
        empty and let a brief that carries nothing pass for one that carries the failures.
        """
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

    # -- the packet -------------------------------------------------------

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
        # The nodes pass an absolute spec dir, so this skips the real `_resolve` — which
        # would load the graph just to join a path that is already anchored.
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

    # -- the plan ---------------------------------------------------------

    def qa_validate(
        self, plan_file: str | Path, *, spec: str | Path | None = None
    ) -> QaOutcome:
        self.script.plan_validations += 1
        # The plan turn is supposed to have written this; validating a file that is not
        # there would make every plan-gate test pass for the wrong reason.
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

    # -- the run ----------------------------------------------------------

    def qa_run(
        self,
        plan_file: str | Path,
        *,
        spec: str | Path | None = None,
        stop_on_fail: bool = False,
        label: str | None = None,
    ) -> QaOutcome:
        script = self.script
        script.runs += 1
        if script.runs <= script.block_runs:
            return script._blocked(["target 'web' requires the Playwright Python package"])
        if script.blocked_problems is not None:
            # A blocked run writes nothing: it never executed a scenario.
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

    # -- the artifact contract --------------------------------------------

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
    """The declared journey command, scripted. `fail_runs` leading invocations exit non-zero."""

    def __init__(self, *, fail_runs: int = 0) -> None:
        self.fail_runs = fail_runs
        self.calls: list[str] = []

    def __call__(self, command: str, cwd: Path, timeout: int) -> regression_nodes._Outcome:
        self.calls.append(command)
        if len(self.calls) <= self.fail_runs:
            return regression_nodes._Outcome(1, "FAIL journeys/login.spec.ts › logs a user in\n")
        return regression_nodes._Outcome(0, "12 passed\n")


# --------------------------------------------------------------------------- the agent


class _Agent:
    """The flow's eleven prompts, scripted on the axes its states branch on.

    Each handler writes what its prompt claims to write — the plan turn writes `qa_plan.py`,
    the resolver writes the operator's answer into `context.md` — because a handler that only
    returned a status would be testing the state machine against a fiction.
    """

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
        #: What the repair turn leaves in the dry-run scratch directory: `passed` writes a
        #: green log per scenario the brief named, `failed` a red one, `empty` a log with no
        #: assertion in it, and `missing` writes nothing at all. Only `passed` gets past
        #: `verify_qa_dry_run`; the other three are the refusals it exists to make.
        self.dry_run = dry_run
        #: The same four shapes, for the *first draft*, which nominates the scenarios it
        #: judged riskiest and proves them the same way. A knob of its own because the two
        #: turns are gated separately: a test that wants a repair refused wants the draft
        #: that preceded it to have reached the runner normally.
        self.plan_dry_run = plan_dry_run
        #: What the draft *names* as proved, which the flow gates it on. Separate from the
        #: shape it leaves on disk, because the two disagreeing is the whole failure mode:
        #: an empty nomination is a plan with nothing worth proving, not a plan that lied.
        self.plan_proves = plan_proves
        #: The same four shapes, for the *per-scenario* fixer. A separate knob because the
        #: two turns prove different things — a plan repair proves the scenarios it rewrote,
        #: a scenario fix proves the one item it was handed — and a test that wants one
        #: refused nearly always wants the other left green. A tuple scripts one shape per
        #: attempt at the *same* item, which is the only way to ask for two refusals that
        #: differ: two identical ones are a stall and never reach the second budget arm.
        self.item_dry_run = (
            (item_dry_run,) if isinstance(item_dry_run, str) else item_dry_run
        )
        self.repair = repair
        self.disposition = disposition
        # A count of *leading* assessments that send the failure to the plan author, after
        # which the assessment behaves normally.
        self.repair_plans = repair_plans
        self.failure_class = failure_class
        self.objective = objective
        self.assessment_class = assessment_class
        # These default to *nothing*: the flow's prose fall-through for a gate that named no
        # findings is the pre-existing behaviour and most of the suite still exercises it, so
        # a fake that invented findings would hide it.
        self.assessment_findings = assessment_findings or []
        self.audit = audit
        self.audit_findings = audit_findings or []
        self.triage = triage
        self.setup = setup
        self.qa_fix = qa_fix
        self.escalate = escalate
        self.scope = scope
        self.explode = explode or set()
        #: Stems whose turn is stopped at its wall-clock cap. Unlike `explode`, the handler
        #: runs *first* and only then does the raise happen: an overrun turn leaves behind
        #: whatever it had written when the clock ran out, and a fake that raised instead of
        #: writing would be testing the flow against a turn that never started.
        self.cut = cut or set()
        #: Prompt stems whose turn answers "I cannot get there from here". The reply replaces
        #: the handler's rather than decorating it, because a turn that refused did not also
        #: write the file its handler stands in for — and a fake that wrote it anyway would
        #: test the flow against a refusal nobody has ever seen.
        self.refuses = refuses or set()
        self.calls: list[str] = []
        self.args: list[dict[str, Any]] = []
        self.dirs: list[list[str]] = []

    # -- the seam ---------------------------------------------------------

    #: The plan author's two prompts. `plan-qa` writes the first draft and `repair-qa-plan`
    #: edits the cited scenarios on every later lap, so they are one role and share one lap
    #: number: `nth` means the author's nth turn, not the nth turn of one of its prompts.
    PLAN_STEMS = ("plan-qa", "repair-qa-plan")

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        stem = Path(node.prompt).stem
        data = ctx.as_dict()
        self.calls.append(stem)
        self.args.append(data)
        self.dirs.append(list(node.add_dirs or []))
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
            # The transport-level signal, not the pyflow one: raising `AgentTimeout` here
            # would skip the engine's translation and let the flow pass over a chain that
            # does not connect. `retries=0` on the node is what makes this the first and
            # only invocation.
            raise BackendInvocationError(f"timed out after {node.timeout}s", timed_out=True)
        return f"(scripted) {node.prompt}", answer

    def counts(self) -> Counter[str]:
        return Counter(self.calls)

    def planned(self) -> int:
        """How many plan-authoring turns have run, across the draft and every repair."""
        return sum(self.counts()[stem] for stem in self.PLAN_STEMS)

    def args_for(self, stem: str) -> list[dict[str, Any]]:
        return [a for s, a in zip(self.calls, self.args, strict=True) if s == stem]

    def plan_args(self) -> list[dict[str, Any]]:
        """Every plan turn's brief in order, whichever of its two prompts served it."""
        return [a for s, a in zip(self.calls, self.args, strict=True) if s in self.PLAN_STEMS]

    def fix_args(self) -> list[dict[str, Any]]:
        """Every unaided lap of the code-fix loop, whichever fixer prompt served it.

        The loop spends its lap one scenario at a time when the run reported which scenarios
        failed, and on the whole report when it did not — an evidence-class finding, a
        routed finding, an operator's note. Both are laps of the same budget.

        The operator gate runs `apply-qa-fixes` too, with `operator_feedback` in its args.
        Those are not the loop's own laps and are excluded here, which is the distinction
        every caller of this wanted.
        """
        return [
            a
            for s, a in zip(self.calls, self.args, strict=True)
            if s == "fix-qa-scenario"
            or (s == "apply-qa-fixes" and "operator_feedback" not in a)
        ]

    # -- one handler per prompt -------------------------------------------

    def _repair_qa_context(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """One key: did the packet heal? The running QA verdict follows from that."""
        return {
            "status": self.repair,
            "notes": f"the diff touches code no feature node owns (pass {nth})",
        }

    def _plan_qa(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """The draft, and the proof of the scenarios it nominated as its riskiest.

        `QA_PLAN` holds exactly one scenario, so the nomination is that one. A fake that
        wrote the file and named nothing would stand in for a turn its own prompt refuses,
        and every draft in this suite would reach the runner unproven — which is the
        behaviour this knob exists to be able to ask for on purpose.
        """
        (Path(data["spec_dir"]) / "qa_plan.py").write_text(QA_PLAN, encoding="utf-8")
        for scenario in self.plan_proves:
            self._prove(data, scenario, self.plan_dry_run)
        return {
            "status": "done",
            "notes": f"plan pass {nth}",
            "proved_scenarios": list(self.plan_proves),
        }

    def _prove(self, data: dict[str, Any], scenario: str, shape: str) -> None:
        """Write one scenario's scratch dry-run log, in whichever of the four shapes.

        `passed` is a log with a green assertion in it, `failed` a red one, `empty` a log
        that reached no assertion at all, and `missing` no log — the three refusals
        `verify_qa_dry_run` exists to make, plus the one that gets past it.
        """
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
        """The repair turn rewrites the plan *and* proves it, exactly as its prompt demands.

        The proof is the scratch run log the flow's dry-run gate reads: one out-dir per
        scenario the brief named, holding the assertions that scenario recorded. A fake that
        only returned `{"status": "done"}` would stand in for a turn the gate refuses, so
        every repair lap in this suite would be a gate failure rather than the loop under
        test. `self.dry_run` is what lets a test ask for the refused shapes on purpose.
        """
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
        # A runner failure the assessment confirms is a product defect unless the test says
        # otherwise; a runner pass has nothing to classify.
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
        """One scenario's fixer, which proves its own item exactly as its prompt demands.

        Same scratch layout as `_repair_qa_plan`, one out-dir instead of several: the brief
        names a single scenario, and `verify_qa_dry_run` is called for that one id.
        """
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
        """An escalating resolver writes its note into the same file, it does not write nothing.

        `shared/prompts/resolve-operator.md` mandates `STATUS: AWAITING_OPERATOR` plus what it tried
        and what the human must supply — the thing the escalated `Await` must not overwrite.
        """
        (self.docs / CONTEXT_REL).write_text(ESCALATION_NOTE, encoding="utf-8")



#: Where the QA stack is declared now that it is a book node rather than a root YAML file.
#: `ostler.qa.runbook.load_stack` globs `docs/features/**/*.md`, so the `ops/` directory is
#: not decoration — a runbook written anywhere else is one the reader never sees.


def _answers(seen: list[str], *, scope: str = "story") -> Callable[..., None]:
    """A stand-in for the human an `Await` is waiting on, patched over `wait_for_answer`."""

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text(encoding="utf-8"))
        path.write_text(
            f"STATUS: ANSWERED\nSCOPE: {scope}\n\nUse the staging bucket.\n", encoding="utf-8"
        )

    return answered


class _Parked(Exception):
    """Raised by the patched `wait_for_answer` to stop a run right at its `Await`.

    A budget exhaustion always escalates now, and never terminates on its own — so a test
    that only wants to prove the escalation was reached, without hand-scripting an answer
    and the cascade that follows it, stops the run here instead. `otel.wait` re-raises
    rather than swallowing, and nothing in `drive()` catches around the `wait_for_answer`
    call, so this propagates cleanly out of `drive_flow` to `pytest.raises`.
    """


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


# --------------------------------------------------------------------------- happy path


def test_one_clean_pass_through_every_gate(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Context, plan, run, evidence, audit, sentinels — all first try, no assessment.

    A green runner skips the `qa-story` assessment turn entirely: the sieve's arms all
    route failures, blocks and dispositions, and the pass is judged by the evidence gate
    and the audit. The clean path spends exactly two agent turns.
    """
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
    # A fresh story has no plan on disk, so an authoring turn ran at all.
    assert agent.planned() == 1, agent.counts()
    # One packet build, one run, and the evidence contract really was vetted.
    assert (okf.contexts, okf.runs, okf.vets) == (1, 1, 1)
    # The runner's artifacts are on disk and the gate accepted them on their own terms.
    assert (docs / SPEC_REL / "qa-evidence.json").is_file()
    assert (docs / SPEC_REL / "qa" / "qa-run.ndjson").is_file()


def test_a_story_that_cannot_be_resolved_fails_the_run_without_spending_a_turn(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """An unresolvable story is a defect in whatever asked for this slug, and fails as one.

    Not a status: ending `exhausted` says the story was QA'd and could not be carried,
    when what happened is that it was never found. Nothing is spent proving that — the
    raise is `setup`'s, before the first turn.
    """
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
    """The port's one deliberate `add_dirs` divergence, asserted off the node the engine built.

    `dev` and `docs` grant the whole workspace; `qa` grants `affected_repo_paths`, which is
    what its YAML did at all eleven agent nodes. Nothing else in the suite would notice if
    the flow quietly widened the grant.
    """
    ostler()
    agent = _Agent(docs)
    run_env = env()

    drive_flow(Qa(story=STORY), run_env, agent)

    expected = _output(run_env, resolve_impl_context)["affected_repo_paths"]
    assert expected == [str(docs)], expected
    assert agent.dirs == [expected] * len(agent.calls), agent.dirs


# --------------------------------------------------------------------------- the packet


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
    # The packet was genuinely rebuilt rather than re-validated in place.
    assert okf.contexts == 2, okf.contexts
    # The repair turn was handed the validator's own complaint.
    assert "no feature node" in agent.args_for("repair-qa-context")[0]["context_notes"]


def test_a_gate_that_passed_hands_the_plan_turn_no_diagnostics(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A pass is not a finding, so it must not reach `plan_qa` as one.

    `plan-qa.md` renders the `*_notes` under an instruction to repair the existing plan from
    what the gates said about it. `validate_okf_context` spells a pass "QA OKF context is
    valid." — carry that into the notes and the plan turn is told to repair a plan from the
    diagnostic that nothing is wrong. A coder run read the brief exactly as written, answered
    "I'm leaving both files unchanged", and burned one of three plan reworks on a no-op turn.

    The repair path is what exposes it: the flow re-enters `plan` from `build_context` after a
    rebuild, so the note the *passing* rebuild wrote is the one `plan` reads.
    """
    ostler(context_invalid=1)
    agent = _Agent(docs, repair="repaired")

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    # The rebuild passed, so `plan` is entered with a clean slate — not with the pass restated
    # as something to fix. `context_status` still carries the verdict; that is the routing
    # field, and it is not rendered as a finding.
    plan_args = agent.args_for("plan-qa")[0]
    assert plan_args["context_status"] == "passed", plan_args
    assert plan_args["context_notes"] == "", plan_args
    assert all(
        plan_args[key] == ""
        for key in ("plan_validation_notes", "run_assessment_notes", "audit_notes")
    ), plan_args
    # No repo in this fixture opts a tool into `agents.yml`, so the catalog resolves empty
    # rather than failing the plan turn.
    assert plan_args["qa_tools"] == [], plan_args


def test_the_context_repair_loop_is_bounded_at_three(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A repairer that claims success on a packet that stays unmappable costs three passes,
    then escalates — there is no cap on re-escalation, only on the repair loop itself."""
    okf = ostler(context_invalid=9)
    # `escalate=True` throughout the budget tests: the resolver investigates and declines to
    # answer, which is what leaves the boundary these tests are about — the budget's own —
    # the only thing that moved before the run parks at the operator gate.
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
    # `apply_resolved` runs the fix prompt and spends a rework on the operator's answer.
    assert agent.counts()["apply-qa-fixes"] == 1, agent.counts()
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


# --------------------------------------------------------------------------- the plan gate


def test_a_plan_that_never_parses_spends_only_the_schema_budget(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Three schema repairs buy four plan turns and never reach the stack, then escalate.

    The schema-repair count itself is not one of the counters threaded into the escalation
    body (only `qa_rework`/`plan_rework`/`context_rework`/`setup_rework` are), so there is
    no live assertion for the old "3 QA-plan schema repair" phrase — this test now only
    proves where the run actually stopped.
    """
    okf = ostler(plan_invalid=9)
    agent = _Agent(docs, escalate=True)
    seen: list[str] = []

    with (
        patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)),
        pytest.raises(_Parked),
    ):
        drive_flow(Qa(story=STORY), env(), agent)

    # One draft and three repairs: a plan that does not parse is repaired, not re-authored.
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
    """The lap-discipline rule, on the gate that had only a count bounding it.

    `plan_invalid_stuck` is a validator saying the identical sentence back: the repair turn
    was handed that sentence, edited the file, and earned it again. Every further lap buys
    the same turn for the same answer, so the second one goes to the operator — which is an
    `Await` through the resolver path and not an ending, and the test proves that by the run
    parking rather than by any status.

    The budget is untouched by this: `MAX_PLAN_VALIDATION_REWORKS` is three, and the run
    stops at one repair.
    """
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
    """The other half of the rule: a lane that is still moving keeps its laps.

    Without this the repeat detector reads as "two refusals of any kind end the plan lane",
    which would price the schema budget at one. What ends it is *sameness* — a validator
    naming a different defect each pass is a repair that fixed the last one.
    """
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

    # Two schema repairs and one post-run repair still leave a judgement repair, so the
    # story now reaches a verdict where the shared budget gave up on it.
    assert result.status == "passed", result
    assert okf.runs == 2
    # Draft, two schema repairs, then the post-run repair — every plan lap revalidates.
    assert okf.plan_validations == 4


def test_the_repair_turn_is_told_which_scenarios_failed_and_on_which_assertions(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The repair's worklist is the failing set itself, not a paragraph describing it.

    Standing, the brief carried the runner's prose notes and the author re-derived what had
    failed from them — sometimes onto a scenario that was green. The ids come off the run
    log, which is the same artifact the evidence gate reads, so the two cannot disagree.
    """
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
    """The draft has no *failing* set — but it does have scenarios it nominated and ran.

    The two halves of the same brief: `failed_scenarios` is the repair turn's contract and is
    empty here, while the ids the draft proved come back in its own reply and are gated on
    the way to the runner. A draft that proves what it nominated reaches the runner once.
    """
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
    """The lever: the first draft is proof-gated too, and its refusal costs no suite run.

    `plan_dry_run="missing"` is an author that named the scenario it judged riskiest and
    never executed it. That used to be free — the draft went to the runner on its own word,
    and a locator matching nothing was discovered by a full suite run and a repair lap. Here
    the same defect is caught before the runner is reached at all.
    """
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
    """The other refusal: it ran, and it failed. Same gate, same lap, still no suite run."""
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
    """A plan with nothing worth proving must still reach the runner.

    The gate is over the ids the turn named, not over the existence of a dry run: an empty
    nomination skips it exactly as the repair path's empty failing set does. Without this
    the lever would turn "the author judged nothing risky" into an unfixable repair lap.
    """
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
    """The point of the gate: an unproven repair is refused where the refusal is cheap.

    A suite run is the most expensive thing this flow does, and the plan-repair loop has six
    laps to spend on it. Believing the turn's own "repaired" cost one full run per lap to
    disprove — and the run came back with the same scenario red, which then looked like a
    stall in the *product* rather than a repair that never executed anything.
    """
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
    # And the second refusal says exactly what the first said, so the lane stops there rather
    # than spending the rest of `MAX_PLAN_REWORKS` re-earning it. The budget is still the one
    # it is spent from — no new counter beside it — it is just no longer the only thing that
    # ends this loop.
    assert agent.counts()["repair-qa-plan"] == 2, agent.counts()
    assert len(seen) == 1 and "plan repair" in seen[0], seen


def test_a_repair_whose_dry_run_is_still_red_is_not_a_finished_repair(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The turn ran the scenario and left it failing — which is the answer, honestly come by,
    and still not a repair. The next brief says so rather than the next suite run."""
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


def test_the_stacked_plan_budgets_cannot_multiply(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Alternating between the two budgets does not buy their product in laps.

    Each guard bounds its own stage and nothing bounded the sum, so a plan that failed
    validation, then was sent back by the assessment, then failed validation again spent a lap
    that neither ceiling had yet reached — twelve legal laps between them. A live story took
    thirteen turns of `plan-qa` exactly that way. Here the laps are spread across both stages —
    schema failures interleaved with a runner the assessment never accepts — so no stage budget
    is exhausted and only the total ends the run.
    """
    ostler(plan_invalid_passes=(2, 4, 6), fail_runs=99)
    agent = _Agent(docs, repair_plans=99, escalate=True)
    seen: list[str] = []

    # `plan_rework_total` is not one of the counters threaded into the escalation body, so
    # there is no live equivalent for the old "8 total QA-plan lap" phrase — what still
    # proves the total-lap ceiling (rather than either stage ceiling) is what stopped this
    # run is the lap count itself, below.
    with (
        patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)),
        pytest.raises(_Parked),
    ):
        drive_flow(Qa(story=STORY), env(), agent)

    # One author turn per charged lap, plus the draft that opened the lane — the draft is
    # deliberately free, because charging it would price the lane at one lap less than the
    # ceiling names.
    assert agent.planned() == qa_flow.MAX_TOTAL_PLAN_LAPS + 1, agent.counts()


def test_a_plan_turn_cut_at_its_budget_is_repaired_rather_than_failing_the_run(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """An overrun `plan-qa` lands on the repair lane, because its deliverable is a file.

    The turn's reply is discarded either way — what `_validated` reads is `qa_plan.py` off
    disk. So a turn stopped at its twenty-minute cap has still produced something, and the
    draft it left is worth a `power="low"` repair pass rather than a dead run: standing, the
    ladder threw the draft away and re-authored from nothing three times over, at the
    authoring tier and for another twenty minutes each, before ending the run with no QA
    verdict at all.

    `plan_invalid=1` is what a truncated file looks like at the seam the flow actually
    consults — `ostler qa validate` refusing to import it.
    """
    ostler(plan_invalid=1)
    agent = _Agent(docs, cut={"plan-qa"})

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["repair-qa-plan"] == 1, agent.counts()
    # The repair turn is told the file is a stopped draft rather than a mistake, so its
    # worklist is "finish it" and not "re-author it".
    brief = agent.args_for("repair-qa-plan")[0]
    assert "stopped at its wall-clock budget" in brief["plan_validation_notes"], brief


def test_a_plan_lane_past_its_wall_clock_budget_carries_on(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A spent wall-clock budget is advisory: the lane behaves exactly as if it had room.

    A zero `PLAN_LANE_BUDGET_S` is the seam — the first plan turn charges a real, tiny delta, so
    every plan-lane comparison is past by the time `_validated` decides what to do next. It
    used to demote a parsing plan straight to the runner and give up on one that would not
    import; now it decides nothing at all.
    """
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
    """Past the budget with a plan that will not import, the schema repairs still run.

    A clock cannot tell a lane going nowhere from one three turns from green, and cutting on
    it discarded stories that were converging — the give-up here names the lap ceiling that
    was actually reached, which is a statement about the work rather than about its speed.
    """
    ostler(plan_invalid=99)
    agent = _Agent(docs, escalate=True)
    seen: list[str] = []

    # `plan_validation_rework` is not threaded into the escalation body either, so the old
    # "3 QA-plan schema repair" phrase has no live equivalent — the repair count below is
    # what still proves this is the schema ceiling, not the lap ceiling, that stopped it.
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
    """The join point is an entry into the plan lane, bounded by `MAX_CONTEXT_REWORKS`.

    `build_context` clears `plan_authored` because a rebuilt packet changed what the diff
    obligates, so the plan answering the old obligations must not be the one that runs.
    What decides whether the plan on disk still answers is the validate gate, re-run
    against the rebuilt packet: here it still passes, so the rejoin adopts the standing
    plan rather than paying a turn to reproduce it — a packet whose obligations really
    moved fails that gate and buys the authoring turn. The clock overrides none of it;
    what bounds the rejoin is the ceiling on the rebuilds themselves.
    """
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
    """Reached from `_guard_plan`, a spent clock no longer skips `repair_plan`.

    That demotion re-ran an unedited plan against unedited code and paid a `power="high"`
    assessment turn to be told the same thing — a live story spent exactly that lap. The
    repair budget is what bounds this now, and it is what the give-up names.
    """
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
    """Both guards land on `repair_plan`, whichever of them fired.

    Re-entering `plan` regenerates the whole file from the story, which resamples the
    scenarios the earlier passes already accepted and hands the next gate a fresh set of
    defects to find — the loop then has no reason to terminate. Here two schema failures and
    a post-run assessment all fire in one run, and only the very first turn is an authoring
    turn.
    """
    ostler(plan_invalid_passes=(1, 3), fail_runs=1)
    agent = _Agent(docs, repair_plans=1)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["plan-qa"] == 1, agent.counts()
    # Two schema repairs and one post-run repair.
    assert agent.counts()["repair-qa-plan"] == 3, agent.counts()
    assert agent.calls[0] == "plan-qa", agent.calls


def test_a_plan_loop_that_never_converges_escalates_with_the_refusal_that_spent_it(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The gate's diagnosis reaches the escalation, not just an aggregate attempt count.

    The give-up marker and its recorder are gone — every exhaustion now escalates to the
    operator gate instead of writing that marker, and the gate's `where` names the plan-repair
    count that was spent reaching it. This is driven the way it now happens in practice: a
    runner the post-run assessment never accepts, sending the plan back until the shared
    ceiling escalates it.
    """
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


# --------------------------------------------------------------------------- the stack


def test_the_stack_is_standing_before_the_plan_is_written(
    docs: Path,
    ostler: Callable[..., _Ostler],
    write: Callable[[Path, str], Path],
    monkeypatch: pytest.MonkeyPatch,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The reorder, stated as the thing the planner can rely on.

    A plan is written against locators, fixture data and credentials that either resolve or
    do not, and the only way to find out is to drive the surface. With the stack behind the
    plan lane the planner could not, so a curly apostrophe in an accessible name or a
    password constant that disagreed with the seed script cost a full workflow lap to
    discover. Standing the stack up first is what makes the dry run in `plan-qa.md`
    executable at all, so the ordering is the contract, not an optimisation.
    """
    ostler()
    agent = _Agent(docs)
    #: How many agent turns had been taken when the stack came up. Zero is the assertion.
    turns_before: list[int] = []

    def _up(*a: Any, **k: Any) -> dict[str, Any]:
        turns_before.append(len(agent.calls))
        return {"ready": "yes", "entry_url": "http://x"}

    monkeypatch.setattr(qa_stack, "ensure_stack", _up)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert turns_before == [0], (turns_before, agent.calls)
    assert agent.calls[0] == "plan-qa", agent.calls
    # And standing first does not cost a second visit: the approval arms go to the runner.
    assert agent.planned() == 1, agent.counts()


def test_a_setup_repair_mid_run_returns_to_the_runner_not_to_a_second_plan(
    docs: Path,
    ostler: Callable[..., _Ostler],
    write: Callable[[Path, str], Path],
    monkeypatch: pytest.MonkeyPatch,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`plan_authored`: `stack` is two entries, and only one of them authors.

    The setup loop rejoins at `stack`, and it is reachable from the *runner* — a blocked run
    naming a missing Playwright package — as well as from a stack that would not come up.
    Without the flag, repairing an environment fault would buy a `power="high"` replan of a
    plan the runner never objected to, once per fault. The flag is cleared only at
    `build_context`, which is where the diff's obligations can actually have changed.
    """
    okf = ostler(block_runs=1)
    monkeypatch.setattr(
        qa_stack, "ensure_stack", lambda *a, **k: {"ready": "yes", "entry_url": "http://x"}
    )
    agent = _Agent(docs, setup="ready")

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["setup-fix"] == 1, agent.counts()
    assert okf.runs == 2, "the repaired run was never retried"
    # The whole point: one authoring turn, not one per environment fault.
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
    # There is no manifest path to pass any more: the fixer repairs the book's runbook node,
    # which ostler finds for itself. Passing one was how a fixer could author a file the run
    # never read — the failure mode the node's single home removes.
    assert "stack_manifest" not in agent.args_for("setup-fix")[0]


def test_the_setup_fixer_is_briefed_with_why_the_stack_would_not_come_up(
    docs: Path,
    ostler: Callable[..., _Ostler],
    write: Callable[[Path, str], Path],
    monkeypatch: pytest.MonkeyPatch,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A stack failure is the running verdict, so the failing step's message reaches the fixer.

    The brief is composed from the QA verdict, which a stack that never came up leaves
    blank: the fixer was dispatched to repair something without being told what about it
    broke, and spent its turn rediscovering a line the stack supervisor already had.
    """
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
    """The YAML cycle with no terminal — the ledger's C3 finding — never gets a give-up either.

    `guard_setup` escalates a spent setup budget to the operator gate, and the gate's answer
    is applied as a QA fix that rejoins at `build_context` — which walks back to the stack,
    which is still down, which finds the budget still spent, which escalates again. A
    workflow does not give up, so this cycle has no counter left to end it on its own — it
    escalates every lap, forever, and only the driver's transition budget (pinned low here)
    stops the *test* rather than the story. Answering every gate keeps the cycle turning so
    the escalation count below is what proves the repeat, not a single park.
    """
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

    # Two repairs before the setup budget is spent, and the gate is what it hands off to —
    # every lap after that re-escalates without spending another repair.
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
    """An identical blocked bundle is an operator question, not another repair attempt.

    The run this comes from: the runner reported the Playwright package missing, the fixer
    installed it, proved the install worked, reported `ready` — and the next run named the
    same requirement, because the copy it repaired was not the interpreter the QA stage
    imports ostler into. Nothing in the loop could tell that apart from a repair that had not
    been tried yet, so it spent the whole setup budget on `power="high"` turns under a 2400s
    timeout to be told the same thing twice.

    The sameness is the signal. One fix is still attempted — the fixer has to run before
    there is any evidence about it — and the second is spent on a person instead. Answering
    each of those questions still leaves the identical bundle behind, so the cycle escalates
    again rather than ending — a workflow does not give up — and only the pinned-low
    transition budget stops this test rather than the story.
    """
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
    # And the block reached a person on every lap instead of another repair attempt.
    assert counts["resolve-operator"] > 1, counts
    assert len(seen) > 1, "the identical bundle must escalate more than once"


def test_a_packet_that_stays_unmappable_bounds_the_operator_gate(
    docs: Path,
    ostler: Callable[..., _Ostler],
    monkeypatch: pytest.MonkeyPatch,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The same hole, entered from the context loop rather than the stack loop.

    `build_context` guards on `context_rework`, and `repair_context` only spends one when it
    claims to have *repaired* something. A repairer that answers `blocked` every time
    therefore laps context → repair → gate → resolve → read → apply → context with no counter
    moving — three agent turns a lap, one of them the unbounded-timeout resolver. `qa_rework`
    is spent each lap in `apply_resolved`, but once it is spent past `MAX_QA_REWORKS` every
    later lap re-escalates instead of stopping — a workflow blocks rather than gives up, so
    only the driver's transition budget ends this run.
    """
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
    # The resolver is what `MAX_QA_BLOCKS` bounds — every gate lap past it goes straight to a
    # person, which is why the escalations below keep coming while this number stops.
    assert counts["resolve-operator"] == qa_flow.MAX_QA_BLOCKS, counts
    # `context_rework` never moves — the packet never gets repaired — so the context loop's
    # own repair attempts plateau, unlike the unbounded gate/apply pair above.
    assert counts["repair-qa-context"] < counts["apply-qa-fixes"], counts
    assert len(seen) > 1, "the identical block must escalate more than once"


def test_a_fixer_that_reports_blocked_reaches_the_operator(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`blocked` is the fixer saying nothing it does in this repo can help — so ask a person.

    The prompt has always asked for this status on a credential it cannot hold, a product
    decision in neither the story nor the plan, or work in another repo. The node discarded
    it and re-entered `build_context` regardless, so the answer to "I am blocked on X" was
    the same question again, at high power, until the budget ran out.

    Here the first `blocked` reaches the operator gate instead, so the block is put to
    somebody who can answer it. And the fix that is handed the answer and *still* says it is
    blocked goes back to the gate rather than round the QA cycle: the answer did not reach
    the block, so re-planning and re-running the suite against it buys nothing but the same
    refusal an hour later. One suite cycle, then gate laps only.

    No cap on the fix budget still ends the story now: an answer that never actually unblocks
    the fixer just earns the next escalation, forever — bounded here only by the harness's
    transition budget, not by `Qa`.
    """
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
    # The block is asked of the operator on the first fix, not swallowed. The suite is
    # planned and assessed exactly once — the cycle that found the failure — and never again,
    # because every lap after it is a fixer refusing an answer rather than a fix to verify.
    assert counts["qa-story"] == 1, counts
    assert counts["plan-qa"] + counts["repair-qa-plan"] == 1, counts
    # One gate lap per refusing fix lap, unboundedly: an answer that never actually unblocks
    # the fixer just earns the next escalation. The *resolver* is what stops — past
    # `MAX_QA_BLOCKS` the gate spends no more turns on it and asks a person directly.
    assert len(seen) == counts["apply-qa-fixes"], counts
    assert counts["resolve-operator"] == qa_flow.MAX_QA_BLOCKS, counts
    # Each gate is the composed escalation body, numbered, carrying the resolver's note.
    assert [f"**Escalation #{n} " in body for n, body in enumerate(seen, 1)] == [
        True
    ] * len(seen), seen
    # Only while the resolver still gets a turn: past `MAX_QA_BLOCKS` the gate composes the
    # body without one, so there is no resolver note in it to carry.
    assert all(ESCALATION_NOTE.strip() in body for body in seen[: qa_flow.MAX_QA_BLOCKS]), seen


def test_a_resolver_that_grounds_its_answer_settles_a_qa_block(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The `answered` arm, which lands on the same `read_operator` an escalation does.

    What the resolver may answer is narrow — see `coder/shared/resolution.py` — and narrower
    still here, because in QA it is the interested party: it may apply a written decision
    about the product, never one about its own evidence. What this proves is the mechanics:
    an answer is consumed exactly where a human's would be, and nobody is woken.
    """
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
    """The auto-operator's one honest answer: it waits on the same file a human mode does.

    In the YAML this fell out of `resolve_qa` flowing unconditionally into the await node,
    whose inotify wait was a no-op when the answer was already written. Here the resolver's
    `decision` is read, so the escalation is a branch — and the wait is the same `Await`.
    """
    ostler(context_invalid=1)
    seen: list[str] = []
    agent = _Agent(docs, repair="blocked", escalate=True)

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen)):
        result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    # The gate the human arrives at is the composed body: this story's escalation number,
    # what blocked, what the resolver ruled out — and the resolver's own note, carried
    # forward verbatim rather than overwritten. See `coder.shared.escalation`.
    (gate,) = seen
    assert "**Escalation #1 " in gate, gate
    assert all(line in gate for line in RESOLVER_TRIED), gate
    assert "only a person can decide this" in gate, gate
    assert ESCALATION_NOTE.strip() in gate, gate


# --------------------------------------------------------------------------- the two gates


def test_the_evidence_gate_invalidates_a_pass_it_cannot_verify(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A runner pass whose artifact contract fails is `invalid`, never `failed`.

    `invalid` routes back to planning rather than into the fix loop, because the finding is
    that the proof is malformed and no product fix addresses that. The auditor never runs:
    it only ever gets to see evidence this gate already confirmed.
    """
    ostler(vet_problems=["criterion AC-1 cites an artifact this run did not produce"])
    agent = _Agent(docs, escalate=True)
    seen: list[str] = []

    with pytest.raises(_Parked), patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)):
        drive_flow(Qa(story=STORY), env(), agent)

    assert agent.counts()["audit-qa"] == 0, agent.counts()
    assert agent.counts()["apply-qa-fixes"] == 0, agent.counts()
    # The draft, plus one plan turn per judgement rework the gate is entitled to spend.
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

    # Every subsequent pass is refuted the same way, so the fix loop runs out its budget
    # and escalates instead of stopping.
    assert agent.counts()["apply-qa-fixes"] == qa_flow.MAX_QA_REWORKS, agent.counts()
    # One triage per lap, plus the one on the lap the ceiling refuses to grant.
    assert agent.counts()["triage-qa"] == qa_flow.MAX_QA_REWORKS + 1, agent.counts()
    assert len(seen) == 1 and "code rework" in seen[0], seen


# --------------------------------------------------------------------------- the fix loop


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
    # The fixer is handed the assessment's own verdict, not the runner's raw notes.
    assert agent.args_for("apply-qa-fixes")[0]["qa_notes"] == "assessment pass 1"


_STUCK = {"copy-link": {"status": "failed", "assertions": 9, "failures": 1}}


def test_a_fix_that_leaves_the_run_failing_identically_is_not_repeated(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The `setup_problems` detector, one loop over — and the loop that cost the most.

    The run this comes from: a live scenario that failed under the QA runner's own driver on
    every attempt and never under a second, independent one. No fix written in the repo could
    reach it, so repairs two, three and four each bought a `power` agent turn plus a full
    re-run of the suite to be told the same thing — same scenario, same assertion, same depth
    — and the story was then filed `exhausted`, which reads as an intractable product defect
    rather than as a harness that cannot be repaired from here.

    Sameness is the signal. One fix is still attempted, because there is no evidence about a
    repair until it has run; the second buys the *other* hypothesis one lap (see
    `Qa._switched`) and only after that does the failure go to the operator instead of to the
    budget. What the detector still stops is the fix loop grinding out `MAX_QA_REWORKS`
    identical laps.
    """
    ostler(fail_runs=99, scenarios=(_STUCK,))
    agent = _Agent(docs, assessment_class="product", triage=("qa_fix", "code"), escalate=True)
    seen: list[str] = []

    with pytest.raises(_Parked), patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)):
        drive_flow(Qa(story=STORY), env(), agent)

    # The operator gate runs the same fixer prompt, so count the laps of the *fix loop* —
    # the ones carrying no operator answer — rather than every invocation of it.
    unaided = agent.fix_args()
    assert len(unaided) < qa_flow.MAX_QA_REWORKS, agent.counts()
    # The stall bought exactly one plan repair — the untried class — and that lap is the
    # whole difference between this ending and the one the docstring above describes.
    assert agent.counts()["repair-qa-plan"] == 1, agent.counts()
    # And the failure reached a person instead of the rest of the budget.
    assert len(seen) == 1, seen


def test_a_stalled_plan_repair_tries_the_other_hypothesis_before_the_operator(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The defect this whole switch exists for, in the direction it actually happened.

    A live story failed five assertions, every one of them a race *in the QA plan*. The
    assessment sent it to the plan author, the repair moved nothing, `_repeating` read the
    identical fingerprint as a stall, and the story was abandoned into `qa-skip-stories.txt`
    **having never spent a code lap**. But "the plan repair changed nothing" is evidence
    against the plan hypothesis, not against the story: it argues for looking at the product
    next, which is the one thing that run never did.
    """
    ostler(fail_runs=99, scenarios=(_STUCK,))
    agent = _Agent(docs, repair_plans=99, escalate=True)
    seen: list[str] = []

    with pytest.raises(_Parked), patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)):
        drive_flow(Qa(story=STORY), env(), agent)

    unaided = agent.fix_args()
    assert len(unaided) >= 1, agent.counts()
    # The fixer is told which hypothesis was spent, so it does not re-derive it.
    assert "the other side" in unaided[0]["qa_notes"], unaided[0]["qa_notes"]


def test_the_hypothesis_switch_happens_at_most_once_per_story(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`class_switched` is monotone, and that is the whole termination argument.

    Both classes stall here, one after the other, against a suite that never moves. The
    second stall — whichever class raises it — has to fall straight through to the operator
    gate, or the two loops trade laps until every budget is spent on the same answer.
    """
    ostler(fail_runs=99, scenarios=(_STUCK,))
    agent = _Agent(docs, repair_plans=99, escalate=True)
    seen: list[str] = []

    # The "after switching repair class" marker is logged only (see `Qa._stalled`), not
    # threaded into the escalation body — there is no live equivalent to assert on here.
    with pytest.raises(_Parked), patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)):
        drive_flow(Qa(story=STORY), env(), agent)

    # One shot at the operator, not one per stall.
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    assert len(seen) == 1, seen


def test_a_dev_target_switching_to_the_product_reports_instead_of_fixing(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The switch routes through `_fixable`, not `apply_fixes`.

    `apply_fixes` is the shorter wiring and would have had a `dev` run editing a repo it is
    only allowed to file findings against — the shortcut does not get to skip that rule.
    """
    ostler(fail_runs=99, scenarios=(_STUCK,))
    agent = _Agent(docs, repair_plans=99, escalate=True)

    result = drive_flow(Qa(story=STORY, target_env="dev"), env(), agent)

    assert result.status == "inconclusive", result
    assert agent.counts()["apply-qa-fixes"] == 0, agent.counts()
    assert agent.counts()["report-qa-dev"] == 1, agent.counts()
    # The switch is what ended the story: `report_dev` is terminal, so the stall never
    # reached the gate at all. Without it this run would have escalated instead.
    assert "resolve-operator" not in agent.counts(), agent.counts()


def test_a_fix_that_gets_the_run_further_still_earns_its_next_lap(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The other half: the detector must not stop a loop that is converging.

    Scenario identity alone would call every one of these laps "no progress" and cut the
    budget off after the first. The assertion depth is what says otherwise — each repair
    carries the journey further before it stops — and it is in the fingerprint for exactly
    this case.
    """
    ostler(
        fail_runs=99,
        scenarios=tuple(
            {"copy-link": {"status": "failed", "assertions": depth, "failures": 1}}
            # One deeper journey per lap the ceiling allows, and one for the lap it refuses.
            for depth in range(3, 3 + 2 * (qa_flow.MAX_QA_REWORKS + 1), 2)
        ),
    )
    agent = _Agent(docs, assessment_class="product", triage=("qa_fix", "code"), escalate=True)
    seen: list[str] = []

    with pytest.raises(_Parked), patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)):
        drive_flow(Qa(story=STORY), env(), agent)

    assert len(agent.fix_args()) == qa_flow.MAX_QA_REWORKS, agent.counts()
    assert len(seen) == 1, seen


#: Two failing scenarios in one run. The split is only observable with more than one — a
#: single-item worklist looks exactly like the whole-report turn it replaced.
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
    """The lever this split exists for: one brief per failing scenario, not one per report.

    The whole-report fixer was handed every failure at once and answered with one turn that
    had to hold all of them in its head — the single most expensive turn in the lane, and
    the one most likely to come back having half-fixed two things. Each item now gets its
    own brief, its own dry run and its own verdict, and the brief names the others only to
    say they are not this turn's job.
    """
    ostler(fail_runs=1, scenarios=(_TWO_FAILED, {}))
    agent = _Agent(docs, assessment_class="product", triage=("qa_fix", "code"))

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    briefs = agent.args_for("fix-qa-scenario")
    assert [b["scenario"] for b in briefs] == ["copy-link", "share-note"], agent.counts()
    # The whole-report turn is what runs when the run named no scenarios; it did not here.
    assert agent.counts()["apply-qa-fixes"] == 0, agent.counts()
    # Each brief carries its own item's assertions and disclaims what is still queued.
    assert briefs[0]["remaining_scenarios"] == ["share-note"], briefs[0]
    assert briefs[1]["remaining_scenarios"] == [], briefs[1]


def test_each_scenario_fix_is_proved_by_its_own_dry_run_before_the_next(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A per-item gate, so a fix that did not take is caught by the item that made it.

    The scored re-run is what the whole loop is paying for, and it costs the same whether
    one scenario or all of them come back red. Proving each item where it was written
    spends a re-lap of one brief instead.
    """
    ostler(fail_runs=1, scenarios=(_TWO_FAILED, {}))
    agent = _Agent(docs, assessment_class="product", triage=("qa_fix", "code"),
                   item_dry_run=("missing", "failed", "passed", "passed"))

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    briefs = agent.args_for("fix-qa-scenario")
    # `copy-link` refused twice — once for no log, once for a red one — and only then was
    # carried on as written; `share-note` was proved on its first attempt.
    assert [b["scenario"] for b in briefs] == [
        "copy-link", "copy-link", "share-note"
    ], agent.counts()


def test_a_scenario_that_spends_its_budget_is_carried_into_the_scored_run(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The per-item budget is not a give-up: an unproved item goes to the run, not the wall.

    Two differing refusals mean the turn is moving and out of item budget, and the honest
    next step is the scored run judging the item rather than a third brief guessing. The
    story's own budget, one loop out, is what still bounds the whole thing.
    """
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
    """Sameness at item granularity, and the same conclusion `_repeating` draws at run level.

    A dry run refusing an item twice in the identical words is evidence about the fixer, not
    about the item: nothing the second turn wrote moved the gate. That goes to a person —
    as an `Await`, which is resumable — rather than into the rest of the budget.
    """
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
    """A defect in the product is the dev lane's work, and the QA lane stops owning it.

    Fixing product code from inside QA is how a run ends up with the lane that judges the
    story also being the lane that wrote it. `refix` hands the story back with the findings
    already on disk in `qa.md`, and the triage budget is what stops it bouncing forever.
    """
    ostler(fail_runs=99, scenarios=(_STUCK,))
    agent = _Agent(docs, assessment_class="product", triage=("qa_fix", "product"))

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "refix", result
    assert result.triage_scope == 1, result
    # Nothing in the QA lane touched the product on the way out.
    assert "fix-qa-scenario" not in agent.counts(), agent.counts()
    assert agent.counts()["apply-qa-fixes"] == 0, agent.counts()


def test_a_product_class_triage_past_its_budget_stops_bouncing_to_dev(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The termination argument: `triage_scope` is spent, and past it the lane escalates.

    Without the ceiling a story whose triage keeps saying "product" would ride between the
    two lanes as long as the run lasted, each round paying a full dev pass and a full scored
    run to reach the identical verdict.
    """
    ostler(fail_runs=99, scenarios=(_STUCK,))
    agent = _Agent(docs, assessment_class="product", triage=("qa_fix", "product"),
                   escalate=True)
    seen: list[str] = []

    with pytest.raises(_Parked), patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)):
        drive_flow(Qa(story=STORY, triage_scope=qa_flow.MAX_TRIAGE_SCOPES), env(), agent)

    assert len(seen) == 1, seen


def test_the_fix_loop_grants_one_bonus_pass_only_for_an_evidence_failure(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`guard_qa_bonus`: past the lap ceiling, a missing-proof finding earns one more attempt.

    `code` and `environment` earn nothing, which is what the companion assertion below
    covers — the bonus is for the case where the code may well be right and the proof is
    what is missing, so one verification-only pass is cheap and often decisive.
    """
    ostler(fail_runs=99)
    agent = _Agent(docs, assessment_class="product", triage=("qa_fix", "evidence"), escalate=True)
    seen: list[str] = []

    with pytest.raises(_Parked), patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)):
        drive_flow(Qa(story=STORY), env(), agent)

    assert agent.counts()["apply-qa-fixes"] == qa_flow.MAX_QA_REWORKS + 1, agent.counts()
    assert len(seen) == 1, seen


def test_a_code_failure_earns_no_bonus_pass(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The same run, triaged `code`: the fix loop runs out its laps and stops."""
    ostler(fail_runs=99)
    agent = _Agent(docs, assessment_class="product", triage=("qa_fix", "code"), escalate=True)
    seen: list[str] = []

    with pytest.raises(_Parked), patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)):
        drive_flow(Qa(story=STORY), env(), agent)

    assert agent.counts()["apply-qa-fixes"] == qa_flow.MAX_QA_REWORKS, agent.counts()
    assert len(seen) == 1, seen


# ------------------------------------------------------------------ the give-up is a handoff


def test_a_spent_budget_asks_the_operator_before_abandoning_the_story(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A give-up is where an operator's one sentence is worth the most, and was where nobody asked.

    Eleven sites in this flow used to file a story `exhausted` outright, and only two of them
    ever reached the gate. Every one of those give-ups is a story a person could plausibly
    unblock — the port is squatted, the driver is fine, that assertion tests the wrong thing —
    and the flow's old answer was to stamp it and move on. Now every one reaches the gate, and
    a spent code-fix budget is no exception: the first answer is spent as a fix, and if that
    still does not clear the run, the story escalates again rather than ending — a workflow
    blocks, it does not give up.
    """
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
    # The answer is spent as a fix, which is the whole point of asking for it.
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
    """A spent code-fix budget escalates and keeps escalating — a workflow blocks, not gives up.

    There used to be a one-shot flag here: auto mode got exactly one ask, and declining it
    filed the story `exhausted` outright rather than parking the single-threaded story drain.
    That flag is gone — every give-up site now reaches the same `Await`, repeatedly if the
    operator's answer never actually clears the run, bounded only by the harness's transition
    budget rather than by `Qa` itself.
    """
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
    """The guided lap can exhaust a second time, and that is another ask, not a give-up.

    `_exhausted` gates, the gate's answer is applied, the flow rejoins the loop that was
    already out of budget, and exhausts into the same gate again — the livelock
    `apply_resolved` documents, and now the intended behavior rather than one this test used
    to guard against with a one-shot flag.
    """
    ostler(context_invalid=9)
    monkeypatch.setenv("WORKHORSE_MAX_TRANSITIONS", "60")
    agent = _Agent(docs, repair="repaired", escalate=True)
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen)):
        result = drive_flow(Qa(story=STORY), env(), agent)

    # The context stays invalid for nine checks, so `MAX_CONTEXT_REWORKS` runs out well
    # before it clears — the story is escalated, a guided lap is applied, the budget is
    # already spent so it escalates again immediately, and this repeats until the invalid
    # count finally runs out and the run passes. Every one of those is a real ask, not a
    # give-up.
    assert result.status == "passed", result
    # Every lap is a real ask; only the first `MAX_QA_BLOCKS` of them buy a resolver turn.
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

    # `human` mode parks the run on the gate directly, with no resolver investigation first —
    # and the context eventually clears the same way it does in `auto` mode, so the run ends
    # up passed rather than filed exhausted.
    assert result.status == "passed", result
    assert agent.counts()["resolve-operator"] == 0, agent.counts()
    assert len(seen) >= 1, seen


def test_each_exhaustion_names_the_budget_it_spent(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The escalation body names the budget that ran out, and the budgets must not blur.

    There is no terminal `exhausted` status anymore — every arm below now parks on the
    operator gate instead. What survives from the old give-up marker is the `where` clause
    `_escalation` composes: a story that burned its QA-plan repairs and so never reached a
    code fix must not read as `0 code rework`, which looks like a loop that never tried.
    Each budget keeps its own counter in that clause.
    """
    ostler(context_invalid=9)
    seen: list[str] = []
    with (
        pytest.raises(_Parked),
        patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)),
    ):
        drive_flow(Qa(story=STORY), env(), _Agent(docs, repair="repaired", escalate=True))
    assert "3 context repair" in seen[0], seen

    # The mechanical plan gate spends its own budget (`plan_validation_rework`), not the
    # coverage one threaded into the escalation body — `_escalation`'s `where` only reports
    # `qa_rework`/`plan_rework`/`context_rework`/`setup_rework`, so a schema give-up and a
    # coverage give-up both read as `0 plan repair` there. What still tells them apart is
    # that this one never got as far as a run.
    okf = ostler(plan_invalid=9)
    seen = []
    with (
        pytest.raises(_Parked),
        patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)),
    ):
        drive_flow(Qa(story=STORY), env(), _Agent(docs, escalate=True))
    assert "0 plan repair" in seen[0], seen
    assert okf.runs == 0

    # The post-run budget, reached only through a plan that validated and the runner
    # executed — the first run plus one per judgement repair, each an assessment that did not
    # reach the objective.
    okf = ostler(fail_runs=99)
    seen = []
    with (
        pytest.raises(_Parked),
        patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)),
    ):
        drive_flow(Qa(story=STORY), env(), _Agent(docs, escalate=True))
    assert f"{qa_flow.MAX_PLAN_REWORKS} plan repair" in seen[0], seen
    assert okf.runs == qa_flow.MAX_PLAN_REWORKS + 1

    ostler(fail_runs=99)
    agent = _Agent(docs, assessment_class="product", triage=("qa_fix", "code"), escalate=True)
    seen = []
    with (
        pytest.raises(_Parked),
        patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)),
    ):
        drive_flow(Qa(story=STORY), env(), agent)
    assert f"{qa_flow.MAX_QA_REWORKS} code rework" in seen[0], seen

    # A dev target reworks nothing and has no code to rework, so there is no operator-
    # answerable question to gate on — it is still the one legitimate terminal exit in this
    # flow, reported via `inconclusive` rather than an escalation.
    ostler(fail_runs=99)
    agent = _Agent(docs, assessment_class="product", escalate=True)
    result = drive_flow(Qa(story=STORY, target_env="dev"), env(), agent)
    assert result.status == "inconclusive", result


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

    # `triage_scope` isn't threaded into the escalation body's `where` clause, so it isn't
    # observable once the story parks rather than ending — what stays checkable is that the
    # triager's `rescope` verdict was ignored: the story goes on to spend a full code-rework
    # budget instead of ending early with `status="rescope"`.
    with (
        pytest.raises(_Parked),
        patch.object(pyflow_driver, "wait_for_answer", _parked_at(seen)),
    ):
        drive_flow(Qa(story=STORY, triage_scope=2), env(), agent)

    assert agent.counts()["triage-qa"] == qa_flow.MAX_QA_REWORKS + 1, agent.counts()
    assert agent.counts()["apply-qa-fixes"] == qa_flow.MAX_QA_REWORKS, agent.counts()


# ------------------------------------------------------------------- routing a gate's findings


def _a_product_test_finding(handle: str = "A1") -> dict[str, str]:
    """The finding that livelocked a live story: a gap only a code edit can close.

    Taken from the run verbatim. An acceptance criterion claimed no network call happens
    during an export, the only proof was a static read of the exporting function, and the
    repair is a fetch-spy assertion in a committed browser test — a file the QA plan may cite
    but not write.
    """
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
    """The `coder-qafix2` regression: three gates, one missing assertion, nobody who could add it.

    A live story spent 82 minutes here. The audit refuted an `evidence-defect` whose repair
    was an assertion in a committed test file; `refutation_class` alone sent every refutation
    to the plan author, who cannot write one. So the author re-planned, disclosed the same
    gap, and the audit refuted it again — four laps, and a give-up filed as "QA-plan repair",
    which reads to a triaging human as a plan nobody could write rather than a missing test.

    The finding's scope is what breaks that: the repair goes to the loop that edits code.
    """
    ostler()
    agent = _Agent(
        docs,
        audit=("refuted", "evidence-defect"),
        audit_findings=[_a_product_test_finding()],
        escalate=True,
    )

    seen: list[str] = []

    # The auditor never relents in this fake, so the flow still escalates — but on the
    # budget that names the work, and having actually attempted it.
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
    """The same gap found one gate earlier, by the post-run assessment.

    `extend_plan` reads as a plan instruction and was routed as one unconditionally. It is
    routinely the opposite: the run exposed an untested claim whose proof belongs in a
    committed test, and appending scenarios to `qa_plan.py` cannot supply it. The runner
    stays red here because a green run no longer reaches the assessment at all.
    """
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
    """The fall-through the change must not remove.

    `findings` defaults to empty, so a checkpoint written before the field existed — and an
    auditor that answers in prose alone — resumes on exactly the behaviour it had. Failing a
    finding-less refutation the way a structurally invalid plan is failed would add a new way
    to kill a run over an audit's output shape, on the gate that reads a pass which already
    cleared every other gate.
    """
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
    """The other half of the `coder-qafix2` regression: the gate with nothing downstream.

    Story `04-publish-metadata` died here. The runner passed every lap; the audit refuted
    three times with three *different* genuine plan gaps, each closed by a repair and each
    replaced by a fresh one from a fresh sample — because the auditor samples the riskiest
    evidence rather than enumerating it, so the bar moves under every repair. Four laps
    later the plan budget was gone and the story filed `give_up` on a plan whose runner had
    never failed.

    Every other plan-lane gate has a blocking ceiling for exactly this, justified by "a gate
    still stands downstream either way". Nothing stands downstream of the audit, so it needs
    its own: past `MAX_BLOCKING_AUDITS` plan-scoped refutations its findings are filed
    as backlog work and the story lands on the verdict its evidence supports.
    """
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
    # The ceiling is on *blocking*, not on running: the audit still ran the lap it stopped
    # blocking on, and its findings still reached the filer.
    assert agent.counts()["audit-qa"] == qa_flow.MAX_BLOCKING_AUDITS + 1, agent.counts()
    assert agent.counts()["repair-qa-plan"] == qa_flow.MAX_BLOCKING_AUDITS, agent.counts()


def test_a_dev_target_reports_a_product_test_finding_rather_than_fixing_it(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The route goes through `_fixable`, so `dev`'s "we do not own this code" still holds.

    Calling `apply_fixes` directly would have been the shorter wiring and would have had a
    `dev` run editing a repo it is only allowed to file findings against.
    """
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


# --------------------------------------------------------------------------- target_env=dev


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


# --------------------------------------------------------------------------- feedback


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
    assert okf.runs == 2, okf.runs
    # Feedback is not a failure of the fix loop, so no rework is spent on it.
    assert result.qa_rework == 0
    assert result.docs_recheck_required is True
    assert "TODO" in agent.args_for("apply-qa-fixes")[0]["operator_feedback"]
    # The message is replied to, which is what stops the second pass looping.
    messages = inbox.all_messages(run_env.writer.run_dir / INBOX_FILE)
    assert len(messages) == 1, messages
    assert messages[0].reply, messages


# --------------------------------------------------------------------------- regression


def test_a_failing_journey_suite_is_fixed_and_the_story_is_re_qad(
    docs: Path,
    web: Path,
    ostler: Callable[..., _Ostler],
    monkeypatch: pytest.MonkeyPatch,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A regression fix is a code change, so the primary QA evidence has to be recaptured.

    That round trip is the whole subtlety of the two flags: a green suite *after* a fix
    sends the story back through primary QA once, and `regression_reqa_pending` is what
    stops it repeating forever.
    """
    okf = ostler()
    suite = _Suite(fail_runs=1)
    monkeypatch.setattr(regression_nodes, "_run", suite)
    agent = _Agent(docs)
    run_env = env()

    result = drive_flow(Qa(story=STORY), run_env, agent)

    assert result.status == "passed", result
    assert result.docs_recheck_required is True
    assert agent.counts()["fix-regression"] == 1, agent.counts()
    # Three suite runs: the failure, the green re-run after the fix, and the re-QA's.
    assert len(suite.calls) == 3, suite.calls
    assert suite.calls[0] == "run-journeys", suite.calls
    # Primary QA really was re-run, which is the point of the round trip.
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


# --------------------------------------------------------------------------- resume


def test_a_run_killed_mid_audit_resumes_on_the_audit(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The whole eighteen-field loop carrier round-trips through one checkpoint parameter.

    This is the shape the port needed and the driver already had: a pydantic model is a
    legal state parameter, so the resumed run re-enters `audit` with every counter, note and
    flag the killed run had accumulated — and does not re-run the QA suite to get them back.
    """
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
    """QA against someone else's checkout: no dev lane ran, so there is no `plan-context.json`.

    The file is the *dev* lane's output. A QA run pointed at a branch this workflow did not
    implement — a review of an outside contribution, a standalone verification pass — has
    never had one, and the plan-context brief added to `plan-qa.md` must therefore be
    strictly additive. `resolve_impl_context` degrades to empty lists by design and the
    prompt's blocks are `{% if %}`-guarded, but every other test in this file writes the file
    from the `docs` fixture, so nothing pinned the degraded path until here.
    """
    (docs / SPEC_REL / "plan-context.json").unlink()
    ostler()
    monkeypatch.setattr(
        qa_stack, "ensure_stack", lambda *a, **k: {"ready": "yes", "entry_url": "http://x"}
    )
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.planned() == 1, agent.counts()



# --------------------------------------------------------------- a turn that cannot proceed


@pytest.mark.parametrize("stem", ["plan-qa", "qa-story", "audit-qa"])
def test_a_turn_that_says_it_cannot_proceed_reaches_the_operator(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    stem: str,
) -> None:
    """Every binding turn on the clean path can refuse, and the refusal is a block.

    Not a repair lap: nothing about the plan, the run or the evidence is wrong, so a lap
    that re-ran the same turn would get the same answer for the same reason. The refusal's
    own words are what the operator is shown — that is the only thing in the run that says
    *why* it stopped.

    `qa-story` needs a red run to be on the path at all: a green runner skips the
    assessment turn, so its refusal is only reachable downstream of a failure.
    """
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
    # The fix loop never opened: a triage that refused named no target to fix.
    assert agent.counts()["apply-qa-fixes"] == 0, agent.counts()
    assert len(seen) == 1 and "needs a credential this run does not hold" in seen[0], seen


# ------------------------------------------------------- a standing plan, and first verdicts


def test_a_standing_valid_plan_is_adopted_without_an_authoring_turn(
    docs: Path,
    ostler: Callable[..., _Ostler],
    write: Callable[[Path, str], Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A `qa_plan.py` that lints and validates goes to the runner with no plan turn at all.

    `build_context` clears `plan_authored` on every entry, so before this a re-QA of a
    story whose accepted plan sat on disk paid a full authoring turn to write it again.
    The gates run *before* the turn now, and they are the whole question: lint vouches
    for the AST, validate fail-closes on any uncovered required obligation — so a plan
    that passes both is adopted outright, and the validation tail still re-checks what
    is on disk before the runner spends anything on it.
    """
    ostler()
    write(docs / SPEC_REL / "qa_plan.py", QA_PLAN)
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    # No plan turn: the standing plan is the plan. The runner still ran it.
    assert agent.planned() == 0, agent.counts()
    assert agent.args_for("plan-qa") == [], agent.counts()


def test_stop_at_first_verdict_finishes_a_green_run_with_no_post_run_agent_turns(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`stop_at_first_verdict`: a pass is still gated deterministically, and only deterministically.

    The evidence gate and the sentinel check both run — a pass this mode reports is one
    whose artifacts exist on disk — but the audit exists to refute a pass into a repair,
    and this mode reports rather than repairs.
    """
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
    """`stop_at_first_verdict`: the first red is the report, and no agent reads it first.

    `report_dev` is the precedent — a mode that does not own the outcome reports what it
    saw, and reporting is the terminal action. The flow ends `inconclusive` (nothing was
    repaired, refuted or triaged) with the runner's own verdict in `qa` and the evidence
    map the runner wrote as the report's substance. The classification turn stays out:
    every disposition it could return either enters a repair this mode forbids or ends
    the flow exactly as this branch already does.
    """
    okf = ostler(fail_runs=99)
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY, stop_at_first_verdict=True), env(), agent)

    assert result.status == "inconclusive", result
    assert result.qa.status == "failed", result
    # One plan, one run — and not a single classification, repair or triage turn.
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
    """`stop_at_first_verdict` reports verdicts about the product, never about the harness.

    A blocked run says nothing about the product, so ending on it would report the
    stack's failure as the story's. The setup loop keeps its job, and the retried run's
    verdict is the one reported.
    """
    okf = ostler(block_runs=1)
    write(docs / "qa-stack.yml", "app_cwd: .\nhealth:\n  - run: true\n")
    monkeypatch.setattr(
        qa_stack, "ensure_stack", lambda *a, **k: {"ready": "yes", "entry_url": "http://x"}
    )
    agent = _Agent(docs, setup="ready")

    result = drive_flow(Qa(story=STORY, stop_at_first_verdict=True), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["setup-fix"] == 1, agent.counts()
    # A `blocked` run — unlike a plain `failed` one — still buys the classification
    # turn: telling a dead stack apart from a red about the product is its job here.
    assert agent.counts()["qa-story"] == 1, agent.counts()
    assert okf.runs == 2, "the repaired run was never retried"
