"""End-to-end tests for the `qa` flow — the gates, the four loops, and the operator.

Ninety-one YAML nodes became twenty-five states holding five bounded loops that all rejoin
at `build_context`: the context repair, the plan rework, the QA fix, the setup repair and
the regression fix. What is worth testing is which arm each verdict takes, what makes each
loop terminate, and — above all — that the evidence gate cannot be talked past.

**Five seams, all of them a process boundary.** `ostler qa context|validate|run`, `ostler
artifact vet`, `workhorse.stack.ensure_stack` (docker) and the regression suite's
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
import logging
import subprocess
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml
from workhorse import stack as workhorse_stack
from workhorse.artifacts import ArtifactWriter
from workhorse.pyflow import WorkflowFailed
from workhorse.pyflow import driver as pyflow_driver
from workhorse.pyflow.driver import read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import parse_checkpoint
from workhorse.runner.failure import BackendInvocationError

from workhorse_workflows.coder.shared import ostler_qa
from workhorse_workflows.coder.qa.flow import Qa
from workhorse_workflows.coder.qa.nodes import regression as regression_nodes
from workhorse_workflows.coder.qa.nodes.qa import record_qa_giveup
from workhorse_workflows.coder.shared.dev import resolve_impl_context

STORY = "STORY-1"
EPIC = "EPIC-1"
SPEC_REL = f"docs/specs/{STORY}"
STORY_REL = f"docs/epics/{EPIC}/stories/{STORY}"
CONTEXT_REL = f"{STORY_REL}/context.md"

#: What an escalating resolver leaves in `context.md` before handing the block to a person —
#: the shape `prompts/resolve-operator.md` mandates for the escalated arm.
ESCALATION_NOTE = (
    "STATUS: AWAITING_OPERATOR\n\n"
    "Re-ran the stack twice; the emulator comes up but the suite still cannot reach it.\n"
    "Please confirm which host the suite should dial.\n"
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

## Context

Users need a thing.

## Acceptance Criteria

- the thing exists

## Implementation Status

- **Status**: Done
"""

#: The dev phase's plan, decoded by `resolve_impl_context` for the repo grant and the QA
#: source roots. A `go` service has no UI layer, so `detect_regression_platform` says `none`
#: and the regression loop is out of the way of every test that is not about it.
API_SERVICE: dict[str, Any] = {
    "repo": "api",
    "path": ".",
    "type": "go",
    "plan_file": "plan-api.md",
    "skills": [],
}

#: The same plan with a UI layer, which is what puts the committed journey suites at risk.
WEB_SERVICE: dict[str, Any] = {
    "repo": "web",
    "path": ".",
    "type": "react-router",
    "plan_file": "plan-web.md",
    "skills": [],
}

QA_PLAN = '''from ostler_qa import Qa, plan, scenario, target

plan(run_id="qa-story", story="the-story")
api = target("api")


@scenario(target=api, mechanism="live", covers=["ac:1"])
def the_thing_exists(qa: Qa) -> None:
    """The thing exists."""
    qa.check("it exists", True)
'''


# --------------------------------------------------------------------------- fixtures


