"""End-to-end tests for the `dev` flow — the three gates, the layer loop, the operator.

Thirty-five YAML nodes became twelve states holding three loops that share them: the reuse
gate, the path gate and the per-layer implement/lint loop. What is worth testing is which
arm each verdict takes and what makes each loop terminate, so the tests are organised by
gate rather than by node.

**There are no seams here beyond the agent turn.** Every deterministic node runs for real:
the story is a real authored story in a real docs repo, the workspace is two real git repos
named by a real `.code-workspace` file, `stamp_specs` really stamps the plan files ostler
then reads back, `branch_code_repos` really moves both repos onto the story branch, and
`run_lint` really shells out to the command `agents.yml` names. That is what makes the port's
parity claim checkable rather than asserted — the flow is driven against the same artifacts
the YAML engine drove against, and the same files are on disk afterwards.

The scripted agent is scripted the way `surveyor`'s is: it dispatches on the prompt's
filename, which is the same key the engine derives its node id from, and every handler leaves
behind the artifacts its reply claims to have written — the plan turn writes
`plan-context.json` and the per-service plan files, the resolver writes the operator's answer
into `context.md`, the lint fixer writes the file that makes the linter pass. A handler that
only returned a status would be testing the state machine against a fiction.
"""
from __future__ import annotations

import json
import subprocess
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from workhorse.artifacts import ArtifactWriter
from workhorse.pyflow import driver as pyflow_driver
from workhorse.pyflow.driver import read_resume
from workhorse.pyflow.engine import RunEnv

from workhorse_workflows.coder.flows.dev import Dev
from workhorse_workflows.coder.nodes.dev import (
    read_operator_context,
    resolve_impl_context,
    run_lint,
    validate_plan_context,
)

STORY = "STORY-1"
EPIC = "EPIC-1"
SPEC_REL = f"docs/specs/{STORY}"
STORY_REL = f"docs/epics/{EPIC}/stories/{STORY}"
CONTEXT_REL = f"{STORY_REL}/context.md"

#: The epic index ostler parses to learn the story exists. Without the `## Stories` heading
#: and the `### <slug>` subsection the graph does not know the story at all, and
#: `prepare_story`'s authored gate is skipped rather than satisfied — which would make every
#: test below pass for the wrong reason.
EPIC_MD = """---
title: Epic One
status: active
---

# Epic One

## Stories

### STORY-1

- title: Story One
"""

#: An *authored* story: ostler's `Story.authored` wants `Context` and `Acceptance Criteria`
#: filled and `Implementation Status` present. A scaffold with empty sections fails
#: `prepare_story`, which is the gate `test_an_unauthored_story_is_refused` drives.
STORY_MD = """---
type: story
---

# Story One

## Context

Users need a thing.

## Acceptance Criteria

- the thing exists

## Implementation Status

- **Status**: Not started
"""

#: The two services the plan declares by default, in implementation order.
SERVICES: list[dict[str, Any]] = [
    {
        "repo": "api",
        "path": ".",
        "type": "go",
        "plan_file": "plan-api.md",
        "skills": ["go-service"],
    },
    {
        "repo": "web",
        "path": ".",
        "type": "react-router",
        "plan_file": "plan-web.md",
        "skills": [],
    },
]

#: The same plan naming a repo the workspace does not carry. `validate_plan_context` rejects
#: it on the workspace lookup, which is the one failure mode no blind refine pass can repair
#: by luck — the path gate's escalation arm needs an error that stays an error.
GHOST: list[dict[str, Any]] = [
    {"repo": "ghost", "path": ".", "type": "go", "plan_file": "plan-api.md", "skills": []}
]


# --------------------------------------------------------------------------- fixtures


