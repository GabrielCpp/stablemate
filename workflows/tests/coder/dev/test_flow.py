"""End-to-end tests for the `dev` flow — the gates, the layer loop, the operator.

Several YAML nodes collapsed into states holding the loops that share them — the path gate
and the per-layer implement/gates/fix loop. What is worth testing is which arm each verdict
takes and what makes each loop terminate, so the tests are organised by gate rather than by
node.

**There are no seams here beyond the agent turn.** Every deterministic node runs for real:
the story is a real authored story in a real docs repo, the workspace is two real git repos
named by a real `.code-workspace` file, `stamp_specs` really stamps the plan files ostler
then reads back, `branch_code_repos` really moves both repos onto the story branch, and
`run_gate` really shells out to the command `agents.yml` names. That is what makes the port's
parity claim checkable rather than asserted — the flow is driven against the same artifacts
the YAML engine drove against, and the same files are on disk afterwards.

The scripted agent is scripted the way `surveyor`'s is: it dispatches on the prompt's
filename, which is the same key the engine derives its node id from, and every handler leaves
behind the artifacts its reply claims to have written — the plan turn writes
the per-service plan files and returns the structure Python projects, the resolver
writes the operator's answer into `context.md`, the lint fixer writes the file that makes the linter pass. A handler that
only returned a status would be testing the state machine against a fiction.
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
from pydantic import ValidationError
from workhorse.artifacts import ArtifactWriter
from workhorse.pyflow import driver as pyflow_driver
from workhorse.pyflow.driver import read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import parse_checkpoint

from workhorse_workflows.coder.dev import nodes
from workhorse_workflows.coder.dev.flow import Dev
from workhorse_workflows.coder.shared.schemas.dev import PlanResult
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

#: What an escalating resolver writes into `context.md` before it hands the block over —
#: the shape `dev/prompts/resolve-operator.md` mandates for the escalated arm.
ESCALATION_NOTE = (
    "STATUS: AWAITING_OPERATOR\n\n"
    "Tried the staging bucket and the fixture; neither exists.\n"
    "Please confirm which bucket this story targets.\n"
)

#: What that resolver reports it ruled out, which the composed gate publishes verbatim.
RESOLVER_TRIED = (
    "listed both buckets with the workspace credentials — neither is reachable",
    "grepped the epic and the plan for a bucket name — nothing names one",
)

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
#: filled and `Dependencies`, `Fixtures` and `Implementation Status` present. A scaffold with empty sections fails
#: `prepare_story`, which is the gate `test_an_unauthored_story_is_refused` drives.
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

#: The same plan naming a repo the workspace does not carry. `record_plan` rejects
#: it on the workspace lookup, which is the one failure mode no blind refine pass can repair
#: by luck — the path gate's escalation arm needs an error that stays an error.
GHOST: list[dict[str, Any]] = [
    {"repo": "ghost", "path": ".", "type": "go", "plan_file": "plan-api.md", "skills": []}
]


# --------------------------------------------------------------------------- fixtures


@pytest.fixture
def docs(repo: Path, write: Callable[[Path, str], Path]) -> Path:
    """The docs repo, carrying one epic and one authored story under it.

    `repo` is the checkout every coder test is stood in; what is added here is the
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
    ambient: dict[str, str],
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
    ambient["workspace_file"] = str(root / "acme.code-workspace")
    return repos


@pytest.fixture
def lint_gate(
    docs: Path, workspace: dict[str, Path], write: Callable[[Path, str], Path]
) -> Path:
    """Make `api` adopt the lint gate, failing until a marker file exists.

    `run_gate` resolves its command from the orchestrating repo's `agents.yml` before
    falling back to `make lint`, and keys the map by the service name and then by the cwd's
    basename — `api` here is the second. The script is the whole gate: it fails while the
    marker is absent, so the `dev-fix` turn has something real to fix and the loop's exit
    is a genuinely clean lint rather than a scripted claim of one.

    Returns the marker path so the lint-fixer handler can create it.
    """
    write(docs / "agents.yml", "lint:\n  api: sh lint.sh\n")
    script = write(workspace["api"] / "lint.sh", "test -f .lint-ok\n")
    return script.parent / ".lint-ok"


# --------------------------------------------------------------------------- the agent