@pytest.fixture
def docs(
    repo: Path,
    write: Callable[[Path, str], Path],
    write_json: Callable[[Path, Any], Path],
) -> Path:
    """The docs repo: one epic, one built story, and the plan the dev phase left behind."""
    write(repo / "docs" / "epics" / EPIC / "epic.md", EPIC_MD)
    write(repo / STORY_REL / "story.md", STORY_MD)
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
    """A real `web` repo carrying a `Makefile`, and a plan that names it.

    `_run_web_one` skips a service with no `Makefile` outright, so the regression tests need
    a repo that has one — the suite command itself is the seam, not its absence.
    """
    write_json(
        docs / SPEC_REL / "plan-context.json", {"story": STORY, "services": [WEB_SERVICE]}
    )
    root = tmp_path / "ws"
    path = root / "web"
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    write(path / "Makefile", "e2e-journeys:\n\t@true\n")
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
    a real runner writes — the evidence, the run log, the run manifest — because the evidence
    gate below it is real and reads all of them.
    """

    def __init__(
        self,
        *,
        fail_runs: int = 0,
        context_invalid: int = 0,
        plan_invalid: int = 0,
        plan_invalid_passes: tuple[int, ...] = (),
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
        self.vet_problems = vet_problems or []
        self.runs = 0
        self.contexts = 0
        self.context_validations = 0
        self.plan_validations = 0
        self.vets = 0
        self.context_args: list[dict[str, Any]] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> _Ostler:
        for name in (
            "qa_context",
            "qa_context_validate",
            "qa_validate",
            "qa_run",
            "artifact_vet",
        ):
            monkeypatch.setattr(ostler_qa, name, getattr(self, name))
        return self

    # -- the packet -------------------------------------------------------

    def qa_context(
        self,
        spec_dir: str,
        *,
        base: str,
        head: str,
        features_root: str,
        story_file: str,
        source_roots: list[str],
        docs_root: Path | None = None,
        exclude_paths: list[str] | None = None,
    ) -> tuple[int, dict[str, Any], str]:
        self.contexts += 1
        self.context_args.append(
            {
                "base": base,
                "head": head,
                "story_file": story_file,
                "source_roots": source_roots,
                "exclude_paths": list(exclude_paths or []),
            }
        )
        spec = Path(spec_dir)
        spec.mkdir(parents=True, exist_ok=True)
        (spec / "qa-okf-context.json").write_text(
            json.dumps({"status": "passed", "obligations": [], "verificationIndex": []}),
            encoding="utf-8",
        )
        return 0, {"status": "passed"}, ""

    def qa_context_validate(
        self, spec_dir: str, *, docs_root: Path | None = None
    ) -> tuple[int, dict[str, Any], str]:
        self.context_validations += 1
        if self.context_validations <= self.context_invalid:
            return 1, {"status": "invalid", "notes": "two changed files map to no feature node"}, ""
        return 0, {"status": "passed"}, ""

    # -- the plan ---------------------------------------------------------

    def qa_validate(
        self, plan: str, spec_dir: str, *, docs_root: Path | None = None
    ) -> tuple[int, dict[str, Any], str]:
        self.plan_validations += 1
        # The plan turn is supposed to have written this; validating a file that is not
        # there would make every plan-gate test pass for the wrong reason.
        assert Path(plan).is_file(), f"the plan turn wrote no {plan}"
        if (
            self.plan_validations <= self.plan_invalid
            or self.plan_validations in self.plan_invalid_passes
        ):
            return 1, {"status": "invalid", "notes": "step 3 names no assertion"}, ""
        return 0, {"status": "passed"}, ""

    # -- the run ----------------------------------------------------------

    def qa_run(
        self, plan: str, spec_dir: str, *, docs_root: Path | None = None
    ) -> tuple[int, dict[str, Any], str]:
        self.runs += 1
        if self.runs <= self.block_runs:
            return 1, {
                "status": "blocked",
                "problems": ["target 'web' requires the Playwright Python package"],
                "notes": "QA run blocked",
            }, ""
        if self.blocked_problems is not None:
            # A blocked run writes nothing: it never executed a scenario.
            return 1, {
                "status": "blocked",
                "problems": list(self.blocked_problems),
                "notes": "QA run blocked",
            }, ""
        status = "failed" if self.runs <= self.fail_runs else "passed"
        self._write_run(Path(spec_dir), status)
        payload: dict[str, Any] = {
            "status": status,
            "notes": f"run {self.runs} reported {status}",
        }
        if self.scenarios:
            payload["scenarios"] = self.scenarios[min(self.runs, len(self.scenarios)) - 1]
        return (0 if status == "passed" else 1), payload, ""

    def _write_run(self, spec: Path, status: str) -> None:
        """The artifacts `ostler qa run` leaves behind, which the evidence gate reads.

        An un-modeled surface: no OKF criteria and no obligations, proving itself on the run
        log's command assertions. That is the cheapest *legitimate* passing shape, so a gate
        that rejects it is broken and a gate that accepts a fabricated one is too.
        """
        run_id = f"run-{self.runs}"
        qa = spec / "qa"
        qa.mkdir(parents=True, exist_ok=True)
        results = ["PASS", "PASS"] if status == "passed" else ["PASS", "FAIL"]
        (qa / "qa-run.ndjson").write_text(
            "".join(json.dumps({"kind": "assert", "result": r}) + "\n" for r in results),
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

    # -- the artifact contract --------------------------------------------

    def artifact_vet(
        self, kind: str, spec_dir: str, *, root: Path
    ) -> tuple[int, dict[str, Any], str]:
        self.vets += 1
        return (1 if self.vet_problems else 0), {"problems": list(self.vet_problems)}, ""


@pytest.fixture
def ostler(monkeypatch: pytest.MonkeyPatch) -> Callable[..., _Ostler]:
    """Install a scripted ostler; the default one passes every gate it is asked about."""

    def _install(**kwargs: Any) -> _Ostler:
        return _Ostler(**kwargs).install(monkeypatch)

    return _install


class _Suite:
    """`make e2e-journeys`, scripted. `fail_runs` leading invocations exit non-zero."""

    def __init__(self, *, fail_runs: int = 0) -> None:
        self.fail_runs = fail_runs
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str], cwd: Path, timeout: int) -> tuple[int | None, str]:
        self.calls.append(cmd)
        if len(self.calls) <= self.fail_runs:
            return 1, "FAIL journeys/login.spec.ts › logs a user in\n"
        return 0, "12 passed\n"


# --------------------------------------------------------------------------- the agent


def _a_plan_finding(nth: int) -> dict[str, str]:
    """The default in-scope refusal, one per review pass and stably identified.

    `kind` is spelled out rather than left to the schema default, because the default is
    fail-closed and a fake that relied on it would keep passing if the field were ever
    renamed out from under it.
    """
    return {
        "id": f"R{nth}",
        "scope": "plan",
        "kind": "coverage",
        "target": "scenario `create-document`",
        "issue": f"review pass {nth}",
        "repair": "assert the row is present after the dialog closes",
    }


def _a_plan_nit(nth: int, kind: str = "cosmetic") -> dict[str, str]:
    """A finding inside the plan's authority that nothing downstream would fail over."""
    return {
        "id": f"N{nth}",
        "scope": "plan",
        "kind": kind,
        "target": "scenario `create-document`",
        "issue": "the objective says ten test cases and the file has nine",
        "repair": "say nine",
    }


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
        review: str = "approved",
        revise_plans: int = 0,
        approve_reviews: int = 0,
        plan_findings: list[dict[str, str]] | None = None,
        disposition: str = "confirmed",
        repair_plans: int = 0,
        failure_class: str = "none",
        objective: str = "yes",
        assessment_class: str = "none",
        assessment_findings: list[dict[str, str]] | None = None,
        audit: tuple[str, str] = ("stands", "none"),
        audit_findings: list[dict[str, str]] | None = None,
        triage: tuple[str, str] = ("qa_fix", "code"),
        setup: str = "fixed",
        qa_fix: str = "fixed",
        escalate: bool = False,
        scope: str = "story",
        explode: set[str] | None = None,
        cut: set[str] | None = None,
    ) -> None:
        self.docs = docs
        self.repair = repair
        self.review = review
        self.revise_plans = revise_plans
        self.approve_reviews = approve_reviews
        # `None` is not `[]`: the default is one well-formed finding per refusal, and an
        # explicit empty list is a test asking for the shape the flow now rejects.
        self.plan_findings = plan_findings
        self.disposition = disposition
        # `revise_plans`' convention one gate over: a count of *leading* assessments that
        # send the failure to the plan author, after which the assessment behaves normally.
        self.repair_plans = repair_plans
        self.failure_class = failure_class
        self.objective = objective
        self.assessment_class = assessment_class
        # Unlike `plan_findings`, these default to *nothing*: the flow's prose fall-through
        # for a gate that named no findings is the pre-existing behaviour and most of the
        # suite still exercises it, so a fake that invented findings would hide it.
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
        handler = getattr(self, f"_{stem.replace('-', '_')}")
        nth = self.planned() if stem in self.PLAN_STEMS else self.counts()[stem]
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

    # -- one handler per prompt -------------------------------------------

    def _repair_qa_context(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """The only two-key turn in the coder: the repair *and* the running QA verdict."""
        return {
            "qa_context_repair": {"status": self.repair, "notes": f"repair pass {nth}"},
            "qa_result": {
                "status": "blocked" if self.repair != "repaired" else "",
                "notes": f"the diff touches code no feature node owns (pass {nth})",
            },
        }

    def _plan_qa(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        (Path(data["spec_dir"]) / "qa_plan.py").write_text(QA_PLAN, encoding="utf-8")
        return {"status": "planned", "notes": f"plan pass {nth}"}

    def _repair_qa_plan(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """The repair turn leaves the same plan on disk and answers in the same shape."""
        return self._plan_qa(data, nth)

    def _review_qa_plan(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        # `revise_plans` follows `_Ostler`'s convention: a count of *leading* refusals, for
        # the tests that need the reviewer to relent and let a plan through.
        # `approve_reviews` shifts that window later: the leading passes it names are waved
        # through first. It exists because a plan lap's review is the second one, and only a
        # refusal routes findings — an explicit approval goes straight to the stack.
        nth = max(nth - self.approve_reviews, 0)
        disposition = "revise" if 0 < nth <= self.revise_plans else self.review
        # A refusal carries a well-formed finding by default, because the real reviewer's
        # contract now says it must: the flow raises on a `revise` that names nothing. A fake
        # still free to emit the old prose-only shape would let a test pass over a path
        # production rejects.
        default = [_a_plan_finding(nth)] if self.plan_findings is None else self.plan_findings
        findings = default if disposition == "revise" else []
        return {
            "disposition": disposition,
            "findings": findings,
            "notes": f"review pass {nth}",
        }

    def _qa_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        # A runner failure the assessment confirms is a product defect unless the test says
        # otherwise; a runner pass has nothing to classify.
        failed = data["runner_status"] == "failed"
        plan_lap = failed and nth <= self.repair_plans
        return {
            "disposition": "repair_plan" if plan_lap else self.disposition,
            "failure_class": ("plan" if plan_lap else self.assessment_class)
            if failed
            else self.failure_class,
            "objective_reached": "no" if failed else self.objective,
            "findings": self.assessment_findings,
            "notes": f"assessment pass {nth}",
        }

    def _audit_qa(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        verdict, refutation = self.audit
        return {
            "verdict": verdict,
            "refutation_class": refutation,
            "findings": self.audit_findings,
            "notes": f"audit pass {nth}",
        }

    def _triage_qa(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        action, failure_class = self.triage
        return {"triage_action": action, "qa_failure_class": failure_class}

    def _apply_qa_fixes(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return {"status": self.qa_fix, "notes": f"fix pass {nth}"}

    def _fix_regression(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return {"notes": f"regression fix pass {nth}"}

    def _setup_fix(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return {"status": self.setup, "notes": f"setup pass {nth}"}

    def _report_qa_dev(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return {"status": "reported", "notes": "filed with the upstream tracker"}

    def _report_qa_dev_pass(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return {"status": "reported", "notes": "told the tracker it passed"}

    def _resolve_operator(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if self.escalate:
            self._escalate()
            return {"decision": "escalated", "summary": "only a person can decide this"}
        self._answer()
        return {"decision": "answered", "summary": "use the staging bucket"}

    def _answer(self) -> None:
        """Write the answer where `read_operator_context` reads it back out of."""
        (self.docs / CONTEXT_REL).write_text(
            f"STATUS: ANSWERED\nSCOPE: {self.scope}\n\nUse the staging bucket.\n",
            encoding="utf-8",
        )

    def _escalate(self) -> None:
        """An escalating resolver writes its note into the same file, it does not write nothing.

        `prompts/resolve-operator.md` mandates `STATUS: AWAITING_OPERATOR` plus what it tried
        and what the human must supply — the thing the escalated `Await` must not overwrite.
        """
        (self.docs / CONTEXT_REL).write_text(ESCALATION_NOTE, encoding="utf-8")


def _answers(seen: list[str], *, scope: str = "story") -> Callable[..., None]:
    """A stand-in for the human an `Await` is waiting on, patched over `wait_for_answer`."""

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text(encoding="utf-8"))
        path.write_text(
            f"STATUS: ANSWERED\nSCOPE: {scope}\n\nUse the staging bucket.\n", encoding="utf-8"
        )

    return answered


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
    """Context, plan, review, run, assessment, evidence, audit, sentinels — all first try."""
    okf = ostler()
    agent = _Agent(docs)
    run_env = env()

    result = drive_flow(Qa(story=STORY), run_env, agent)

    assert result.status == "passed", result
    assert result.qa_rework == 0
    assert result.docs_recheck_required is False
    assert agent.counts() == {
        "plan-qa": 1,
        "review-qa-plan": 1,
        "qa-story": 1,
        "audit-qa": 1,
    }, agent.counts()
    # One packet build, one run, and the evidence contract really was vetted.
    assert (okf.contexts, okf.runs, okf.vets) == (1, 1, 1)
    # The runner's artifacts are on disk and the gate accepted them on their own terms.
    assert (docs / SPEC_REL / "qa-evidence.json").is_file()
    assert (docs / SPEC_REL / "qa" / "qa-run.ndjson").is_file()


def test_a_blank_story_ends_exhausted_without_running_anything(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`decide_qa_story`'s empty arm: `exhausted`, not a failure, and no turns spent.

    The parent graph's `decide_qa_outcome` has an arm for `exhausted`; `docs` raises on the
    same condition, and the divergence is deliberate. The seeded rescope budget is handed
    straight back, because this flow never got far enough to spend it.
    """
    okf = ostler()
    agent = _Agent(docs)

    result = drive_flow(Qa(story="", triage_scope_count=1), env(), agent)

    assert result.status == "exhausted", result
    assert result.triage_scope == 1
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
        for key in ("plan_validation_notes", "plan_review_notes", "run_assessment_notes",
                    "audit_notes")
    ), plan_args


def test_the_context_repair_loop_is_bounded_at_three(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A repairer that claims success on a packet that stays unmappable costs three passes."""
    okf = ostler(context_invalid=9)
    # `escalate=True` throughout the budget tests: every spent budget now gets one operator
    # shot before the give-up, and a resolver that declines to answer is what leaves the
    # boundary these tests are about — the budget's own — the only thing that moved.
    agent = _Agent(docs, repair="repaired", escalate=True)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "exhausted", result
    assert agent.counts() == {"repair-qa-context": 3, "resolve-operator": 1}, agent.counts()
    assert okf.runs == 0, "the plan was never reached, so nothing should have run"


def test_an_unrepairable_packet_goes_to_the_auto_operator(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`blocked` skips the rework and takes the gate; the answer is applied as a QA fix."""
    ostler(context_invalid=1)
    agent = _Agent(docs, repair="blocked")

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
    agent = _Agent(docs, repair="blocked", scope="epic")

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
    """Three schema repairs buy four plan turns and never reach the stack."""
    okf = ostler(plan_invalid=9)
    agent = _Agent(docs, escalate=True)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "exhausted", result
    # One draft and three repairs: a plan that does not parse is repaired, not re-authored.
    assert agent.counts() == {
        "plan-qa": 1,
        "repair-qa-plan": 3,
        "resolve-operator": 1,
    }, agent.counts()
    assert okf.runs == 0, "an invalid plan must never be executed"
    assert result.spent == "3 QA-plan schema repair", result.spent


def test_a_plan_that_parses_but_does_not_test_the_story_is_sent_back(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The semantic plan gate refuses, and stops being able to after two passes.

    A reviewer that never relents used to spend the whole judgement budget here and end the
    story with no QA verdict — the outcome its own brief calls strictly worse than QA run
    against a merely adequate plan. `MAX_BLOCKING_PLAN_REVIEWS` caps the refusals it can
    make stick, and once they are spent the gate is not entered again: a third pass could
    raise nothing that would change where the plan goes, so the plan goes to the stack
    without paying for it. The gate's job is intact and its failure mode is bounded.
    """
    okf = ostler()
    agent = _Agent(docs, review="revise")

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.counts() == {
        "plan-qa": 1,
        "repair-qa-plan": 2,
        "review-qa-plan": 2,
        "qa-story": 1,
        "audit-qa": 1,
    }, agent.counts()
    assert okf.runs == 1


def test_the_plan_review_is_not_entered_once_its_refusals_stop_blocking(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The cap is on entering the gate, not on the verdict it returns.

    Demoting the findings of a pass that has already been paid for leaves the expensive half
    in place: `review-qa-plan` runs at `power="high"`, and past the threshold every finding it
    can raise is demoted to polish whatever `kind` it claims — so the plan goes to the stack on
    that lap no matter what comes back, and the demoted worklist then buys a mandatory
    `repair-qa-plan` turn producing an edit nothing downstream gates on. A live story paid for
    eight review passes and five repairs that way. Both halves are dropped by declining to
    enter the node at all.

    Asserted against the constant rather than a literal: the number of blocking passes is a
    tuning decision, but "no pass beyond them" is the invariant.
    """
    ostler()
    agent = _Agent(docs, review="revise")

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    counts = agent.counts()
    assert counts["review-qa-plan"] == Qa.MAX_BLOCKING_PLAN_REVIEWS, counts
    # And no plan turn beyond the ones those refusals charged: the demoted polish lap the
    # skipped pass would have demanded is gone with it.
    assert agent.planned() == Qa.MAX_BLOCKING_PLAN_REVIEWS + 1, counts


def test_a_refusal_that_is_only_nits_is_repaired_without_a_second_review(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`kind`: a finding nothing downstream reads costs a cheap edit, not another gate pass.

    The live failure this comes from: a plan was refused four times, once for a real evidence
    gap and then three times for prose accuracy — a checkpoint naming a viewport the run does
    not exercise, an objective saying ten test cases where the file has nine. The reviewer
    said so itself, that neither reflected a missing acceptance-criterion coverage gap. Each
    was repaired correctly for about a fifth of what re-entering a `power="high"` review cost,
    and the fourth pass exhausted the judgement budget and ended the story with no QA verdict.

    So the correction is kept and the re-review is not: one repair lap, then the stack.
    """
    okf = ostler()
    agent = _Agent(docs, revise_plans=1, plan_findings=[_a_plan_nit(1), _a_plan_nit(2)])

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["review-qa-plan"] == 1, agent.counts()
    assert agent.planned() == 2, agent.counts()
    # And the repair turn was told what to fix: `_finding` blanks a *passing* gate's notes,
    # and this gate is recorded as passing.
    brief = agent.plan_args()[1]["plan_review_notes"]
    assert "N1 [plan/cosmetic]" in brief and "N2 [plan/cosmetic]" in brief, brief
    assert okf.runs == 1


def test_an_overclaim_is_a_nit_and_a_coverage_gap_is_not(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The axis is decided by the consumer, and only `coverage` has one that fails.

    An `overclaim` — a checkpoint asserting more than its cited test proves — is still
    corrected, because the post-run audit reads plan claims. It just does not buy a pass
    through the gate. A `coverage` finding beside it does, and the whole worklist rides along:
    demoting the nit must not mean dropping it.
    """
    okf = ostler()
    agent = _Agent(
        docs,
        revise_plans=1,
        plan_findings=[_a_plan_nit(1, kind="overclaim"), _a_plan_finding(2)],
    )

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    # Two reviews, not one: the coverage gap was refused and the repair was read again.
    assert agent.counts()["review-qa-plan"] == 2, agent.counts()
    brief = agent.plan_args()[1]["plan_review_notes"]
    assert "N1 [plan/overclaim]" in brief and "R2 [plan/coverage]" in brief, brief
    assert okf.runs == 1


def test_a_polish_lap_that_breaks_the_yaml_still_does_not_earn_a_re_review(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The skip is structural, so the schema loop cannot smuggle the gate pass back in.

    A polish lap returns through `_validated` exactly like any other plan turn, and a plan
    that no longer parses goes round the schema budget from there. `plan_polish_pending`
    survives that detour — were the skip a branch on "did we just come from the polish
    arm", one mistyped field would restore the expensive review pass the demotion exists to
    drop, and the treadmill would come back only for plans that also had a typo.
    """
    okf = ostler(plan_invalid_passes=(2,))
    agent = _Agent(docs, revise_plans=1, plan_findings=[_a_plan_nit(1)])

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["review-qa-plan"] == 1, agent.counts()
    # The draft, the polish repair that broke the file, and the schema repair that fixed it.
    assert agent.planned() == 3, agent.counts()
    assert okf.runs == 1


def test_each_plan_turn_is_told_everything_the_reviewer_already_refused(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A refusal outlives the draft it was written against.

    `cleared()` blanks `plan_review_notes` before each plan turn, which is right — it
    describes a plan that no longer exists. The *demand* inside it does not expire with the
    draft, and forgetting it is what let a live story spend its whole judgement budget being
    told the same thing: the reviewer's first and fifth refusal both said the copied URL was
    never opened in a fresh page, and each plan turn read it as a first-time request.

    The demoted third refusal is in the ledger too. It no longer blocks, but the repair turn
    it does buy has to be told what every earlier pass asked for, or the cheap lap spends
    itself undoing a correction an expensive one already demanded.
    """
    ostler()
    agent = _Agent(docs, review="revise")

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    briefs = [args["prior_plan_reviews"] for args in agent.plan_args()]
    assert len(briefs) == 3, briefs
    assert briefs[0] == "", "the first draft has been refused nothing"
    # Each later turn carries every refusal so far, oldest first and numbered by its pass —
    # each one the composed finding list, not the pass's prose summary.
    assert briefs[1].startswith("1. (plan-review pass 1) R1 [plan/coverage] scenario "), briefs[1]
    assert [line.split(")")[0] + ")" for line in briefs[2].splitlines() if line[:1].isdigit()] == [
        f"{index}. (plan-review pass {index})" for index in range(1, 3)
    ], briefs[2]


def test_schema_repairs_cannot_starve_the_semantic_plan_gate(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A run of `qa_plan.py` typos leaves the reviewer its full budget.

    The regression: both gates charged one shared ceiling of four, so a story that spent
    three repairs on schema defects reached `review-qa-plan` with a single revision left
    and gave up "after 4 total QA-plan repair" — which reads to a triaging human as a plan
    nobody could make work, when the plan had been read for coverage exactly once.

    Three schema repairs still buy the reviewer every critical read it is entitled to: both
    passes that can refuse. A typo has never been evidence about coverage, and it must not
    silently buy fewer coverage reads.
    """
    okf = ostler(plan_invalid=3)
    agent = _Agent(docs, review="revise")

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.counts() == {
        "plan-qa": 1,
        "repair-qa-plan": 5,
        "review-qa-plan": 2,
        "qa-story": 1,
        "audit-qa": 1,
    }, agent.counts()
    assert okf.runs == 1


def test_validation_and_review_spend_separate_plan_budgets(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Two schema repairs cost the judgement budget nothing."""
    okf = ostler(plan_invalid=2, fail_runs=1)
    agent = _Agent(docs, revise_plans=2)

    result = drive_flow(Qa(story=STORY), env(), agent)

    # Two reviewer revisions and one post-run repair still leave a judgement repair, so
    # the story now reaches a verdict where the shared budget gave up on it.
    assert result.status == "passed", result
    assert okf.runs == 2
    assert okf.plan_validations == 6


def test_the_stacked_plan_budgets_cannot_multiply(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Alternating between the two budgets does not buy their product in laps.

    Each guard bounds its own stage and nothing bounded the sum, so a plan that failed
    validation, then review, then validation again spent a lap that neither ceiling had yet
    reached — twelve legal laps between them. A live story took thirteen turns of `plan-qa`
    exactly that way. Here the laps are spread across all three stages — schema failures, the
    two refusals the reviewer can still make stick, and a runner the assessment never accepts
    — so no stage budget is exhausted and only the total ends the run.
    """
    ostler(plan_invalid_passes=(2, 4, 6), fail_runs=99)
    agent = _Agent(docs, review="revise", escalate=True)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "exhausted", result
    assert result.spent == f"{Qa.MAX_TOTAL_PLAN_LAPS} total QA-plan lap", result.spent
    # Seven author turns for six charged laps: the draft, plus the one polish repair the
    # reviewer's last refusal buys. That one is deliberately free — it replaces a
    # `power="high"` review pass with a `power="low"` edit, so charging it to the ceiling
    # would price the cheap lap as if it were the expensive one it exists to avoid.
    assert agent.planned() == Qa.MAX_TOTAL_PLAN_LAPS + 1, agent.counts()


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


def test_a_plan_review_cut_at_its_budget_goes_to_the_runner_unjudged(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A review leaves no artifact, so the only thing to salvage is the plan it was judging.

    This is the demotion `_validated` already makes when the reviewer has spent its blocking
    budget: a plan that parses and that no gate refused, with `run` → `assess` → `audit` all
    standing downstream. An unjudged plan that gets tested beats a judged plan that never
    runs.
    """
    okf = ostler()
    agent = _Agent(docs, cut={"review-qa-plan"})

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.planned() == 1, "the cut review must not buy a replan"
    assert okf.runs == 1, "the plan the review never judged is still the one that ran"


def test_a_plan_lane_past_its_wall_clock_budget_runs_the_plan_it_has(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A spent wall-clock budget over a plan that parses is the same demotion as a spent
    reviewer budget: go to the runner.

    `plan_lane_budget_s=0` is the seam — the first plan turn charges a real, tiny delta, and
    every plan-lane ceiling is past before the reviewer is entered. A gate whose refusal
    would only buy a lap `_plan_lap` will no longer grant is pure expense, and this is the
    most expensive gate in the lane.
    """
    okf = ostler()
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY, plan_lane_budget_s=0), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["review-qa-plan"] == 0, agent.counts()
    assert okf.runs == 1, "the plan is still the one that ran"


def test_a_plan_lane_past_its_budget_with_no_runnable_plan_gives_up_naming_it(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The other half: past the budget with a plan that will not import, there is nothing to
    demote to the runner, so the flow stops — and the give-up names the wall-clock budget.

    Which budget ran out is the whole value of the record. A story filed as "0 attempts"
    because the give-up reported the code-rework counter reads as untried; this one says the
    lane ran out of hour, which is the thing an operator would raise.
    """
    ostler(plan_invalid=99)
    agent = _Agent(docs, escalate=True)

    result = drive_flow(Qa(story=STORY, plan_lane_budget_s=0), env(), agent)

    assert result.status == "exhausted", result
    assert result.spent == "the QA plan lane's wall-clock budget", result.spent


def test_a_context_rebuild_past_the_plan_budget_does_not_buy_another_author(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The join point is an entry into the plan lane too, and it obeys the same ceiling.

    `build_context` clears `plan_authored`, so a rejoin from a context rebuild used to buy a
    fresh `power="high"` authoring turn however much of the lane's wall-clock had already
    gone. A live story reached the author at 2947s of a 2400s budget by exactly this route:
    a failing run, a fix lap, a rebuilt packet, and back to `plan`.

    The fix lap is what routes through `build_context`; the plan the flow already has is what
    runs the second time.
    """
    okf = ostler(fail_runs=1)
    agent = _Agent(docs, assessment_class="product")

    result = drive_flow(Qa(story=STORY, plan_lane_budget_s=0), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["apply-qa-fixes"] == 1, agent.counts()
    assert agent.planned() == 1, agent.counts()
    assert okf.runs == 2, "the rebuilt packet re-ran the plan it had"


def test_a_refusal_only_the_stack_could_fix_does_not_cost_a_replan(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`_routed`: a `revise` the plan author may not act on is overturned.

    `review-qa-plan.md` tells the reviewer the heavyweight stack is `ensure_stack`'s and not
    the plan's, and real reviews refuse plans over it anyway — an emulator that is not
    running yet, at a point in the flow where it is not supposed to be. Standing, that
    refusal costs a `power="high"` replan turn and a second full review to arrive back at the
    identical plan, because there was nothing in the plan file to change.
    """
    okf = ostler()
    agent = _Agent(
        docs,
        revise_plans=1,
        plan_findings=[
            {
                "id": "R1",
                "scope": "stack",
                "target": "scenario `create-document`",
                "issue": "the auth emulator is not running",
                "repair": "start the emulator before the suite",
            }
        ],
    )

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    # One plan turn and one review: the refusal did not survive its own contract.
    assert agent.planned() == 1, agent.counts()
    assert agent.counts()["review-qa-plan"] == 1, agent.counts()
    assert okf.runs == 1


def test_a_mixed_refusal_keeps_only_what_the_plan_can_fix(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """One actionable finding still refuses the plan, and the stack one is not sent along.

    The brief the replan turn reads is `plan_review_notes`, so what was dropped has to be
    visibly ceded there rather than silently vanishing — a finding that reappears every pass
    with no explanation is how the reviewer and the author deadlock.
    """
    okf = ostler()
    agent = _Agent(
        docs,
        revise_plans=1,
        plan_findings=[
            {
                "id": "R1",
                "scope": "stack",
                "target": "scenario `sign-in`",
                "issue": "the auth emulator is not running",
                "repair": "start the emulator before the suite",
            },
            {
                "id": "R2",
                "scope": "plan",
                "target": "scenario `create-document` / covers `AC-2`",
                "issue": "AC-2's terminal assertion proves nothing",
                "repair": "assert the row is present after the dialog closes",
            },
        ],
    )

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.planned() == 2, agent.counts()
    brief = agent.plan_args()[1]["plan_review_notes"]
    assert "Outside the plan's authority" in brief, brief
    assert "the auth emulator is not running" in brief, brief
    assert okf.runs == 1


def test_the_replan_brief_is_composed_from_the_findings_not_the_prose(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """What the author is told to fix is the finding list, rendered the same way every pass.

    `notes` used to *be* the repair contract, so the author's brief varied with how discursive
    that pass's reviewer felt — and a plan author handed a paragraph rewrites the plan. Each
    finding now renders to one line naming its id, scope, kind, target and repair; the
    reviewer's summary survives, demoted to the last line. Both axes are on the line because
    both decide what happens to the finding, and the give-up record is read from the same
    rendering — a nit that did not block has to be legible as one.
    """
    ostler()
    agent = _Agent(docs, revise_plans=1)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    brief = agent.plan_args()[1]["plan_review_notes"]
    assert (
        "R1 [plan/coverage] scenario `create-document`: review pass 1. Repair: assert" in brief
    ), brief
    assert brief.splitlines()[-1] == "Summary: review pass 1", brief


def test_only_the_first_draft_is_authored_and_every_lap_after_it_repairs(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """All three guards land on `repair_plan`, whichever of them fired.

    Re-entering `plan` regenerates the whole file from the story, which resamples the
    scenarios the reviewer already accepted and hands the next review a fresh set of defects
    to find — the loop then has no reason to terminate. Here a schema failure, a semantic
    refusal and a post-run assessment all fire in one run, and only the very first turn is
    an authoring turn.
    """
    ostler(plan_invalid=1, fail_runs=1)
    agent = _Agent(docs, revise_plans=1)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["plan-qa"] == 1, agent.counts()
    # One schema repair, one review repair, one post-run repair.
    assert agent.counts()["repair-qa-plan"] == 3, agent.counts()
    assert agent.calls[0] == "plan-qa", agent.calls


@pytest.mark.parametrize(
    ("findings", "expected"),
    [
        pytest.param([], "no findings", id="a refusal that names nothing"),
        pytest.param(
            [{"id": "R1", "scope": "plan", "target": "scenario `x`", "issue": "thin"}],
            "finding 1 missing repair",
            id="a finding with no repair to make",
        ),
    ],
)
def test_a_refusal_the_author_cannot_act_on_fails_the_run(
    findings: list[dict[str, str]],
    expected: str,
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A `revise` is a bill; one that names nothing actionable is a reviewer that did not answer.

    Sending it on would spend a `power="medium"` replan and a second `power="high"` review to
    arrive at the same plan, which is the loop this contract exists to close. Failing loudly
    puts the defect on the reviewer's prompt, where it can be fixed once.
    """
    ostler()
    agent = _Agent(docs, revise_plans=1, plan_findings=findings)

    with pytest.raises(WorkflowFailed, match=expected):
        drive_flow(Qa(story=STORY), env(), agent)


def test_three_review_revisions_leave_one_post_run_repair(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The judgement budget the reviewer did not spend is still there for a post-run finding.

    The reviewer's third refusal is never asked for, so two of the four judgement repairs
    remain when the runner comes back failing — and the story reaches a verdict with one
    still unspent. That is the whole point of capping the review: the budget exists to buy
    repairs of a plan that has been *executed*, and the treadmill spent it before the plan
    had run once. The post-run repair is not reviewed either: the cap is on the gate, not on
    the refusal that reached it, so nothing re-enters it once it is spent.
    """
    okf = ostler(fail_runs=1)
    agent = _Agent(docs, revise_plans=3)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    # Four plan turns: the draft, the two charged reviewer repairs, and the post-run one.
    assert agent.counts() == {
        "plan-qa": 1,
        "repair-qa-plan": 3,
        "review-qa-plan": 2,
        "qa-story": 2,
        "audit-qa": 1,
    }, agent.counts()
    assert okf.runs == 2, "the repair the assessment asked for must actually be executed"


def test_a_plan_loop_give_up_leaves_the_reviewers_finding_on_disk(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`record_qa_giveup`: the give-up writes the `qa.md` its own status points at.

    `flag_qa_failure` appends `<spec_dir>/qa.md` to the `needs manual review` status only if
    the file is there, and on this path nothing had ever written one — no plan was ever
    approved, so no run, no assessment. The human was sent to review a story whose whole
    account of itself was only an aggregate attempt count.

    The findings existed the entire time. `review_plan` puts the reviewer's refusal on
    `QaLoop.plan_review_notes` on the very transition that reaches the guard, and `_exhausted`
    used to drop it: `QaFlowResult` carries the code-rework verdict, which on this path is
    empty. A live run lost a correct and specific diagnosis that way — three scenarios
    asserting a raw substring against a validation body the API double-JSON-encodes — and the
    only copy of it was a run-dir artifact the next story's QA flow overwrote.

    The reviewer alone can no longer reach this guard — `MAX_BLOCKING_PLAN_REVIEWS` sees to
    that — so the give-up here is driven the way it now happens in practice: a reviewer that
    keeps refusing *and* a runner the post-run assessment never accepts. The ledger it leaves
    behind is the same one, and it is what the human triaging the marker reads.
    """
    ostler(fail_runs=99)
    agent = _Agent(docs, review="revise")

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "exhausted", result
    giveup = docs / SPEC_REL / "qa.md"
    assert giveup.is_file(), "the give-up must leave the file its status points at"
    text = giveup.read_text(encoding="utf-8")
    assert f"{Qa.MAX_PLAN_REWORKS} QA-plan repair" in text, text
    # And every earlier refusal beside it: two refusals that say the same thing mean the plan
    # turn was told and did not comply, which is a different triage from two fresh findings.
    assert "Plan review — every refusal, in order" in text, text
    for index in range(1, 3):
        assert f"**Pass {index}.** R{index} [plan/coverage] scenario " in text, text
    # Two is all there are: the gate is not entered once its refusals stop being blocking.
    assert "**Pass 3.**" not in text, text


def test_the_give_up_document_is_typed_like_any_other_spec_doc(tmp_path: Path) -> None:
    """A bare give-up doc plants an `okf-missing-type` error the *next* story trips over.

    It lands in `docs/specs/<slug>/`, where every document is an OKF Concept and a missing
    non-empty `type` is a doctor *error*. The docs gate runs `ostler doctor` over the tree,
    not over the story — so a give-up here left a permanent error that the following story's
    documentation phase read as its own blocker and refused to converge on, with nothing
    linking the two. A real run lost a story to it days after the give-up.
    """
    record = record_qa_giveup(
        logging.getLogger("test"),
        spec_dir=str(tmp_path),
        story_slug=STORY,
        spent="4 QA-plan repair",
        plan_review_notes="the reviewer never approved a plan",
    )

    assert record.written is True
    text = (tmp_path / "qa.md").read_text(encoding="utf-8")
    front = yaml.safe_load(text.split("---")[1])
    assert front["type"] == "spec.qa", text
    assert "the reviewer never approved a plan" in text, text


def test_a_give_up_never_overwrites_a_real_qa_assessment(tmp_path: Path) -> None:
    """A run that produced an assessment has the better document — the node keeps it.

    `_exhausted` is reached from four budgets, and two of them (`code rework`, the
    operator-guided loop) run *after* QA has executed and written its own account. Summarizing
    the loop's gate notes over the top of that would replace evidence with a digest.
    """
    written = "# QA — STORY-1\n\nEleven scenarios ran; two failed on the empty state.\n"
    (tmp_path / "qa.md").write_text(written, encoding="utf-8")

    record = record_qa_giveup(
        logging.getLogger("test"),
        spec_dir=str(tmp_path),
        story_slug=STORY,
        spent="3 code rework",
        assessment_notes="two scenarios still fail",
    )

    assert record.written is False
    assert record.path == str(tmp_path / "qa.md")
    assert (tmp_path / "qa.md").read_text(encoding="utf-8") == written


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
    write(docs / "qa-stack.yml", "app_cwd: .\nhealth:\n  - run: true\n")
    agent = _Agent(docs)
    #: How many agent turns had been taken when the stack came up. Zero is the assertion.
    turns_before: list[int] = []

    def _up(*a: Any, **k: Any) -> dict[str, Any]:
        turns_before.append(len(agent.calls))
        return {"ready": "yes", "entry_url": "http://x"}

    monkeypatch.setattr(workhorse_stack, "ensure_stack", _up)

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
    write(docs / "qa-stack.yml", "app_cwd: .\nhealth:\n  - run: true\n")
    monkeypatch.setattr(
        workhorse_stack, "ensure_stack", lambda *a, **k: {"ready": "yes", "entry_url": "http://x"}
    )
    agent = _Agent(docs, setup="fixed")

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
    write(docs / "qa-stack.yml", "app_cwd: .\nhealth:\n  - run: true\n")
    results = [{"ready": "no", "failed_step": "health"}, {"ready": "yes", "entry_url": "http://x"}]
    monkeypatch.setattr(workhorse_stack, "ensure_stack", lambda *a, **k: results.pop(0))
    agent = _Agent(docs, setup="fixed")

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert result.docs_recheck_required is True
    assert agent.counts()["setup-fix"] == 1, agent.counts()
    assert results == [], "the stack was never brought up a second time"
    # The fixer is told which manifest to repair, or it authors one the run never reads.
    assert agent.args_for("setup-fix")[0]["stack_manifest"] == "qa-stack.yml"


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
    write(docs / "qa-stack.yml", "app_cwd: .\nhealth:\n  - run: true\n")
    results = [
        {"ready": "no", "failed_step": "health[0]", "error": "api-test container is not running"},
        {"ready": "yes", "entry_url": "http://x"},
    ]
    monkeypatch.setattr(workhorse_stack, "ensure_stack", lambda *a, **k: results.pop(0))
    agent = _Agent(docs, setup="fixed")

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
    """The YAML cycle with no terminal — the ledger's C3 finding — now has one.

    `guard_setup` escalates a spent setup budget to the operator gate, and the gate's answer
    is applied as a QA fix that rejoins at `build_context` — which walks back to the stack,
    which is still down, which finds the budget still spent, which escalates again. Every
    counter on that cycle was either already at its cap or (`qa_rework`) read by nothing on
    it, so in auto mode — where the resolver always answers — nothing broke the cycle and the
    driver's transition budget ended the run, hundreds of agent turns later.

    `apply_resolved` now reads the budget it was already spending, so the third lap ends the
    flow `exhausted` and the parent decides what that costs. The transition budget is pinned
    low here so a regression is a failed assertion rather than a very slow test.
    """
    ostler()
    write(docs / "qa-stack.yml", "app_cwd: .\nhealth:\n  - run: true\n")
    monkeypatch.setattr(
        workhorse_stack, "ensure_stack", lambda *a, **k: {"ready": "no", "failed_step": "health"}
    )
    monkeypatch.setenv("WORKHORSE_MAX_TRANSITIONS", "60")
    agent = _Agent(docs, setup="unfixable")

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "exhausted", result
    assert result.qa_rework == Qa.MAX_QA_REWORKS, result
    # Two repairs before the setup budget is spent, and the gate is what it hands off to.
    assert agent.counts()["setup-fix"] == 2, agent.counts()
    # One resolver turn per lap of the gate, and the laps are what is now bounded.
    assert agent.counts()["resolve-operator"] == Qa.MAX_QA_REWORKS, agent.counts()


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
    there is any evidence about it — and the second is spent on a person instead.
    """
    ostler(blocked_problems=["target 'web' requires the Playwright Python package"])
    monkeypatch.setenv("WORKHORSE_MAX_TRANSITIONS", "60")
    agent = _Agent(docs, setup="fixed")

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "exhausted", result
    counts = agent.counts()
    assert counts["setup-fix"] == 1, counts
    assert counts["setup-fix"] < Qa.MAX_SETUP_REWORKS, counts
    # And the block reached a person on every lap instead.
    assert counts["resolve-operator"] == Qa.MAX_QA_REWORKS, counts


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
    moving — three agent turns a lap, one of them the unbounded-timeout resolver. This is the
    cycle a live coder run hit; it is the reason the guard in `apply_resolved` exists.
    """
    ostler(context_invalid=99)
    monkeypatch.setenv("WORKHORSE_MAX_TRANSITIONS", "60")
    agent = _Agent(docs, repair="blocked")

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "exhausted", result
    assert result.qa_rework == Qa.MAX_QA_REWORKS, result
    assert agent.counts()["resolve-operator"] == Qa.MAX_QA_REWORKS, agent.counts()
    assert agent.counts()["apply-qa-fixes"] == Qa.MAX_QA_REWORKS, agent.counts()


def test_a_fixer_that_reports_blocked_reaches_the_operator(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`blocked` is the fixer saying nothing it does in this repo can help — so stop asking it.

    The prompt has always asked for this status on a credential it cannot hold, a product
    decision in neither the story nor the plan, or work in another repo. The node discarded
    it and re-entered `build_context` regardless, so the answer to "I am blocked on X" was
    the same question again, at high power, until the budget ran out — and the story was then
    filed as `exhausted`, which reads as "we tried and failed" rather than as blocked on X.

    Here the first `blocked` reaches the operator gate instead, so the block is put to
    somebody who can answer it — and the flow spends half the full QA laps getting there.
    Without this, the same script consults nobody and re-plans and re-runs the entire QA
    suite four times over (`plan-qa`/`qa-story` × 4) before filing the story exhausted.
    """
    ostler(fail_runs=99)
    seen: list[str] = []
    agent = _Agent(docs, assessment_class="product", qa_fix="blocked", escalate=True)

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen)):
        result = drive_flow(Qa(story=STORY), env(), agent)

    counts = agent.counts()
    # The block is asked of the operator on the first fix, not swallowed.
    assert counts["resolve-operator"] == 2, counts
    assert seen == [ESCALATION_NOTE, ESCALATION_NOTE], seen
    # And each lap that would have re-planned and re-run the whole suite is one the gate
    # took instead: two full QA laps rather than the baseline four.
    assert counts["qa-story"] == 2, counts
    assert counts["plan-qa"] + counts["repair-qa-plan"] == 2, counts
    assert result.status == "exhausted", result


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
    # The resolver's note, not `loop.block_notes`: the escalated `Await` waits on this file
    # without rewriting it, so the human arrives to what the resolver already tried. See
    # `dev`'s `test_an_escalating_resolver_leaves_its_note_for_the_human`.
    assert seen == [ESCALATION_NOTE], seen


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

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "exhausted", result
    assert agent.counts()["audit-qa"] == 0, agent.counts()
    assert agent.counts()["apply-qa-fixes"] == 0, agent.counts()
    # The draft, plus one plan turn per judgement rework the gate is entitled to spend.
    assert agent.planned() == Qa.MAX_PLAN_REWORKS + 1, agent.counts()


def test_an_audit_that_refutes_the_pass_turns_it_into_a_product_failure(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`mark-qa-audit-failed.py`: a product contradiction is a fix, not a replan."""
    ostler()
    agent = _Agent(docs, audit=("refuted", "product-contradiction"), escalate=True)

    result = drive_flow(Qa(story=STORY), env(), agent)

    # Every subsequent pass is refuted the same way, so the fix loop runs out its budget.
    assert result.status == "exhausted", result
    assert agent.counts()["apply-qa-fixes"] == 3, agent.counts()
    assert agent.counts()["triage-qa"] == 4, agent.counts()


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
    repair until it has run; the second is put to the operator instead of to the budget.
    """
    ostler(fail_runs=99, scenarios=(_STUCK,))
    agent = _Agent(docs, assessment_class="product", triage=("qa_fix", "code"))

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "exhausted", result
    # The operator gate runs the same fixer prompt, so count the laps of the *fix loop* —
    # the ones carrying no operator answer — rather than every invocation of it.
    unaided = [a for a in agent.args_for("apply-qa-fixes") if "operator_feedback" not in a]
    assert len(unaided) == 1, agent.args_for("apply-qa-fixes")
    assert len(unaided) < Qa.MAX_QA_REWORKS
    # And the failure reached a person instead of the rest of the budget.
    assert agent.counts()["resolve-operator"] >= 1, agent.counts()


def test_a_plan_repair_does_not_make_the_fix_loops_first_visit_a_stall(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The two repair loops share one fingerprint field and must not share its verdict.

    Straight from a live story. The run failed, the assessment sent it to the plan author,
    the plan lap stamped the fingerprint, the repaired plan was approved, and its one
    product-test finding was routed to the fix loop — all without a second run, because a
    plan repair does not re-run the suite. The fix loop's first visit then compared the
    untouched fingerprint against itself, announced "the last code fix left the QA run
    failing identically", and escalated to the operator having spent no code lap at all.

    A stall means *this* loop paid for a repair and got the same answer. Neither half of
    that was true here.
    """
    ostler(fail_runs=1, scenarios=(_STUCK,))
    agent = _Agent(
        docs,
        repair_plans=1,
        approve_reviews=1,
        revise_plans=1,
        plan_findings=[_a_product_test_finding("R1")],
    )

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    # The fix loop got its own lap, unaided — not a guided one behind an operator gate.
    unaided = [a for a in agent.args_for("apply-qa-fixes") if "operator_feedback" not in a]
    assert len(unaided) == 1, agent.args_for("apply-qa-fixes")
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
            for depth in (3, 5, 7, 9)
        ),
    )
    agent = _Agent(docs, assessment_class="product", triage=("qa_fix", "code"), escalate=True)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "exhausted", result
    assert agent.counts()["apply-qa-fixes"] == Qa.MAX_QA_REWORKS, agent.counts()


def test_the_fix_loop_grants_one_bonus_pass_only_for_an_evidence_failure(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`guard_qa_bonus`: past the budget, a missing-proof finding earns one more attempt.

    `code` and `environment` earn nothing, which is what the companion assertion below
    covers — the bonus is for the case where the code may well be right and the proof is
    what is missing, so one verification-only pass is cheap and often decisive.
    """
    ostler(fail_runs=99)
    agent = _Agent(docs, assessment_class="product", triage=("qa_fix", "evidence"), escalate=True)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "exhausted", result
    assert agent.counts()["apply-qa-fixes"] == 4, agent.counts()


def test_a_code_failure_earns_no_bonus_pass(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The same run, triaged `code`: three fixes and out."""
    ostler(fail_runs=99)
    agent = _Agent(docs, assessment_class="product", triage=("qa_fix", "code"), escalate=True)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "exhausted", result
    assert agent.counts()["apply-qa-fixes"] == 3, agent.counts()


# ------------------------------------------------------------------ the give-up is a handoff


def test_a_spent_budget_asks_the_operator_before_abandoning_the_story(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A give-up is where an operator's one sentence is worth the most, and was where nobody asked.

    Eleven sites in this flow file a story `exhausted`, and until this only two of them had
    ever reached the gate. Every one of those give-ups is a story a person could plausibly
    unblock — the port is squatted, the driver is fine, that assertion tests the wrong thing —
    and the flow's answer was to stamp it and move on.
    """
    ostler(fail_runs=99)
    agent = _Agent(docs, assessment_class="product", triage=("qa_fix", "code"))

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "exhausted", result
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    # The answer is spent as a fix, which is the whole point of asking for it.
    guided = [a for a in agent.args_for("apply-qa-fixes") if "operator_feedback" in a]
    assert len(guided) == 1, agent.args_for("apply-qa-fixes")
    assert "staging bucket" in guided[0]["operator_feedback"]
    # And the marker still names the budget that ran out, not the gate that followed it: a
    # human triaging it needs to know the story burned its code reworks.
    assert result.spent == "3 code rework plus an operator-guided lap", result.spent


def test_an_escalating_resolver_gives_up_now_rather_than_halting_the_drain(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """In `auto` mode the gate gets one shot, and declining it is not a reason to stop the fleet.

    The story drain is single-threaded, so a QA gate that parks holds up every remaining epic
    — which is the stall this whole change is removing, not a fix for it. The flow was already
    one transition from filing the story as abandoned-but-visible, so it files it.
    """
    ostler(fail_runs=99)
    seen: list[str] = []
    agent = _Agent(docs, assessment_class="product", triage=("qa_fix", "code"), escalate=True)

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen)):
        result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "exhausted", result
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    assert seen == [], "auto mode must never park the run on a spent budget"
    # No guided lap was bought, so the reported budget is the one that actually ran out.
    assert result.spent == "3 code rework", result.spent


def test_the_operator_is_asked_once_per_story_and_not_once_per_budget(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The guided lap can exhaust a second time, and that one is a give-up, not a second ask.

    Without the one-shot flag the pair cycles: `_exhausted` gates, the gate's answer is
    applied, the flow rejoins the loop that was already out of budget, and exhausts into the
    same gate again. That is the livelock `apply_resolved` already documents, one loop out.
    """
    ostler(context_invalid=9)
    agent = _Agent(docs, repair="repaired")

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "exhausted", result
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    # The same budget ends it both times, so the phrase says it once.
    assert result.spent == "3 OKF-context repair", result.spent


def test_a_human_operator_mode_still_waits_on_a_spent_budget(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Somebody who asked to be asked is still asked — the never-park rule is `auto`'s alone."""
    ostler(context_invalid=9)
    seen: list[str] = []
    agent = _Agent(docs, repair="repaired")

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen)):
        result = drive_flow(Qa(story=STORY, operator_mode="human"), env(), agent)

    assert result.status == "exhausted", result
    assert agent.counts()["resolve-operator"] == 0, agent.counts()
    assert len(seen) == 1, seen


def test_each_exhaustion_names_the_budget_it_spent(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`exhausted` is one status over several unrelated budgets, and they must not blur.

    The parent stamps this phrase into the give-up marker commit and the story frontmatter,
    and for a while it stamped `qa_rework` no matter which budget ended the flow. A story
    that burned its QA-plan repairs and so never reached a code fix was filed as
    `[QA FAILED after 0 attempts]` — which reads as a story the loop never tried, and sends
    whoever triages the marker looking in the wrong place. Each arm now says its own name.
    """
    ostler(context_invalid=9)
    result = drive_flow(Qa(story=STORY), env(), _Agent(docs, repair="repaired", escalate=True))
    assert result.status == "exhausted", result
    assert result.spent == "3 OKF-context repair", result.spent

    # The mechanical plan gate names itself, and spends only its own budget — a schema
    # give-up and a coverage give-up ask a human for very different things.
    okf = ostler(plan_invalid=9)
    result = drive_flow(Qa(story=STORY), env(), _Agent(docs, escalate=True))
    assert result.status == "exhausted", result
    assert result.spent == "3 QA-plan schema repair", result.spent
    assert okf.runs == 0

    # The one budget that can no longer end a flow on its own: a reviewer that never relents
    # is capped at `MAX_BLOCKING_PLAN_REVIEWS` refusals and the plan then goes to the stack.
    # Listed here because the absence is the point — no `spent` string names this arm.
    okf = ostler()
    result = drive_flow(Qa(story=STORY), env(), _Agent(docs, review="revise"))
    assert result.status == "passed", result
    assert okf.runs == 1

    # The post-run budget, reached only through a plan the reviewer approved and the runner
    # executed — the first run plus one per judgement repair, each an assessment that did not
    # reach the objective.
    okf = ostler(fail_runs=99)
    result = drive_flow(Qa(story=STORY), env(), _Agent(docs, escalate=True))
    assert result.status == "exhausted", result
    assert result.spent == f"{Qa.MAX_PLAN_REWORKS} QA-plan repair", result.spent
    assert okf.runs == Qa.MAX_PLAN_REWORKS + 1

    ostler(fail_runs=99)
    agent = _Agent(docs, assessment_class="product", triage=("qa_fix", "code"), escalate=True)
    result = drive_flow(Qa(story=STORY), env(), agent)
    assert result.status == "exhausted", result
    assert result.spent == "3 code rework", result.spent

    # A dev target reworks nothing by design, so its count is a truthful zero — which is
    # exactly the number that used to be indistinguishable from "the loop never ran".
    ostler(fail_runs=99)
    agent = _Agent(docs, assessment_class="product", escalate=True)
    result = drive_flow(Qa(story=STORY, target_env="dev"), env(), agent)
    assert result.status == "exhausted", result
    assert "dev target" in result.spent, result.spent


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

    result = drive_flow(Qa(story=STORY, triage_scope_count=2), env(), agent)

    assert result.status == "exhausted", result
    assert result.triage_scope == 2, "the parent's budget is handed back unspent"
    assert agent.counts()["apply-qa-fixes"] == 3, agent.counts()


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

    result = drive_flow(Qa(story=STORY), env(), agent)

    # The auditor never relents in this fake, so the flow still ends exhausted — but on the
    # budget that names the work, and having actually attempted it.
    assert result.status == "exhausted", result
    assert result.spent == "3 code rework", result.spent
    assert agent.counts()["apply-qa-fixes"] == Qa.MAX_QA_REWORKS, agent.counts()
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
    committed test, and appending scenarios to `qa_plan.py` cannot supply it.
    """
    ostler()
    agent = _Agent(
        docs,
        disposition="extend_plan",
        assessment_findings=[_a_product_test_finding("S1")],
        escalate=True,
    )

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "exhausted", result
    assert result.spent == "3 code rework", result.spent
    assert agent.counts()["apply-qa-fixes"] == Qa.MAX_QA_REWORKS, agent.counts()
    assert agent.counts()["repair-qa-plan"] == 0, agent.counts()


def test_a_reviewers_product_test_finding_reaches_the_fixer_instead_of_the_floor(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The cheapest gate finds it first, and used to be the one that threw it away.

    Scoping the plan review to the plan's own authority stopped billing the author for
    repairs it may not make, but it dropped those findings rather than forwarding them. The
    same gap then cost a full plan, stack, run and audit to rediscover.
    """
    ostler()
    agent = _Agent(docs, revise_plans=1, plan_findings=[_a_product_test_finding("R1")])

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert result.qa_rework == 1
    assert agent.counts()["apply-qa-fixes"] == 1, agent.counts()
    # The refusal cost no plan lap: there was nothing in the plan file to repair.
    assert agent.counts()["repair-qa-plan"] == 0, agent.counts()
    assert "AC9" in agent.args_for("apply-qa-fixes")[0]["qa_notes"]


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
    assert agent.counts()["repair-qa-plan"] == Qa.MAX_BLOCKING_AUDITS, agent.counts()
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
    finding-less refutation the way the plan reviewer's is failed would add a new way to kill
    a run over an audit's output shape, on the gate that reads a pass which already cleared
    every other gate.
    """
    ostler()
    agent = _Agent(docs, audit=("refuted", "evidence-defect"), escalate=True)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["repair-qa-plan"] == Qa.MAX_BLOCKING_AUDITS, agent.counts()
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

    The plan reviewer has had a blocking ceiling for exactly this, justified by "the `audit`
    gate still stands downstream either way". Nothing stands downstream of the audit, so it
    needs its own: past `MAX_BLOCKING_AUDITS` plan-scoped refutations its findings are filed
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
    assert result.spent == "", result.spent
    # The ceiling is on *blocking*, not on running: the audit still ran the lap it stopped
    # blocking on, and its findings still reached the filer.
    assert agent.counts()["audit-qa"] == Qa.MAX_BLOCKING_AUDITS + 1, agent.counts()
    assert agent.counts()["repair-qa-plan"] == Qa.MAX_BLOCKING_AUDITS, agent.counts()


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

    assert result.status == "exhausted", result
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

    assert result.status == "exhausted", result
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
    write(docs / SPEC_REL / "feedback.md", "The empty state still says 'TODO'.\n")
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["apply-qa-fixes"] == 1, agent.counts()
    assert okf.runs == 2, okf.runs
    # Feedback is not a failure of the fix loop, so no rework is spent on it.
    assert result.qa_rework == 0
    assert result.docs_recheck_required is True
    assert "TODO" in agent.args_for("apply-qa-fixes")[0]["operator_feedback"]
    # The inbox is stamped consumed, which is what stops the second pass looping.
    assert "CONSUMED" in (docs / SPEC_REL / "feedback.md").read_text()


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
    assert suite.calls[0] == ["make", "e2e-journeys"]
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
    """`mark-regression-unresolved.py`: three fix attempts, then it is an ordinary failure."""
    ostler()
    monkeypatch.setattr(regression_nodes, "_run", _Suite(fail_runs=99))
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "exhausted", result
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


def test_the_worklist_a_review_pass_is_scored_against_survives_a_resume(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`plan_review_progress`: the budget counters say a story was expensive, not why.

    `plan_review_rework=2` is the same number whether the author was handed the same demand
    twice and ignored it, or closed each one and was met with a new one. Those want
    opposite interventions — one is a plan turn that will not comply, the other a reviewer
    that will not converge — and until this was recorded nothing in the run could tell them
    apart. The treadmill's own signature is `churned`: the same number outstanding each pass,
    a different set of them.

    What is asserted here is the *baseline*, not the verdict: `plan_review_progress` is a
    recorded verdict and blanks with the rest of them on the next plan lap, so by the audit it
    is gone as designed. `plan_review_ids` deliberately is not one — it is the previous pass's
    worklist, and forgetting it would make every pass look like the first. Read off the
    checkpoint because that is the property that matters: a resume must score the next pass
    against the same baseline the killed run would have.
    """
    ostler()
    run_env = env()
    run_dir = run_env.writer.run_dir

    with pytest.raises(RuntimeError, match="killed during audit-qa"):
        drive_flow(Qa(story=STORY), run_env, _Agent(docs, review="revise", explode={"audit-qa"}))

    checkpoint = parse_checkpoint((run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    loop = read_resume(checkpoint).params["loop"]
    assert loop["plan_review_ids"] == ["R2"], loop
    assert loop["plan_review_progress"] == "", loop


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
    write(docs / "qa-stack.yml", "app_cwd: .\nhealth:\n  - run: true\n")
    monkeypatch.setattr(
        workhorse_stack, "ensure_stack", lambda *a, **k: {"ready": "yes", "entry_url": "http://x"}
    )
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    assert agent.planned() == 1, agent.counts()
