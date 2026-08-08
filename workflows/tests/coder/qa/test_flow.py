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
from workhorse import stack as workhorse_stack
from workhorse.artifacts import ArtifactWriter
from workhorse.pyflow import driver as pyflow_driver
from workhorse.pyflow.driver import read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import parse_checkpoint

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

QA_PLAN = """version: 1
steps:
  - id: s1
    run: check the thing exists
"""


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
        vet_problems: list[str] | None = None,
    ) -> None:
        self.fail_runs = fail_runs
        self.context_invalid = context_invalid
        self.plan_invalid = plan_invalid
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
        if self.plan_validations <= self.plan_invalid:
            return 1, {"status": "invalid", "notes": "step 3 names no assertion"}, ""
        return 0, {"status": "passed"}, ""

    # -- the run ----------------------------------------------------------

    def qa_run(
        self, plan: str, spec_dir: str, *, docs_root: Path | None = None
    ) -> tuple[int, dict[str, Any], str]:
        self.runs += 1
        status = "failed" if self.runs <= self.fail_runs else "passed"
        self._write_run(Path(spec_dir), status)
        return (0 if status == "passed" else 1), {
            "status": status,
            "notes": f"run {self.runs} reported {status}",
        }, ""

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


class _Agent:
    """The flow's eleven prompts, scripted on the axes its states branch on.

    Each handler writes what its prompt claims to write — the plan turn writes `qa-plan.yml`,
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
        disposition: str = "confirmed",
        failure_class: str = "none",
        objective: str = "yes",
        assessment_class: str = "none",
        audit: tuple[str, str] = ("stands", "none"),
        triage: tuple[str, str] = ("qa_fix", "code"),
        setup: str = "fixed",
        escalate: bool = False,
        scope: str = "story",
        explode: set[str] | None = None,
    ) -> None:
        self.docs = docs
        self.repair = repair
        self.review = review
        self.revise_plans = revise_plans
        self.disposition = disposition
        self.failure_class = failure_class
        self.objective = objective
        self.assessment_class = assessment_class
        self.audit = audit
        self.triage = triage
        self.setup = setup
        self.escalate = escalate
        self.scope = scope
        self.explode = explode or set()
        self.calls: list[str] = []
        self.args: list[dict[str, Any]] = []
        self.dirs: list[list[str]] = []

    # -- the seam ---------------------------------------------------------

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        stem = Path(node.prompt).stem
        data = ctx.as_dict()
        self.calls.append(stem)
        self.args.append(data)
        self.dirs.append(list(node.add_dirs or []))
        if stem in self.explode:
            raise RuntimeError(f"killed during {stem}")
        handler = getattr(self, f"_{stem.replace('-', '_')}")
        return f"(scripted) {node.prompt}", handler(data, self.counts()[stem])

    def counts(self) -> Counter[str]:
        return Counter(self.calls)

    def args_for(self, stem: str) -> list[dict[str, Any]]:
        return [a for s, a in zip(self.calls, self.args, strict=True) if s == stem]

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
        (Path(data["spec_dir"]) / "qa-plan.yml").write_text(QA_PLAN, encoding="utf-8")
        return {"status": "planned", "notes": f"plan pass {nth}"}

    def _review_qa_plan(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        # `revise_plans` follows `_Ostler`'s convention: a count of *leading* refusals, for
        # the tests that need the reviewer to relent and let a plan through.
        disposition = "revise" if nth <= self.revise_plans else self.review
        return {"disposition": disposition, "notes": f"review pass {nth}"}

    def _qa_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        # A runner failure the assessment confirms is a product defect unless the test says
        # otherwise; a runner pass has nothing to classify.
        failed = data["runner_status"] == "failed"
        return {
            "disposition": self.disposition,
            "failure_class": self.assessment_class if failed else self.failure_class,
            "objective_reached": "no" if failed else self.objective,
            "notes": f"assessment pass {nth}",
        }

    def _audit_qa(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        verdict, refutation = self.audit
        return {
            "verdict": verdict,
            "refutation_class": refutation,
            "notes": f"audit pass {nth}",
        }

    def _triage_qa(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        action, failure_class = self.triage
        return {"triage_action": action, "qa_failure_class": failure_class}

    def _apply_qa_fixes(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return {"status": "fixed", "notes": f"fix pass {nth}"}

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
    """A stand-in for the human an `Await` is waiting on, patched over `poll_until_touched`."""

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
    agent = _Agent(docs, repair="repaired")

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "exhausted", result
    assert agent.counts() == {"repair-qa-context": 3}, agent.counts()
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


def test_human_operator_mode_waits_on_the_story_context_file(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`operator_mode=human` skips the resolver and blocks on `<story>/context.md`."""
    ostler(context_invalid=1)
    seen: list[str] = []
    agent = _Agent(docs, repair="blocked")

    with patch.object(pyflow_driver, "poll_until_touched", _answers(seen)):
        result = drive_flow(Qa(story=STORY, operator_mode="human"), env(), agent)

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