class _Agent:
    """A scripted stand-in for the flow's prompts, writing what each claims to write.

    The knobs are the flow's branches: `blocked` makes the first N planning turns report a
    block, `bad_paths` makes the first N plan writes name a repo the workspace has not got,
    `fix_gate` decides whether the repair turn actually repairs anything, and `explode`
    raises on a named
    prompt — a run killed mid-turn. There is no `escalate` knob: the resolver never decides
    on the operator's behalf, so every resolved block investigates and then waits, the same
    way every time — and no `scope` knob either, since the answer's `SCOPE:` now comes from
    whatever stands in for the operator (`_answers`), not from the resolver the agent scripts.

    `impl_blocked` makes the first N implementation turns report they could not write the
    change.
    """

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
        repo_relative_plans: bool = False,
        unwritten_plans: int = 0,
    ) -> None:
        self.docs = docs
        self.services = services if services is not None else SERVICES
        self.blocked = blocked
        #: Whether the resolver settles the block itself rather than parking on it — the
        #: `answered` arm, which writes the operator's answer where a human would have.
        self.resolver_answers = resolver_answers
        self.bad_paths = bad_paths
        self.fix_gate = fix_gate
        self.explode = explode or set()
        self.impl_blocked = impl_blocked
        #: Report `plan_file` the other way it can legally be read — repo-relative, the form
        #: the turn was holding when it wrote the file — while writing the file itself
        #: exactly where it belongs.
        self.repo_relative_plans = repo_relative_plans
        #: The first N plan turns report a structure whose plan files they never wrote —
        #: the failure the path gate exists for.
        self.unwritten_plans = unwritten_plans
        self.calls: list[str] = []
        self.args: list[dict[str, Any]] = []
        self.plans = 0
        self.impls = 0

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
        """Write the plan files both planning prompts are told to, then report the structure.

        The plan files are written *untyped*: `stamp_specs` runs right after the first plan
        turn and is what gives them their OKF `type`, so writing them with front-matter
        already in place would hide whether the stamping step ran at all.
        """
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
        return {"status": "done", "notes": f"implemented {data['service_path']}"}

    def _dev_fix(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if self.fix_gate is None:
            return {"status": "failed", "notes": "the finding is in vendored code"}
        self.fix_gate.write_text("", encoding="utf-8")
        return {"status": "fixed", "notes": "satisfied the gate"}

    # -- what the resolver leaves behind ----------------------------------

    def _escalate(self) -> None:
        """What an *escalating* resolver leaves behind — it does not write nothing.

        `dev/prompts/resolve-operator.md` requires the escalated arm to write
        `STATUS: AWAITING_OPERATOR` into this same file, with what it tried and what the
        human must supply. Modelling that as "writes nothing" is what let the flow overwrite
        it unnoticed; see `test_an_escalating_resolver_leaves_its_note_for_the_human`.
        """
        (self.docs / CONTEXT_REL).write_text(ESCALATION_NOTE, encoding="utf-8")


def _answers(docs: Path, seen: list[str], *, scope: str = "story") -> Callable[..., None]:
    """A stand-in for the human an `Await` is waiting on.

    Patched over `wait_for_answer`, so it runs where the operator's edit would land: the
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
        "implement-plan": 2,
    }, agent.counts()

    # The plan files the turn wrote untyped are OKF Concepts afterwards: `stamp_specs` ran.
    for name in ("plan-api.md", "plan-web.md"):
        assert (docs / SPEC_REL / name).read_text().startswith("---\n"), name

    # Both code repos moved onto the story branch — `branch_code_repos` ran for real.
    assert _branch_of(workspace["api"]) == STORY
    assert _branch_of(workspace["web"]) == STORY

    # The layers were dispatched in the plan's declared order, each with its own plan file.
    implemented = [
        (a["service_path"], a["plan_file"]) for a in agent.args_for("implement-plan")
    ]
    assert implemented == [(".", "plan-api.md"), (".", "plan-web.md")], implemented
    assert [a["service_type"] for a in agent.args_for("implement-plan")] == [
        "go",
        "react-router",
    ]


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
    assert first["verification_setup"] == impl["verification_setup"]


def test_a_plan_written_before_the_rename_still_carries_its_verification_setup() -> None:
    """`verification_setup` was `qa_stack`, and old documents are still on disk.

    The rename took the field off its near-homograph with `qa-stack.yml`, which is a
    different document with a different schema. What it must not take with it is the
    fixture list out of a `plan-context.json` a resume reads back: `extra="ignore"` would
    drop the old key without a word, and QA would be handed a story it cannot stand up.
    """
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
    """The other half of the rename: a resume validates a `PlanResult` written before it.

    A checkpoint is not a document the reader can hand-tolerate — pydantic validates it,
    and `extra="ignore"` is what makes the resilience ladder soft. The alias is what stops
    that same setting from eating a real answer on the one turn that produced it.
    """
    legacy = PlanResult.model_validate({"status": "done", "qa_stack": {"profile": "seeded"}})

    assert legacy.verification_setup == {"profile": "seeded"}
    assert PlanResult(status="done", verification_setup={"profile": "new"}).verification_setup == {
        "profile": "new"
    }


def test_the_fixtures_nested_in_the_setup_block_become_the_typed_list() -> None:
    """The planner writes one `## Verification setup` section, and it always did.

    The typed field is not a second thing to write — it is the one part of that section a
    later lane *calls*, lifted out of the prose beside it so `qa.fixture()` gets the name
    the story wrote rather than a name a turn paraphrased out of a dumped object.
    """
    plan = {
        "status": "done",
        "verification_setup": {"profile": "seeded", "fixtures": [{"name": "signed_in"}]},
    }

    result = PlanResult.model_validate(plan)

    assert [f.name for f in result.fixtures] == ["signed_in"]
    # The prose is untouched: nothing typed here takes anything away from the QA turn.
    assert result.verification_setup["profile"] == "seeded"


def test_a_bare_string_fixture_is_the_fixture_it_names() -> None:
    """The same lift `shared_packages` gets, and for the same reason: `"signed_in"` says
    exactly what `{"name": "signed_in"}` says, and rejecting it spends a rework lap
    teaching a planner punctuation."""
    result = PlanResult.model_validate(
        {"status": "done", "qa_stack": {"fixtures": ["signed_in", "seeded_db"]}}
    )

    assert [(f.name, f.provides) for f in result.fixtures] == [
        ("signed_in", ""),
        ("seeded_db", ""),
    ]


def test_a_bare_sentence_is_lifted_as_prose_rather_than_as_a_name() -> None:
    """The same lift, applied to what the corpus actually contains.

    `qa.fixture()` takes a name exactly, so a name is a key or it is nothing. Lifting
    `"an empty desk (DELETE /api/claims)"` into the name slot handed the QA planner a
    declaration to look up, and the lane it could not find it in was `agents.yml`.
    """
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
    """A planner that filled in the typed field said what it meant there; the lift is a
    fallback for the documents that predate it, not a second opinion about them."""
    result = PlanResult.model_validate(
        {
            "status": "done",
            "fixtures": [{"name": "typed", "provides": "an account"}],
            "verification_setup": {"fixtures": ["nested"]},
        }
    )

    assert [(f.name, f.provides) for f in result.fixtures] == [("typed", "an account")]


def test_the_projection_carries_the_fixtures_under_either_spelling() -> None:
    """`plan-context.json` is read by lanes outside the run that produced it, including
    ones resuming against a document written before the field existed."""
    nested = {"services": [], "qa_stack": {"fixtures": ["seeded_db"]}}
    typed = {"services": [], "fixtures": [{"name": "signed_in", "provides": "a bearer token"}]}

    assert plan_document(nested, {})["fixtures"] == [{"name": "seeded_db", "provides": ""}]
    assert plan_document(typed, {})["fixtures"] == [
        {"name": "signed_in", "provides": "a bearer token"}
    ]


def test_a_nameless_arrangement_is_kept_and_an_empty_entry_is_dropped() -> None:
    """A nameless fixture is nothing `qa.fixture()` can resolve — but it is still something
    the story needs standing up, and dropping it told the QA planner the story had declared
    nothing at all. It is carried as prose instead, apart from the names; only an entry that
    says neither is dropped, because that one carries no instruction to anybody."""
    plan = {
        "services": [],
        "fixtures": [{"provides": "an account"}, "signed_in", {"name": "", "provides": ""}],
    }

    assert plan_document(plan, {})["fixtures"] == [
        {"name": "", "provides": "an account"},
        {"name": "signed_in", "provides": ""},
    ]


def test_a_sentence_in_the_fixture_list_is_an_arrangement_and_not_a_name() -> None:
    """Every frozen story in the benchmark corpus describes its arrangements in prose here,
    and reading one as a name is not harmless: the QA planner was handed a "declared fixture"
    called `an empty desk (DELETE /api/claims)`, found no such declaration in `agents.yml`,
    and rewrote the plan *and* the registry to invent it — four agent turns on a round that
    had been costing zero."""
    plan = {
        "services": [],
        "fixtures": ["seeded_accounts", "an empty desk (DELETE /api/claims)"],
    }

    assert plan_document(plan, {})["fixtures"] == [
        {"name": "seeded_accounts", "provides": ""},
        {"name": "", "provides": "an empty desk (DELETE /api/claims)"},
    ]


def test_the_summary_says_the_names_apart_from_the_arrangements(tmp_path: Path) -> None:
    """The two halves of a fixture list are acted on differently and so are said apart.

    A declared name is something the QA plan *calls*; an arrangement is something it has to
    build for itself. Rendered as one list they read as one instruction, and a QA turn that
    tried to call a sentence went looking for its declaration, did not find it, and set about
    writing one — into the plan and into `agents.yml` both.
    """
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
    """`shared_packages` means "non-service directories the plan changes", so a planner
    that emits `"docs"` said exactly what `{"path": "docs"}` says — one did, and the
    string's shape alone ended a four-hour run. The lift is scoped to that list:
    a bare string in `services` still under-specifies (repo, plan_file) and stays a
    validation error the ladder re-asks about.
    """
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
    """A story ostler knows and reports unauthored fails in `setup`, not in review.

    This is the gate that exists because an author run once produced 44 stubs and reported
    success. It is in `setup`, so the failure precedes the first agent turn entirely.
    """
    write(docs / STORY_REL / "story.md", "---\ntype: story\n---\n\n# Story One\n")
    agent = _Agent(docs)

    with pytest.raises(Exception, match="not authored"):
        drive_flow(Dev(story=STORY), env(), agent)

    assert agent.calls == []


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
    assert _output(run_env, record_plan)["status"] == "valid"


def test_a_plan_whose_files_were_never_written_reworks_the_plan(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A structure naming plan files the turn did not write is a plan defect, not a prompt.

    The implementer is handed the plan as content, so an unwritten file used to arrive as an
    empty string and the turn invented the work. It is the gate's now: one refine lap, and
    the second turn writes them.
    """
    agent = _Agent(docs, unwritten_plans=1)
    run_env = env()

    result = drive_flow(Dev(story=STORY), run_env, agent)

    assert result.status == "ready", result
    assert agent.counts()["refine-plan"] == 1, agent.counts()
    notes = agent.args_for("refine-plan")[0]["review_notes"]
    assert "plan-api.md" in notes and "not readable" in notes, notes
    assert _output(run_env, record_plan)["status"] == "valid"


def test_a_repo_relative_plan_file_costs_no_refine_lap(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The two readings of `plan_file` name the same file, so neither is a plan defect.

    `plan-story.md` asks for it relative to the spec dir, and the turn that fills it has
    just written `docs/specs/<story>/plan.md` — so it hands that string back about as often
    as the short one. Benchmark run `c1` spent a 203 s high-power `refine-plan` lap on the
    difference, and produced one string rewritten into another string for the same file.
    """
    agent = _Agent(docs, repo_relative_plans=True)
    run_env = env()

    result = drive_flow(Dev(story=STORY), run_env, agent)

    assert result.status == "ready", result
    assert agent.counts()["refine-plan"] == 0, agent.counts()
    assert _output(run_env, record_plan)["status"] == "valid"
    # Repaired on the way in, not tolerated at the check: every later reader of the
    # projection — `ostler artifact vet`, QA on a later run — sees the one spelling.
    written = json.loads((docs / SPEC_REL / "plan-context.json").read_text())
    assert [svc["plan_file"] for svc in written["services"]] == ["plan-api.md", "plan-web.md"]


def test_a_plan_file_outside_the_spec_dir_is_still_an_error(
    tmp_path: Path,
    write: Callable[[Path, str], Path],
) -> None:
    """The repair is narrow on purpose: only a path that lands *inside* the spec dir.

    A file that exists somewhere else entirely is not the same file under another notation,
    it is the wrong file — and passing it through verbatim is what keeps the downstream
    error naming what the planner actually wrote.
    """
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
    """Three refine passes that do not fix it escalate rather than looping forever.

    `MAX_VALIDATE_REWORKS` is 3, so the fourth validation is the one that escalates to the
    gate; the resolver investigates and parks, the operator answers, the plan is reworked
    with the answer in hand — the fifth write, and the first good one — and the restored
    budget takes it through the gate.
    """
    agent = _Agent(docs, bad_paths=4)
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(docs, seen)):
        result = drive_flow(Dev(story=STORY), env(), agent)

    assert result.status == "ready", result
    assert agent.counts()["refine-plan"] == 4, agent.counts()
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    assert agent.args_for("resolve-operator")[0]["block_kind"] == "plan"


def test_a_service_path_nobody_can_repair_never_gives_up(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wider of the two operator cycles never dead-ends, even once the resolver is spent.

    `read_operator` deliberately restores the path-validation budget — the YAML re-emitted
    `plan_rework_count: 0` and an operator answer really is a fresh licence to re-validate.
    But a repo the workspace has not got is not a thing an answer can conjure, so the block
    keeps recurring long after `MAX_PLAN_BLOCKS` resolver turns are spent. `_gate_plan`
    routes every trip past that cap straight to a human instead of raising — there is no
    further cap on how many times it may ask. Once "the operator" finally supplies a real
    fix, the run finishes normally rather than having given up on itself somewhere in the
    middle.
    """
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
    # The resolver only ever gets `MAX_PLAN_BLOCKS` turns; every later block still reaches a
    # human, which `seen` outgrowing that count proves without a resolver call to match it.
    assert agent.counts()["resolve-operator"] == nodes.MAX_PLAN_BLOCKS, agent.counts()
    assert len(seen) == nodes.MAX_PLAN_BLOCKS + 2, seen
    assert agent.counts()["implement-plan"] > 0, agent.counts()


# --------------------------------------------------------------------------- the operator


def test_a_resolver_that_grounds_its_answer_settles_the_block_without_a_person(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The `answered` arm: a question the documents already settle costs nobody a round trip.

    The resolver may only *apply* a decision somebody wrote down — see
    `coder/shared/resolution.py` — and when it can, it writes the same `context.md` a human
    would have and the flow rejoins at the same `read_operator`. Nothing waits, which is what
    patching `wait_for_answer` to fail proves: reaching it at all would mean the block parked.
    """
    agent = _Agent(docs, blocked=1, resolver_answers=True)

    def never(path: Path, **kwargs: Any) -> None:
        raise AssertionError(f"a grounded answer must not park on {path}")

    with patch.object(pyflow_driver, "wait_for_answer", never):
        result = drive_flow(Dev(story=STORY), env(), agent)

    assert result.status == "ready", result
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    # The answer reached the refiner exactly as a human's would have, and the marker was
    # flipped, so the next block re-arms instead of re-consuming this answer.
    assert "staging bucket" in agent.args_for("refine-plan")[0]["operator_context"]
    assert "STATUS: CONSUMED" in (docs / CONTEXT_REL).read_text()


def test_an_answered_block_still_spends_the_resolver_budget(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An answer that does not clear the block walks toward a person, it does not lap forever.

    This is the failure mode the answering arm introduces: the resolver keeps finding the
    same written rule, keeps applying it, and the plan keeps coming back blocked. Spending
    `plan_blocks` on the answering arm too is what makes the cycle terminate at a human
    rather than at the driver's transition budget.
    """
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
    """Canonical `human` and legacy `operator` skip the resolver and block on the file.

    The questions are written next to the story, which is where `await_operator.py` put them
    and where the operator answering is reading the story they are about.
    """
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
    """The escalated arm waits on the file without rewriting it.

    `Await` writes its `questions` with `write_text`, and the escalated arm waits on the very
    file the resolver has just written `STATUS: AWAITING_OPERATOR` into. Passing the block
    notes as the ask therefore replaced the resolver's investigation — what it tried, and the
    concrete thing it needs — with the producer's one-line block summary, so the human
    arrived to the question instead of the answer-so-far. It also erased the `AWAITING_OPERATOR`
    /`CONSUMED` history the resolver's own prompt reads back as its "did I already answer
    this?" loop guard, which is what let the same block escalate round after round.

    Contrast `test_the_human_mode_gate_blocks_on_the_story_folder`: there no resolver ran, so
    the flow writing the questions is the only thing that puts an ask on disk.
    """
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
    """The lane's root-cause bug, from the outside.

    A turn reporting it could not implement the plan used to be discarded where it was
    produced, and the layer went straight on to lint a change nobody had written — the run
    reported `ready` over an empty diff. It is a block like any other now: it parks on the
    story's `context.md`, and the operator's answer re-enters the layer with the answer in
    hand rather than starting the same turn again blind.
    """
    agent = _Agent(docs, impl_blocked=1)
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(docs, seen)):
        result = drive_flow(Dev(story=STORY), env(), agent)

    assert result.status == "ready", result
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    (gate,) = seen
    assert "the plan names a migration nobody has run" in gate, gate
    # The layer is re-entered from the top, so the retried turn is the second one — and it
    # carries what the operator said, which is the whole point of stopping to ask.
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
    """The tight operator cycle: a refine that re-raises the block keeps escalating, not failing.

    `rework_plan` re-gating a still-blocked plan is what keeps the loop honest — a resolver
    that resolved nothing cannot wave the plan through. Nothing bounds how many times the
    block itself may recur: `MAX_PLAN_BLOCKS` only bounds how many of those trips get a
    resolver turn before `_gate_plan` starts routing straight to a human instead, forever if
    it must. Once a real answer lands the run finishes, rather than the block having ended
    the run on its own somewhere short of that.
    """
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
    """`operator_mode=human` skips the resolver entirely, and has no bound of its own either.

    Only `resolve_plan` increments `plan_blocks`, and human mode never calls it — `_gate_plan`
    takes the direct-to-human arm unconditionally in this mode, so there is nothing here for
    `MAX_PLAN_BLOCKS` to bound. A human who answers wrong more times than that is asked again,
    not handed a failed run.
    """
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
    # More asks than the resolver's own cap, with zero resolver turns — proof this mode was
    # never tied to that counter at all, not just given a larger one.
    assert len(seen) == nodes.MAX_PLAN_BLOCKS + 2, seen


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


def test_the_gate_lane_repairs_and_re_runs_until_clean(
    docs: Path,
    workspace: dict[str, Path],
    lint_gate: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A dirty layer is repaired and re-gated; the second run is genuinely clean.

    `web` has adopted no gate, so it is `skipped` and moves straight on — which is the
    opt-in half of the same behavior.
    """
    agent = _Agent(docs, fix_gate=lint_gate)
    run_env = env()

    result = drive_flow(Dev(story=STORY), run_env, agent)

    assert result.status == "ready", result
    assert agent.counts()["dev-fix"] == 1, agent.counts()
    assert lint_gate.is_file(), "the fixer did not write what the gate checks for"
    # The last gate run of the run is `web`'s, which adopted nothing.
    assert _output(run_env, run_gate)["status"] == "skipped"
    # The fixer was handed one `FailureReport`, built in Python off the gate's own output:
    # which gate, what it ran, where, and what it printed.
    report = agent.args_for("dev-fix")[0]["report"]
    assert report["source"] == "lint", report
    assert report["command"] == "sh lint.sh", report
    assert report["cwd"] == str(workspace["api"]), report


def test_a_gate_no_repair_lap_can_satisfy_never_gives_up_either(
    docs: Path,
    workspace: dict[str, Path],
    lint_gate: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A spent repair budget is a block, not a give-up.

    The old lint loop was fail-open: two fruitless fix turns and the layer moved on, on the
    argument that QA re-runs lint as the binding gate. That is the shape AGENTS.md rules
    out — the run went on to report success over a service nobody had looked at. The budget
    bounds the *lap* now; the block goes to the operator, as many times as it takes, and the
    run finishes once something actually clears the gate.
    """
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

    checkpoint = parse_checkpoint((run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    resume = read_resume(checkpoint)
    assert resume.state == "implement", resume
    assert resume.flow == "Dev", resume
    # The cursor and the repair lap: the layer loop's `operator_context`/`impl_blocks` are
    # still at their defaults on a first pass, so nothing carries them into the checkpoint.
    assert resume.params == {
        "index": 0,
        "lap": {"fix_lap": 0, "session_turns": 1, "digest": ""},
    }, resume.params

    agent = _Agent(docs)
    result = drive_flow(Dev(**resume.inputs), env(run_dir=run_dir), agent, resume)

    assert result.status == "ready", result
    assert agent.counts() == {"implement-plan": 2}, agent.counts()
