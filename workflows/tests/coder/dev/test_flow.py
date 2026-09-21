"""End-to-end tests for the `dev` flow — the gates, the layer loop, the operator."""
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
from pydantic import ValidationError
from workhorse.artifacts import ArtifactWriter
from workhorse.pyflow import driver as pyflow_driver
from workhorse.pyflow.driver import read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import parse_checkpoint

from workhorse_workflows.coder.dev import nodes
from workhorse_workflows.coder.dev.flow import Dev
from workhorse_workflows.coder.shared.schemas.dev import PlanResult
from workhorse_workflows.coder.shared import story_status
from workhorse_workflows.coder.shared.dev import (
    plan_document,
    plan_summary,
    read_operator_context,
    record_plan,
    resolve_impl_context,
    run_gate,
)

STORY = "STORY-1"
EPIC = "EPIC-1"
SPEC_REL = f"docs/specs/{STORY}"
STORY_REL = f"docs/epics/{EPIC}/stories/{STORY}"
CONTEXT_REL = f"{STORY_REL}/context.md"

ESCALATION_NOTE = (
    "STATUS: AWAITING_OPERATOR\n\n"
    "Tried the staging bucket and the fixture; neither exists.\n"
    "Please confirm which bucket this story targets.\n"
)

RESOLVER_TRIED = (
    "listed both buckets with the workspace credentials — neither is reachable",
    "grepped the epic and the plan for a bucket name — nothing names one",
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

- **Status**: Not started
"""

SERVICES: list[dict[str, Any]] = [
    {
        "repo": "api",
        "path": ".",
        "type": "go",
        "plan_file": "plan-api.md",
    },
    {
        "repo": "web",
        "path": ".",
        "type": "react-router",
        "plan_file": "plan-web.md",
    },
]

GHOST: list[dict[str, Any]] = [
    {"repo": "ghost", "path": ".", "type": "go", "plan_file": "plan-api.md"}
]




@pytest.fixture
def docs(repo: Path, write: Callable[[Path, str], Path]) -> Path:
    """The docs repo, carrying one epic and one authored story under it."""
    write(repo / "docs" / "epics" / EPIC / "epic.md", EPIC_MD)
    write(repo / STORY_REL / "story.md", STORY_MD)
    return repo


@pytest.fixture
def workspace(
    tmp_path: Path,
    docs: Path,
    git: Callable[..., subprocess.CompletedProcess],
    write: Callable[[Path, str], Path],
    ambient: dict[str, str],
) -> dict[str, Path]:
    """Two real git repos and the VSCode workspace file that names them, in order."""
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
    ambient["workspace_file"] = str(root / "acme.code-workspace")
    return repos


@pytest.fixture
def lint_gate(
    docs: Path, workspace: dict[str, Path], write: Callable[[Path, str], Path]
) -> Path:
    """Make `api` adopt the lint gate, failing until a marker file exists."""
    write(docs / "agents.yml", "lint:\n  api: sh lint.sh\n")
    script = write(workspace["api"] / "lint.sh", "test -f .lint-ok\n")
    return script.parent / ".lint-ok"




class _Agent:
    """A scripted stand-in for the flow's prompts, writing what each claims to write."""

    def __init__(
        self,
        docs: Path,
        *,
        services: list[dict[str, Any]] | None = None,
        blocked: int = 0,
        resolver_answers: bool = False,
        bad_paths: int = 0,
        fix_gate: Path | None = None,
        explode: set[str] | None = None,
        impl_blocked: int = 0,
        stamps_status: int = 0,
        repo_relative_plans: bool = False,
        unwritten_plans: int = 0,
    ) -> None:
        self.docs = docs
        self.services = services if services is not None else SERVICES
        self.blocked = blocked
        self.resolver_answers = resolver_answers
        self.bad_paths = bad_paths
        self.fix_gate = fix_gate
        self.explode = explode or set()
        self.impl_blocked = impl_blocked
        self.stamps_status = stamps_status
        self.repo_relative_plans = repo_relative_plans
        self.unwritten_plans = unwritten_plans
        self.calls: list[str] = []
        self.args: list[dict[str, Any]] = []
        self.plans = 0
        self.impls = 0


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


    def _plan_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return self._plan(data)

    def _repair_plan_paths(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return self._plan(data)

    def _replan_with_answer(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return self._plan(data)

    def _plan(self, data: dict[str, Any]) -> dict[str, Any]:
        """Write the plan files every planning prompt is told to, then report the structure."""
        self.plans += 1
        services = GHOST if self.plans <= self.bad_paths else self.services
        spec = Path(data["spec_dir"])
        spec.mkdir(parents=True, exist_ok=True)
        if self.plans > self.unwritten_plans:
            for svc in services:
                (spec / svc["plan_file"]).write_text(
                    f"# Plan for {svc['repo']}::{svc['path']}\n",
                    encoding="utf-8",
                )
        if self.repo_relative_plans:
            services = [
                {**svc, "plan_file": (spec / svc["plan_file"]).relative_to(self.docs).as_posix()}
                for svc in services
            ]
        structure = {
            "services": services,
            "implementation_order": [f"{s['repo']}::{s['path']}" for s in services],
        }
        if self.plans <= self.blocked:
            return {"status": "blocked", "summary": "the prod bucket may not exist", **structure}
        return {"status": "done", "summary": f"plan {self.plans}", **structure}

    def _resolve_operator(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if self.resolver_answers:
            (self.docs / CONTEXT_REL).write_text(
                "STATUS: ANSWERED\nSCOPE: story\n\nUse the staging bucket.\n",
                encoding="utf-8",
            )
            return {
                "decision": "answered",
                "summary": "the bucket is named in the epic's acceptance criteria",
                "grounded": ["docs/epics/EPIC-1/epic.md:12 — 'all writes go to the staging bucket'"],
                "record": "which-bucket-do-writes-go-to",
            }
        self._escalate()
        return {
            "decision": "escalated",
            "summary": "needs a product call",
            "tried": list(RESOLVER_TRIED),
        }

    def _implement_plan(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        self.impls += 1
        if self.impls <= self.impl_blocked:
            return {"status": "blocked", "notes": "the plan names a migration nobody has run"}
        if self.impls <= self.stamps_status:
            _set_status(self.docs, "QA passed")
        return {"status": "done", "notes": f"implemented {data['service_path']}"}

    def _dev_fix(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if data["report"]["source"] == "story status":
            _set_status(self.docs, "Not started")
            return {"status": "fixed", "notes": "put the status line back"}
        if self.fix_gate is None:
            return {"status": "failed", "notes": "the finding is in vendored code"}
        self.fix_gate.write_text("", encoding="utf-8")
        return {"status": "fixed", "notes": "satisfied the gate"}


    def _escalate(self) -> None:
        """What an *escalating* resolver leaves behind — it does not write nothing."""
        (self.docs / CONTEXT_REL).write_text(ESCALATION_NOTE, encoding="utf-8")


def _set_status(docs: Path, status: str) -> None:
    """Rewrite the story's `- **Status**:` line, the way a turn editing the file would."""
    story = docs / STORY_REL / "story.md"
    lines = story.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.startswith("- **Status**:"):
            lines[i] = f"- **Status**: {status}"
            break
    story.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _answers(docs: Path, seen: list[str], *, scope: str = "story") -> Callable[..., None]:
    """A stand-in for the human an `Await` is waiting on."""

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
        "implement-plan": 2,
    }, agent.counts()

    for name in ("plan-api.md", "plan-web.md"):
        assert (docs / SPEC_REL / name).read_text().startswith("---\n"), name

    assert _branch_of(workspace["api"]) == STORY
    assert _branch_of(workspace["web"]) == STORY

    implemented = [
        (a["service_path"], a["plan_file"]) for a in agent.args_for("implement-plan")
    ]
    assert implemented == [(".", "plan-api.md"), (".", "plan-web.md")], implemented
    assert [a["service_type"] for a in agent.args_for("implement-plan")] == [
        "go",
        "react-router",
    ]


def test_the_implement_turn_is_handed_the_two_values_its_prompt_reads(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`implement-plan.md` reads two values the YAML node never passed."""
    agent = _Agent(docs)
    run_env = env()

    drive_flow(Dev(story=STORY), run_env, agent)

    first = agent.args_for("implement-plan")[0]
    impl = _output(run_env, resolve_impl_context)
    assert first["qa_run_plan"] == impl["qa_run_plan"]
    assert first["verification_setup"] == impl["verification_setup"]


def test_a_plan_written_before_the_rename_still_carries_its_verification_setup() -> None:
    """`verification_setup` was `qa_stack`, and old documents are still on disk."""
    legacy = {"services": [], "qa_stack": {"profile": "seeded", "fixtures": ["acme.json"]}}

    assert plan_document(legacy, {})["verification_setup"] == {
        "profile": "seeded",
        "fixtures": ["acme.json"],
    }


def test_the_new_spelling_wins_when_a_document_somehow_has_both() -> None:
    """Nothing writes both, and the reader still has to pick one deterministically."""
    both = {"verification_setup": {"profile": "new"}, "qa_stack": {"profile": "old"}}

    assert plan_document(both, {})["verification_setup"] == {"profile": "new"}


def test_a_checkpointed_plan_result_reads_back_under_the_old_field_name() -> None:
    """The other half of the rename: a resume validates a `PlanResult` written before it."""
    legacy = PlanResult.model_validate({"status": "done", "qa_stack": {"profile": "seeded"}})

    assert legacy.verification_setup == {"profile": "seeded"}
    assert PlanResult(status="done", verification_setup={"profile": "new"}).verification_setup == {
        "profile": "new"
    }


def test_the_fixtures_nested_in_the_setup_block_become_the_typed_list() -> None:
    """The planner writes one `## Verification setup` section, and it always did."""
    plan = {
        "status": "done",
        "verification_setup": {"profile": "seeded", "fixtures": [{"name": "signed_in"}]},
    }

    result = PlanResult.model_validate(plan)

    assert [f.name for f in result.fixtures] == ["signed_in"]
    assert result.verification_setup["profile"] == "seeded"


def test_a_bare_string_fixture_is_the_fixture_it_names() -> None:
    """The same lift `shared_packages` gets, and for the same reason: `"signed_in"` says exactly what `{"name": "signed_in"}` says, and rejecting it spends a rework lap teaching a planner punctuation."""
    result = PlanResult.model_validate(
        {"status": "done", "qa_stack": {"fixtures": ["signed_in", "seeded_db"]}}
    )

    assert [(f.name, f.provides) for f in result.fixtures] == [
        ("signed_in", ""),
        ("seeded_db", ""),
    ]


def test_a_bare_sentence_is_lifted_as_prose_rather_than_as_a_name() -> None:
    """The same lift, applied to what the corpus actually contains."""
    result = PlanResult.model_validate(
        {
            "status": "done",
            "fixtures": ["seeded_accounts", "an empty desk (DELETE /api/claims)"],
        }
    )

    assert [(f.name, f.provides) for f in result.fixtures] == [
        ("seeded_accounts", ""),
        ("", "an empty desk (DELETE /api/claims)"),
    ]


def test_an_explicit_fixture_list_is_not_overwritten_by_the_nested_one() -> None:
    """A planner that filled in the typed field said what it meant there; the lift is a fallback for the documents that predate it, not a second opinion about them."""
    result = PlanResult.model_validate(
        {
            "status": "done",
            "fixtures": [{"name": "typed", "provides": "an account"}],
            "verification_setup": {"fixtures": ["nested"]},
        }
    )

    assert [(f.name, f.provides) for f in result.fixtures] == [("typed", "an account")]


def test_the_projection_carries_the_fixtures_under_either_spelling() -> None:
    """`plan-context.json` is read by lanes outside the run that produced it, including ones resuming against a document written before the field existed."""
    nested = {"services": [], "qa_stack": {"fixtures": ["seeded_db"]}}
    typed = {"services": [], "fixtures": [{"name": "signed_in", "provides": "a bearer token"}]}

    assert plan_document(nested, {})["fixtures"] == [{"name": "seeded_db", "provides": ""}]
    assert plan_document(typed, {})["fixtures"] == [
        {"name": "signed_in", "provides": "a bearer token"}
    ]


def test_a_nameless_arrangement_is_kept_and_an_empty_entry_is_dropped() -> None:
    """A nameless fixture is nothing `qa.fixture()` can resolve — but it is still something the story needs standing up, and dropping it told the QA planner the story had declared nothing at all."""
    plan = {
        "services": [],
        "fixtures": [{"provides": "an account"}, "signed_in", {"name": "", "provides": ""}],
    }

    assert plan_document(plan, {})["fixtures"] == [
        {"name": "", "provides": "an account"},
        {"name": "signed_in", "provides": ""},
    ]


def test_a_sentence_in_the_fixture_list_is_an_arrangement_and_not_a_name() -> None:
    """Every frozen story in the benchmark corpus describes its arrangements in prose here, and reading one as a name is not harmless: the QA planner was handed a "declared fixture" called `an empty desk (DELETE /api/claims)`, found no such declaration in `agents.yml`, and rewrote the plan *and* the registry to invent it — four agent turns on a round that had been costing zero."""
    plan = {
        "services": [],
        "fixtures": ["seeded_accounts", "an empty desk (DELETE /api/claims)"],
    }

    assert plan_document(plan, {})["fixtures"] == [
        {"name": "seeded_accounts", "provides": ""},
        {"name": "", "provides": "an empty desk (DELETE /api/claims)"},
    ]


def test_the_summary_says_the_names_apart_from_the_arrangements(tmp_path: Path) -> None:
    """The two halves of a fixture list are acted on differently and so are said apart."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    spec = tmp_path / SPEC_REL
    spec.mkdir(parents=True)
    (spec / "plan-context.json").write_text(
        json.dumps(
            {
                "services": [{"repo": "api", "path": ".", "type": "go", "plan_file": "plan.md"}],
                "fixtures": [
                    {"name": "seeded_accounts", "provides": "three funded accounts"},
                    {"name": "", "provides": "an empty desk"},
                ],
            }
        ),
        encoding="utf-8",
    )

    text = plan_summary(
        logging.getLogger(__name__), spec_dir=SPEC_REL, repo_dir=str(tmp_path)
    ).text

    assert "Declared fixtures: seeded_accounts (three funded accounts)" in text
    assert "Arrangements this story described without declaring: an empty desk" in text


def test_a_bare_string_shared_package_is_the_directory_it_names() -> None:
    """`shared_packages` means "non-service directories the plan changes", so a planner that emits `"docs"` said exactly what `{"path": "docs"}` says — one did, and the string's shape alone ended a four-hour run."""
    plan = PlanResult.model_validate(
        {"status": "done", "shared_packages": ["docs", {"path": "libs/core"}]}
    )

    assert [pkg.path for pkg in plan.shared_packages] == ["docs", "libs/core"]

    with pytest.raises(ValidationError):
        PlanResult.model_validate({"status": "done", "services": ["docs"]})


def test_an_unauthored_story_is_refused_before_anything_is_planned(
    docs: Path,
    workspace: dict[str, Path],
    write: Callable[[Path, str], Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A story ostler knows and reports unauthored fails in `setup`, not in review."""
    write(docs / STORY_REL / "story.md", "---\ntype: story\n---\n\n# Story One\n")
    agent = _Agent(docs)

    with pytest.raises(Exception, match="not authored"):
        drive_flow(Dev(story=STORY), env(), agent)

    assert agent.calls == []


def test_a_slug_that_resolves_to_no_file_is_refused_before_anything_is_planned(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The other half of the authored gate: the slug resolved, but to a file nobody wrote."""
    agent = _Agent(docs)

    with pytest.raises(Exception, match="not readable"):
        drive_flow(Dev(story="ghost-story", epic=EPIC), env(), agent)

    assert agent.calls == []


def test_no_slug_at_all_is_refused_before_anything_is_planned(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`prepare_story` with nothing to resolve returns blank paths, and blank is not a story."""
    agent = _Agent(docs)

    with pytest.raises(Exception, match="no story path"):
        drive_flow(Dev(), env(), agent)

    assert agent.calls == []




def test_validate_is_not_a_reserved_pydantic_name() -> None:
    """The path gate's state is `validate_paths`, and the name is load-bearing."""
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
    assert agent.counts()["repair-plan-paths"] == 1, agent.counts()
    assert "ghost" in agent.args_for("repair-plan-paths")[0]["review_notes"]
    assert _output(run_env, record_plan)["status"] == "valid"


def test_a_plan_whose_files_were_never_written_reworks_the_plan(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A structure naming plan files the turn did not write is a plan defect, not a prompt."""
    agent = _Agent(docs, unwritten_plans=1)
    run_env = env()

    result = drive_flow(Dev(story=STORY), run_env, agent)

    assert result.status == "ready", result
    assert agent.counts()["repair-plan-paths"] == 1, agent.counts()
    notes = agent.args_for("repair-plan-paths")[0]["review_notes"]
    assert "plan-api.md" in notes and "not readable" in notes, notes
    assert _output(run_env, record_plan)["status"] == "valid"


def test_a_repo_relative_plan_file_costs_no_refine_lap(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The two readings of `plan_file` name the same file, so neither is a plan defect."""
    agent = _Agent(docs, repo_relative_plans=True)
    run_env = env()

    result = drive_flow(Dev(story=STORY), run_env, agent)

    assert result.status == "ready", result
    assert agent.counts()["repair-plan-paths"] == 0, agent.counts()
    assert _output(run_env, record_plan)["status"] == "valid"
    written = json.loads((docs / SPEC_REL / "plan-context.json").read_text())
    assert [svc["plan_file"] for svc in written["services"]] == ["plan-api.md", "plan-web.md"]


def test_a_plan_file_outside_the_spec_dir_is_still_an_error(
    tmp_path: Path,
    write: Callable[[Path, str], Path],
) -> None:
    """The repair is narrow on purpose: only a path that lands *inside* the spec dir."""
    root = tmp_path / "book"
    spec = root / "docs" / "specs" / "thing"
    write(spec / "plan-api.md", "# in\n")
    write(root / "elsewhere" / "plan-api.md", "# out\n")
    plan = {
        "services": [
            {"repo": "api", "path": ".", "plan_file": "elsewhere/plan-api.md"},
            {"repo": "api", "path": ".", "plan_file": "docs/specs/thing/plan-api.md"},
            {"repo": "api", "path": ".", "plan_file": "nowhere/plan-api.md"},
        ]
    }

    doc = plan_document(plan, {}, spec, root)

    assert [svc["plan_file"] for svc in doc["services"]] == [
        "elsewhere/plan-api.md",
        "plan-api.md",
        "nowhere/plan-api.md",
    ]


def test_an_unfixable_plan_exhausts_the_budget_and_reaches_the_operator(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Three refine passes that do not fix it escalate rather than looping forever."""
    agent = _Agent(docs, bad_paths=4)
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(docs, seen)):
        result = drive_flow(Dev(story=STORY), env(), agent)

    assert result.status == "ready", result
    assert agent.counts()["repair-plan-paths"] == 3, agent.counts()
    assert agent.counts()["replan-with-answer"] == 1, agent.counts()
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    assert agent.args_for("resolve-operator")[0]["block_kind"] == "plan"


def test_a_service_path_nobody_can_repair_never_gives_up(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wider of the two operator cycles never dead-ends, even once the resolver is spent."""
    monkeypatch.setenv("WORKHORSE_MAX_TRANSITIONS", "180")
    agent = _Agent(docs, bad_paths=99)
    seen: list[str] = []

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text(encoding="utf-8"))
        if len(seen) >= nodes.MAX_PLAN_BLOCKS + 2:
            agent.bad_paths = 0
        path.write_text(
            "STATUS: ANSWERED\nSCOPE: story\n\nUse the staging bucket.\n", encoding="utf-8"
        )

    with patch.object(pyflow_driver, "wait_for_answer", answered):
        result = drive_flow(Dev(story=STORY), env(), agent)

    assert result.status == "ready", result
    assert agent.counts()["resolve-operator"] == nodes.MAX_PLAN_BLOCKS, agent.counts()
    assert len(seen) == nodes.MAX_PLAN_BLOCKS + 2, seen
    assert agent.counts()["implement-plan"] > 0, agent.counts()




def test_a_resolver_that_grounds_its_answer_settles_the_block_without_a_person(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The `answered` arm: a question the documents already settle costs nobody a round trip."""
    agent = _Agent(docs, blocked=1, resolver_answers=True)

    def never(path: Path, **kwargs: Any) -> None:
        raise AssertionError(f"a grounded answer must not park on {path}")

    with patch.object(pyflow_driver, "wait_for_answer", never):
        result = drive_flow(Dev(story=STORY), env(), agent)

    assert result.status == "ready", result
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    assert "staging bucket" in agent.args_for("replan-with-answer")[0]["operator_context"]
    assert "STATUS: CONSUMED" in (docs / CONTEXT_REL).read_text()


def test_an_answered_block_still_spends_the_resolver_budget(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An answer that does not clear the block walks toward a person, it does not lap forever."""
    monkeypatch.setenv("WORKHORSE_MAX_TRANSITIONS", "180")
    agent = _Agent(docs, blocked=99, resolver_answers=True)
    seen: list[str] = []

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text(encoding="utf-8"))
        agent.blocked = 0
        path.write_text(
            "STATUS: ANSWERED\nSCOPE: story\n\nUse the staging bucket.\n", encoding="utf-8"
        )

    with patch.object(pyflow_driver, "wait_for_answer", answered):
        result = drive_flow(Dev(story=STORY), env(), agent)

    assert result.status == "ready", result
    assert agent.counts()["resolve-operator"] == nodes.MAX_PLAN_BLOCKS, agent.counts()
    assert len(seen) == 1, seen


def test_a_blocked_plan_goes_to_the_auto_operator_and_is_reworked(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`operator_mode=auto` stands an agent in for the human, and consumes its answer."""
    agent = _Agent(docs, blocked=1)
    run_env = env()
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(docs, seen)):
        result = drive_flow(Dev(story=STORY), run_env, agent)

    assert result.status == "ready", result
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    assert agent.counts()["replan-with-answer"] == 1, agent.counts()
    assert "staging bucket" in agent.args_for("replan-with-answer")[0]["operator_context"]
    assert "STATUS: CONSUMED" in (docs / CONTEXT_REL).read_text()


def test_an_epic_scoped_answer_leaves_the_flow_to_be_replanned(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`SCOPE: epic` means the epic premise was wrong, not this story's plan."""
    agent = _Agent(docs, blocked=1)
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(docs, seen, scope="epic")):
        result = drive_flow(Dev(story=STORY), env(), agent)

    assert result.status == "replan", result
    assert "staging bucket" in result.operator_notes
    assert agent.counts()["implement-plan"] == 0, agent.counts()


@pytest.mark.parametrize("operator_mode", ["human", "operator"])
def test_human_operator_modes_wait_on_the_story_context_file(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    operator_mode: str,
) -> None:
    """Canonical `human` and legacy `operator` skip the resolver and block on the file."""
    seen: list[str] = []
    agent = _Agent(docs, blocked=1)

    with patch.object(pyflow_driver, "wait_for_answer", _answers(docs, seen)):
        result = drive_flow(Dev(story=STORY, operator_mode=operator_mode), env(), agent)

    assert result.status == "ready", result
    assert agent.counts()["resolve-operator"] == 0, agent.counts()
    assert len(seen) == 1 and "the prod bucket may not exist" in seen[0], seen


def test_an_escalating_resolver_leaves_its_note_for_the_human(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The escalated arm waits on the file without rewriting it."""
    seen: list[str] = []
    agent = _Agent(docs, blocked=1)

    with patch.object(pyflow_driver, "wait_for_answer", _answers(docs, seen)):
        result = drive_flow(Dev(story=STORY), env(), agent)

    assert result.status == "ready", result
    (gate,) = seen
    assert "**Escalation #1 " in gate, gate
    assert all(line in gate for line in RESOLVER_TRIED), gate
    assert ESCALATION_NOTE.strip() in gate, gate


def test_an_implementation_turn_that_says_it_cannot_reaches_the_operator(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The lane's root-cause bug, from the outside."""
    agent = _Agent(docs, impl_blocked=1)
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(docs, seen)):
        result = drive_flow(Dev(story=STORY), env(), agent)

    assert result.status == "ready", result
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    (gate,) = seen
    assert "the plan names a migration nobody has run" in gate, gate
    retried = agent.args_for("implement-plan")[1]
    assert "staging bucket" in retried["operator_context"], retried


def test_an_implementation_block_in_human_mode_skips_the_resolver(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Same gate, no investigation — `human` mode routes every block straight to the file."""
    agent = _Agent(docs, impl_blocked=1)
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(docs, seen)):
        result = drive_flow(Dev(story=STORY, operator_mode="human"), env(), agent)

    assert result.status == "ready", result
    assert agent.counts()["resolve-operator"] == 0, agent.counts()
    assert len(seen) == 1 and "no auto-resolver ran" in seen[0], seen


def test_a_plan_no_operator_can_unblock_never_gives_up_either(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The tight operator cycle: a refine that re-raises the block keeps escalating, not failing."""
    monkeypatch.setenv("WORKHORSE_MAX_TRANSITIONS", "180")
    agent = _Agent(docs, blocked=99)
    seen: list[str] = []

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text(encoding="utf-8"))
        if len(seen) >= nodes.MAX_PLAN_BLOCKS + 2:
            agent.blocked = 0
        path.write_text(
            "STATUS: ANSWERED\nSCOPE: story\n\nUse the staging bucket.\n", encoding="utf-8"
        )

    with patch.object(pyflow_driver, "wait_for_answer", answered):
        result = drive_flow(Dev(story=STORY), env(), agent)

    assert result.status == "ready", result
    assert agent.counts()["resolve-operator"] == nodes.MAX_PLAN_BLOCKS, agent.counts()
    assert len(seen) == nodes.MAX_PLAN_BLOCKS + 2, seen
    assert agent.counts()["implement-plan"] > 0, agent.counts()


def test_human_operator_mode_never_gives_up_either(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`operator_mode=human` skips the resolver entirely, and has no bound of its own either."""
    monkeypatch.setenv("WORKHORSE_MAX_TRANSITIONS", "180")
    seen: list[str] = []
    agent = _Agent(docs, blocked=99)

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text(encoding="utf-8"))
        if len(seen) >= nodes.MAX_PLAN_BLOCKS + 2:
            agent.blocked = 0
        path.write_text(
            "STATUS: ANSWERED\nSCOPE: story\n\nUse the staging bucket.\n", encoding="utf-8"
        )

    with patch.object(pyflow_driver, "wait_for_answer", answered):
        result = drive_flow(Dev(story=STORY, operator_mode="human"), env(), agent)

    assert result.status == "ready", result
    assert agent.counts()["resolve-operator"] == 0, agent.counts()
    assert len(seen) == nodes.MAX_PLAN_BLOCKS + 2, seen


def test_an_unanswered_context_file_is_not_treated_as_an_answer(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    logger: Any,
) -> None:
    """`read_operator_context` reports nothing answered when the file is not there."""
    answer = read_operator_context(logger, str(docs / STORY_REL / "story.md"))

    assert answer.answered is False
    assert answer.scope == "story"




def test_the_gate_lane_repairs_and_re_runs_until_clean(
    docs: Path,
    workspace: dict[str, Path],
    lint_gate: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A dirty layer is repaired and re-gated; the second run is genuinely clean."""
    agent = _Agent(docs, fix_gate=lint_gate)
    run_env = env()

    result = drive_flow(Dev(story=STORY), run_env, agent)

    assert result.status == "ready", result
    assert agent.counts()["dev-fix"] == 1, agent.counts()
    assert lint_gate.is_file(), "the fixer did not write what the gate checks for"
    assert _output(run_env, run_gate)["status"] == "skipped"
    report = agent.args_for("dev-fix")[0]["report"]
    assert report["source"] == "lint", report
    assert report["command"] == "sh lint.sh", report
    assert report["cwd"] == str(workspace["api"]), report


def test_a_turn_that_stamps_the_story_finished_is_sent_back(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The Status line is a machine-parsed shape, so a gate holds the turn to it."""
    agent = _Agent(docs, stamps_status=1)
    run_env = env()

    result = drive_flow(Dev(story=STORY), run_env, agent)

    assert result.status == "ready", result
    assert agent.counts()["dev-fix"] == 1, agent.counts()
    report = agent.args_for("dev-fix")[0]["report"]
    assert report["source"] == "story status", report
    assert "QA passed" in report["findings"][0]["issue"], report
    assert report["findings"][0]["target"].endswith("story.md"), report
    story_md = docs / STORY_REL / "story.md"
    assert story_status.current(docs, STORY, epic=EPIC, story_path=str(story_md)) == (
        "Not started"
    )


def test_a_gate_no_repair_lap_can_satisfy_never_gives_up_either(
    docs: Path,
    workspace: dict[str, Path],
    lint_gate: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A spent repair budget is a block, not a give-up."""
    monkeypatch.setenv("WORKHORSE_MAX_TRANSITIONS", "240")
    monkeypatch.setattr(nodes, "MAX_FIX_LAPS", 2)
    agent = _Agent(docs, fix_gate=None)
    seen: list[str] = []

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text(encoding="utf-8"))
        if len(seen) >= 2:
            lint_gate.write_text("", encoding="utf-8")
        path.write_text(
            "STATUS: ANSWERED\nSCOPE: story\n\nVendored code is exempt.\n", encoding="utf-8"
        )

    with patch.object(pyflow_driver, "wait_for_answer", answered):
        result = drive_flow(Dev(story=STORY), env(), agent)

    assert result.status == "ready", result
    assert agent.counts()["dev-fix"] == 4, agent.counts()
    assert len(seen) == 2, seen




def test_a_run_killed_mid_implement_resumes_on_that_layer(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The checkpoint is written before a state runs, so the layer cursor survives the kill."""
    run_env = env()
    run_dir = run_env.writer.run_dir

    with pytest.raises(RuntimeError, match="killed during implement-plan"):
        drive_flow(Dev(story=STORY), run_env, _Agent(docs, explode={"implement-plan"}))

    checkpoint = parse_checkpoint((run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    resume = read_resume(checkpoint)
    assert resume.state == "implement", resume
    assert resume.flow == "Dev", resume
    assert resume.params == {
        "index": 0,
        "lap": {"fix_lap": 0, "session_turns": 1, "digest": ""},
    }, resume.params

    agent = _Agent(docs)
    result = drive_flow(Dev(**resume.inputs), env(run_dir=run_dir), agent, resume)

    assert result.status == "ready", result
    assert agent.counts() == {"implement-plan": 2}, agent.counts()