def test_an_unrunnable_plan_spends_the_total_repair_budget_then_gives_up(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Four total repairs buy five plan turns and never reach the stack."""
    okf = ostler(plan_invalid=9)
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "exhausted", result
    assert agent.counts() == {"plan-qa": 5}, agent.counts()
    assert okf.runs == 0, "an invalid plan must never be executed"


def test_a_plan_that_parses_but_does_not_test_the_story_is_sent_back(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The semantic plan gate can spend all four shared repairs."""
    okf = ostler()
    agent = _Agent(docs, review="revise")

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "exhausted", result
    assert agent.counts() == {"plan-qa": 5, "review-qa-plan": 5}, agent.counts()
    assert okf.runs == 0


def test_validation_and_review_share_the_total_plan_repair_budget(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Two validation and two review repairs leave no post-run repair."""
    okf = ostler(plan_invalid=2, fail_runs=1)
    agent = _Agent(docs, revise_plans=2)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "exhausted", result
    assert agent.counts() == {
        "plan-qa": 5,
        "review-qa-plan": 3,
        "qa-story": 1,
    }, agent.counts()
    assert okf.plan_validations == 5
    assert okf.runs == 1
    assert result.spent == "4 total QA-plan repair"


def test_three_review_revisions_leave_one_post_run_repair(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The fourth and final shared repair can address a post-run finding."""
    okf = ostler(fail_runs=1)
    agent = _Agent(docs, revise_plans=3)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "passed", result
    # Five plan turns: three reviewer repairs and one post-run repair after the initial plan.
    assert agent.counts() == {
        "plan-qa": 5,
        "review-qa-plan": 5,
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
    """
    ostler()
    agent = _Agent(docs, review="revise")

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "exhausted", result
    giveup = docs / SPEC_REL / "qa.md"
    assert giveup.is_file(), "the give-up must leave the file its status points at"
    text = giveup.read_text(encoding="utf-8")
    assert "review pass 5" in text, text
    assert "4 total QA-plan repair" in text, text


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

    with patch.object(pyflow_driver, "poll_until_touched", _answers(seen)):
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
    agent = _Agent(docs)

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "exhausted", result
    assert agent.counts()["audit-qa"] == 0, agent.counts()
    assert agent.counts()["apply-qa-fixes"] == 0, agent.counts()
    assert agent.counts()["plan-qa"] == 5, agent.counts()


def test_an_audit_that_refutes_the_pass_turns_it_into_a_product_failure(
    docs: Path,
    ostler: Callable[..., _Ostler],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`mark-qa-audit-failed.py`: a product contradiction is a fix, not a replan."""
    ostler()
    agent = _Agent(docs, audit=("refuted", "product-contradiction"))

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
    agent = _Agent(docs, assessment_class="product", triage=("qa_fix", "evidence"))

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
    agent = _Agent(docs, assessment_class="product", triage=("qa_fix", "code"))

    result = drive_flow(Qa(story=STORY), env(), agent)

    assert result.status == "exhausted", result
    assert agent.counts()["apply-qa-fixes"] == 3, agent.counts()


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
    result = drive_flow(Qa(story=STORY), env(), _Agent(docs, repair="repaired"))
    assert result.status == "exhausted", result
    assert result.spent == "3 OKF-context repair", result.spent

    # The three plan stages retain separate diagnostics but exhaust one aggregate budget.
    okf = ostler(plan_invalid=9)
    result = drive_flow(Qa(story=STORY), env(), _Agent(docs))
    assert result.status == "exhausted", result
    assert result.spent == "4 total QA-plan repair", result.spent
    assert okf.runs == 0

    okf = ostler()
    result = drive_flow(Qa(story=STORY), env(), _Agent(docs, review="revise"))
    assert result.status == "exhausted", result
    assert result.spent == "4 total QA-plan repair", result.spent
    assert okf.runs == 0

    # The post-run budget, reached only through a plan the reviewer approved and the runner
    # executed — five runs, each one an assessment that did not reach the objective.
    okf = ostler(fail_runs=99)
    result = drive_flow(Qa(story=STORY), env(), _Agent(docs))
    assert result.status == "exhausted", result
    assert result.spent == "4 total QA-plan repair", result.spent
    assert okf.runs == 5

    ostler(fail_runs=99)
    agent = _Agent(docs, assessment_class="product", triage=("qa_fix", "code"))
    result = drive_flow(Qa(story=STORY), env(), agent)
    assert result.status == "exhausted", result
    assert result.spent == "3 code rework", result.spent

    # A dev target reworks nothing by design, so its count is a truthful zero — which is
    # exactly the number that used to be indistinguishable from "the loop never ran".
    ostler(fail_runs=99)
    agent = _Agent(docs, assessment_class="product")
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
    agent = _Agent(docs, assessment_class="product", triage=("rescope", "code"))

    result = drive_flow(Qa(story=STORY, triage_scope_count=2), env(), agent)

    assert result.status == "exhausted", result
    assert result.triage_scope == 2, "the parent's budget is handed back unspent"
    assert agent.counts()["apply-qa-fixes"] == 3, agent.counts()


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