@pytest.fixture
def docs(repo: Path, write: Callable[[Path, str], Path]) -> Path:
    """The docs repo, carrying one epic and one authored story under it.

    `repo` is the `AGENT_REPO_DIR` pin every coder test shares; what is added here is the
    tree ostler needs to resolve the slug — the epic's own `epic.md`, its `## Stories`
    listing, and the story folder the flow's `Await` writes its questions into.
    """
    write(repo / "docs" / "epics" / EPIC / "epic.md", EPIC_MD)
    write(repo / STORY_REL / "story.md", STORY_MD)
    return repo


@pytest.fixture
def workspace(
    tmp_path: Path,
    docs: Path,
    git: Callable[..., subprocess.CompletedProcess],
    write: Callable[[Path, str], Path],
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Path]:
    """Two real git repos and the VSCode workspace file that names them, in order.

    Real repos rather than bare directories because `branch_code_repos` checks out a branch
    in each and the test asserts it landed; the paths in the workspace file are relative
    exactly as a checked-in `.code-workspace` carries them.
    """
    root = tmp_path / "ws"
    repos: dict[str, Path] = {}
    for name in ("api", "web"):
        path = root / name
        path.mkdir(parents=True)
        git(path, "init", "-q", "-b", "main")
        write(path / "README.md", f"# {name}\n")
        git(path, "add", "-A")
        git(path, "commit", "-qm", "Initial commit")
        repos[name] = path
    write(
        root / "acme.code-workspace",
        json.dumps({"folders": [{"name": n, "path": n} for n in repos]}),
    )
    monkeypatch.setenv("CODER_WORKSPACE", str(root / "acme.code-workspace"))
    return repos


@pytest.fixture
def lint_gate(
    docs: Path, workspace: dict[str, Path], write: Callable[[Path, str], Path]
) -> Path:
    """Make `api` adopt the lint gate, failing until a marker file exists.

    `run_lint` resolves its command from the orchestrating repo's `agents.yml` before
    falling back to `make lint`, and keys the map by the service name and then by the cwd's
    basename — `api` here is the second. The script is the whole gate: it fails while the
    marker is absent, so the `fix-lint` turn has something real to fix and the loop's exit
    is a genuinely clean lint rather than a scripted claim of one.

    Returns the marker path so the lint-fixer handler can create it.
    """
    write(docs / "agents.yml", "lint:\n  api: sh lint.sh\n")
    script = write(workspace["api"] / "lint.sh", "test -f .lint-ok\n")
    return script.parent / ".lint-ok"


# --------------------------------------------------------------------------- the agent


class _Agent:
    """A scripted stand-in for the flow's four prompts, writing what each claims to write.

    The knobs are the flow's branches: `blocked` makes the first N planning turns report a
    block, `bad_paths` makes the first N plan writes name a repo the workspace has not got,
    `reuse_rework` makes the first N reuse checks demand a rework, `escalate` makes the
    auto-operator hand the block to a human, `scope` is what the answer it writes claims the
    block was about, `fix_lint` decides whether the lint repair turn actually repairs
    anything, and `explode` raises on a named prompt — a run killed mid-turn.
    """

    def __init__(
        self,
        docs: Path,
        *,
        services: list[dict[str, Any]] | None = None,
        blocked: int = 0,
        bad_paths: int = 0,
        reuse_rework: int = 0,
        escalate: bool = False,
        scope: str = "story",
        fix_lint: Path | None = None,
        explode: set[str] | None = None,
    ) -> None:
        self.docs = docs
        self.services = services if services is not None else SERVICES
        self.blocked = blocked
        self.bad_paths = bad_paths
        self.reuse_rework = reuse_rework
        self.escalate = escalate
        self.scope = scope
        self.fix_lint = fix_lint
        self.explode = explode or set()
        self.calls: list[str] = []
        self.args: list[dict[str, Any]] = []
        #: Plan turns of either prompt, so `blocked` and `bad_paths` count the *writes*
        #: rather than one prompt's share of them.
        self.plans = 0

    # -- the seam ---------------------------------------------------------

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        stem = Path(node.prompt).stem
        data = ctx.as_dict()
        self.calls.append(stem)
        self.args.append(data)
        if stem in self.explode:
            raise RuntimeError(f"killed during {stem}")
        handler = getattr(self, f"_{stem.replace('-', '_')}")
        return f"(scripted) {node.prompt}", handler(data, self.counts()[stem])

    def counts(self) -> Counter[str]:
        return Counter(self.calls)

    def args_for(self, stem: str) -> list[dict[str, Any]]:
        return [a for s, a in zip(self.calls, self.args, strict=True) if s == stem]

    # -- one handler per prompt -------------------------------------------

    def _plan_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return self._plan(data)

    def _refine_plan(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return self._plan(data)

    def _plan(self, data: dict[str, Any]) -> dict[str, Any]:
        """Write the spec dir the way both planning prompts are told to, then report.

        The plan files are written *untyped*: `stamp_specs` runs right after the first plan
        turn and is what gives them their OKF `type`, so writing them with front-matter
        already in place would hide whether the stamping step ran at all.
        """
        self.plans += 1
        services = GHOST if self.plans <= self.bad_paths else self.services
        spec = Path(data["spec_dir"])
        spec.mkdir(parents=True, exist_ok=True)
        for svc in services:
            (spec / svc["plan_file"]).write_text(
                f"# Plan for {svc['repo']}::{svc['path']}\n", encoding="utf-8"
            )
        (spec / "plan-context.json").write_text(
            json.dumps(
                {
                    "story": STORY,
                    "services": services,
                    "implementation_order": [f"{s['repo']}::{s['path']}" for s in services],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if self.plans <= self.blocked:
            return {"status": "blocked", "summary": "the prod bucket may not exist"}
        return {"status": "done", "summary": f"plan {self.plans}"}

    def _check_code_reuse(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if nth <= self.reuse_rework:
            return {
                "status": "needs_rework",
                "findings": [{"path": "pkg/store", "note": "already implemented"}],
                "summary": "reuse the store",
            }
        return {"status": "ok", "findings": [], "summary": "nothing to reuse"}

    def _resolve_operator(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if self.escalate:
            return {"decision": "escalated", "summary": "needs a product call"}
        self._answer()
        return {"decision": "answered", "summary": "the bucket exists in staging"}

    def _implement_plan(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return {"status": "done", "notes": f"implemented {data['service_path']}"}

    def _fix_lint(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if self.fix_lint is None:
            return {"status": "failed", "notes": "the finding is in vendored code"}
        self.fix_lint.write_text("", encoding="utf-8")
        return {"status": "fixed", "notes": "satisfied the linter"}

    # -- what the resolver leaves behind ----------------------------------

    def _answer(self) -> None:
        """Write the answer into the file `read_operator_context` reads it back out of.

        `STATUS: ANSWERED` is what that node flips to `CONSUMED`, and `SCOPE:` is the line
        that decides whether the flow reworks this story's plan or leaves entirely.
        """
        (self.docs / CONTEXT_REL).write_text(
            f"STATUS: ANSWERED\nSCOPE: {self.scope}\n\nUse the staging bucket.\n",
            encoding="utf-8",
        )


def _answers(docs: Path, seen: list[str], *, scope: str = "story") -> Callable[..., None]:
    """A stand-in for the human an `Await` is waiting on.

    Patched over `poll_until_touched`, so it runs where the operator's edit would land: the
    questions are already in the file by then, which is what `seen` records, and writing the
    answer over them is what a person answering in place does.
    """

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text(encoding="utf-8"))
        path.write_text(
            f"STATUS: ANSWERED\nSCOPE: {scope}\n\nUse the staging bucket.\n", encoding="utf-8"
        )

    return answered


def _branch_of(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _output(run_env: RunEnv, node: Any) -> dict[str, Any]:
    """A node's recorded output — the artifact, not the return value the flow saw."""
    path = run_env.writer.run_dir / node.__name__ / "output.json"
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- happy path


def test_plans_stamps_branches_and_implements_every_layer(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """One pass through all three gates and both service layers, with no reworks."""
    agent = _Agent(docs)
    run_env = env()

    result = drive_flow(Dev(story=STORY), run_env, agent)

    assert result.status == "ready", result
    assert agent.counts() == {
        "plan-story": 1,
        "check-code-reuse": 1,
        "implement-plan": 2,
    }, agent.counts()

    # The plan files the turn wrote untyped are OKF Concepts afterwards: `stamp_specs` ran.
    for name in ("plan-api.md", "plan-web.md"):
        assert (docs / SPEC_REL / name).read_text().startswith("---\n"), name

    # Both code repos moved onto the story branch — `branch_code_repos` ran for real.
    assert _branch_of(workspace["api"]) == STORY
    assert _branch_of(workspace["web"]) == STORY

    # The layers were dispatched in the plan's declared order, each with its own plan file.
    implemented = [(a["service_path"], a["plan_file"]) for a in agent.args_for("implement-plan")]
    assert implemented == [(".", "plan-api.md"), (".", "plan-web.md")], implemented
    assert [a["service_type"] for a in agent.args_for("implement-plan")] == ["go", "react-router"]


def test_the_implement_turn_is_handed_the_three_values_its_prompt_reads(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`implement-plan.md` reads three values the YAML node never passed.

    Under the YAML engine a node's declared outputs landed in the run context and the prompt
    rendered against the whole of it; `Engine.agent` renders against `args` alone, so the
    port passes them explicitly. This is the assertion that says so — if they are dropped,
    the prompt silently renders three blanks and nothing else in the suite notices.
    """
    agent = _Agent(docs)
    run_env = env()

    drive_flow(Dev(story=STORY), run_env, agent)

    first = agent.args_for("implement-plan")[0]
    impl = _output(run_env, resolve_impl_context)
    assert first["qa_run_plan"] == impl["qa_run_plan"]
    assert first["impl_instruction_paths"] == impl["impl_instruction_paths"]
    assert first["qa_stack"] == impl["qa_stack"]


def test_an_unauthored_story_is_refused_before_anything_is_planned(
    docs: Path,
    workspace: dict[str, Path],
    write: Callable[[Path, str], Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A story ostler knows and reports unauthored fails in `setup`, not in review.

    This is the gate that exists because an author run once produced 44 stubs and reported
    success. It is in `setup`, so the failure precedes the first agent turn entirely.
    """
    write(docs / STORY_REL / "story.md", "---\ntype: story\n---\n\n# Story One\n")
    agent = _Agent(docs)

    with pytest.raises(Exception, match="not authored"):
        drive_flow(Dev(story=STORY), env(), agent)

    assert agent.calls == []


# --------------------------------------------------------------------------- reuse gate


def test_the_reuse_gate_reworks_the_plan_and_re_checks(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """One `needs_rework` sends the plan back to the refiner and the check runs again."""
    agent = _Agent(docs, reuse_rework=1)

    result = drive_flow(Dev(story=STORY), env(), agent)

    assert result.status == "ready", result
    assert agent.counts()["check-code-reuse"] == 2, agent.counts()
    assert agent.counts()["refine-plan"] == 1, agent.counts()
    # The refiner is handed the findings, and no operator context: this is a plan-quality
    # rework, not a resolved block.
    notes = agent.args_for("refine-plan")[0]
    assert "already implemented" in notes["review_notes"]
    assert notes["operator_context"] == ""


def test_the_reuse_gate_is_bounded_and_then_proceeds_anyway(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The findings are advisory: a spent budget implements the plan rather than failing.

    `max_reuse_reworks=2` buys two reworks, so the check runs three times — the off-by-one
    the `<` in `reuse_rework < self.max_reuse_reworks` decides.
    """
    agent = _Agent(docs, reuse_rework=99)

    result = drive_flow(Dev(story=STORY, max_reuse_reworks=2), env(), agent)

    assert result.status == "ready", result
    assert agent.counts()["check-code-reuse"] == 3, agent.counts()
    assert agent.counts()["refine-plan"] == 2, agent.counts()
    assert agent.counts()["implement-plan"] == 2, agent.counts()


# --------------------------------------------------------------------------- path gate


def test_validate_is_not_a_reserved_pydantic_name() -> None:
    """The path gate's state is `validate_paths`, and the name is load-bearing.

    `Workflow` is a pydantic model and state discovery skips every name already on
    `dir(Workflow)` — `validate` is one of them, pydantic v1's deprecated classmethod. A
    state called `validate` would not be a state at all: no error, no warning, just a
    transition to a target nothing dispatches. This asserts the trap stays sprung.
    """
    assert "validate_paths" in Dev.states
    assert "validate" not in Dev.states


def test_an_unresolvable_service_path_reworks_the_plan(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A plan naming a repo the workspace has not got goes back to the refiner."""
    agent = _Agent(docs, bad_paths=1)
    run_env = env()

    result = drive_flow(Dev(story=STORY), run_env, agent)

    assert result.status == "ready", result
    assert agent.counts()["refine-plan"] == 1, agent.counts()
    assert "ghost" in agent.args_for("refine-plan")[0]["review_notes"]
    # The gate's verdict is the node's, recorded: the second validation passed.
    assert _output(run_env, validate_plan_context)["status"] == "valid"


def test_an_unfixable_plan_exhausts_the_budget_and_reaches_the_operator(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Three refine passes that do not fix it escalate rather than looping forever.

    `MAX_VALIDATE_REWORKS` is 3, so the fourth validation is the one that gives up; the
    operator answers, the plan is reworked with the answer in hand — the fifth write, and
    the first good one — and the restored budget takes it through the gate.
    """
    agent = _Agent(docs, bad_paths=4)

    result = drive_flow(Dev(story=STORY), env(), agent)

    assert result.status == "ready", result
    assert agent.counts()["refine-plan"] == 4, agent.counts()
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    assert agent.args_for("resolve-operator")[0]["block_kind"] == "plan"


# --------------------------------------------------------------------------- the operator


def test_a_blocked_plan_goes_to_the_auto_operator_and_is_reworked(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`operator_mode=auto` stands an agent in for the human, and consumes its answer."""
    agent = _Agent(docs, blocked=1)
    run_env = env()

    result = drive_flow(Dev(story=STORY), run_env, agent)

    assert result.status == "ready", result
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    assert agent.counts()["refine-plan"] == 1, agent.counts()
    # The answer reached the refiner, and the marker was flipped so a later block re-arms
    # instead of consuming this same answer again.
    assert "staging bucket" in agent.args_for("refine-plan")[0]["operator_context"]
    assert "STATUS: CONSUMED" in (docs / CONTEXT_REL).read_text()


def test_an_epic_scoped_answer_leaves_the_flow_to_be_replanned(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`SCOPE: epic` means the epic premise was wrong, not this story's plan.

    It is the only exit from the flow other than an exhausted dispatch list, and it carries
    the operator's text back so the queue level can replan against it.
    """
    agent = _Agent(docs, blocked=1, scope="epic")

    result = drive_flow(Dev(story=STORY), env(), agent)

    assert result.status == "replan", result
    assert "staging bucket" in result.operator_notes
    assert agent.counts()["implement-plan"] == 0, agent.counts()


def test_human_operator_mode_waits_on_the_story_context_file(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`operator_mode=human` skips the resolver entirely and blocks on the file.

    The questions are written next to the story, which is where `await_operator.py` put them
    and where the operator answering is reading the story they are about.
    """
    seen: list[str] = []
    agent = _Agent(docs, blocked=1)

    with patch.object(pyflow_driver, "poll_until_touched", _answers(docs, seen)):
        result = drive_flow(Dev(story=STORY, operator_mode="human"), env(), agent)

    assert result.status == "ready", result
    assert agent.counts()["resolve-operator"] == 0, agent.counts()
    assert seen == ["the prod bucket may not exist"], seen


def test_an_escalating_resolver_falls_through_to_the_human(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The human path is the resolver's fallback, not a separate mode.

    A resolver that cannot resolve the block writes nothing, so the wait is on the questions
    the flow itself put in the file — which is what the escalated arm is for.
    """
    seen: list[str] = []
    agent = _Agent(docs, blocked=1, escalate=True)

    with patch.object(pyflow_driver, "poll_until_touched", _answers(docs, seen)):
        result = drive_flow(Dev(story=STORY), env(), agent)

    assert result.status == "ready", result
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    assert seen == ["the prod bucket may not exist"], seen


def test_an_unanswered_context_file_is_not_treated_as_an_answer(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    logger: Any,
) -> None:
    """`read_operator_context` reports nothing answered when the file is not there.

    The consume half of `await_operator.py`, on its own: the flow only reaches it once the
    block is known to be resolved, so this is the guard against a resume that lost the file.
    """
    answer = read_operator_context(logger, str(docs / STORY_REL / "story.md"))

    assert answer.answered is False
    assert answer.scope == "story"


# --------------------------------------------------------------------------- lint loop


def test_the_lint_gate_fixes_and_re_runs_until_clean(
    docs: Path,
    workspace: dict[str, Path],
    lint_gate: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A dirty layer is repaired and re-linted; the second run is genuinely clean.

    `web` has adopted no gate, so it is `skipped` and moves straight on — which is the
    opt-in half of the same behavior.
    """
    agent = _Agent(docs, fix_lint=lint_gate)
    run_env = env()

    result = drive_flow(Dev(story=STORY), run_env, agent)

    assert result.status == "ready", result
    assert agent.counts()["fix-lint"] == 1, agent.counts()
    assert lint_gate.is_file(), "the fixer did not write what the linter checks for"
    # The last lint of the run is `web`'s, which adopted nothing.
    assert _output(run_env, run_lint)["status"] == "skipped"
    # The fixer was handed the real command and the real findings, off the node's output.
    assert agent.args_for("fix-lint")[0]["lint_command"] == "sh lint.sh"
    assert agent.args_for("fix-lint")[0]["cwd"] == str(workspace["api"])


def test_the_lint_gate_is_bounded_and_moves_on_dirty(
    docs: Path,
    workspace: dict[str, Path],
    lint_gate: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A fixer that fixes nothing costs two attempts and then the layer moves on.

    Never a dead end: QA re-runs lint as the binding gate, so the dev-time one is
    best-effort. `max_lint_reworks=2` buys two fix turns and a third lint.
    """
    agent = _Agent(docs, fix_lint=None)

    result = drive_flow(Dev(story=STORY, max_lint_reworks=2), env(), agent)

    assert result.status == "ready", result
    assert agent.counts()["fix-lint"] == 2, agent.counts()
    assert agent.counts()["implement-plan"] == 2, agent.counts()
    assert not lint_gate.exists()


# --------------------------------------------------------------------------- resume


def test_a_run_killed_mid_implement_resumes_on_that_layer(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The checkpoint is written before a state runs, so the layer cursor survives the kill.

    This is the resume shape the port has to match: the state, the flow name, the cursor
    parameter, and inputs that reconstruct the workflow. The resumed run re-enters on
    `implement` — it does not re-plan, and it does not re-run the gates.
    """
    run_env = env()
    run_dir = run_env.writer.run_dir

    with pytest.raises(RuntimeError, match="killed during implement-plan"):
        drive_flow(Dev(story=STORY), run_env, _Agent(docs, explode={"implement-plan"}))

    checkpoint = json.loads((run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    resume = read_resume(checkpoint)
    assert resume.state == "implement", resume
    assert resume.flow == "Dev", resume
    assert resume.params == {"index": 0}, resume.params

    agent = _Agent(docs)
    result = drive_flow(Dev(**resume.inputs), env(run_dir=run_dir), agent, resume)

    assert result.status == "ready", result
    assert agent.counts() == {"implement-plan": 2}, agent.counts()
