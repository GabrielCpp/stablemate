"""Composition and direct-state tests for the `docs` flow."""
from __future__ import annotations

import hashlib
import itertools
import json
import logging
import subprocess
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from workhorse.artifacts import ArtifactWriter
from workhorse.pyflow import WorkflowFailed
from workhorse.pyflow import park as pyflow_park
from workhorse.pyflow.driver import read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import parse_checkpoint

import workhorse_workflows.coder.docs.flow as docs_flow
from workhorse_workflows.coder.docs.flow import Docs
from workhorse_workflows.coder.docs.flow import _prompt_note
from workhorse_workflows.coder.shared.docs import (
    CONTEXT_FILE,
    DOCTOR_ERRORS_FILE,
    _doctor_errors_note,
    classify_documentation_context,
    verify_story_documentation,
)
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.owner import MAX_BLOCKS, MAX_LAPS
from workhorse_workflows.coder.shared.schemas.docs import DocumentationGate
from workhorse_workflows.coder.shared.okf import build_okf_context, validate_okf_context
from workhorse_workflows.coder.shared.worktree import snapshot_worktree_state

STORY = "STORY-1"
EPIC = "EPIC-1"
SPEC_REL = f"docs/specs/{STORY}"
STORY_REL = f"docs/epics/{EPIC}/stories/{STORY}"
BLOCK_NOTE = "the slug contract is ambiguous"
OPERATOR_ANSWER = "One slug per locale."

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


def _plan_context(repo_name: str) -> dict[str, Any]:
    """The plan the dev run left behind, naming the one repo the story touched."""
    return {
        "story": STORY,
        "services": [
            {"repo": repo_name, "path": ".", "type": "go", "plan_file": "plan-api.md"}
        ],
    }




@pytest.fixture
def docs(repo: Path, write: Callable[[Path, str], Path]) -> Path:
    """A docs repo ostler can load: one epic, one authored story, one spec dir."""
    write(repo / "docs" / "epics" / EPIC / "epic.md", EPIC_MD)
    write(repo / STORY_REL / "story.md", STORY_MD)
    write(repo / SPEC_REL / "plan-context.json", json.dumps(_plan_context("api"), indent=2))
    return repo


@pytest.fixture
def elsewhere(
    tmp_path: Path,
    docs: Path,
    git: Callable[..., subprocess.CompletedProcess],
    write: Callable[[Path, str], Path],
    ambient: dict[str, str],
) -> Path:
    """A code repo *outside* the docs worktree — the multi-repo shape, i.e."""
    root = tmp_path / "ws"
    api = root / "api"
    api.mkdir(parents=True)
    git(api, "init", "-q", "-b", "main")
    write(api / "main.go", "package main\n")
    git(api, "add", "-A")
    git(api, "commit", "-qm", "Initial commit")
    write(root / "acme.code-workspace", json.dumps({"folders": [{"name": "api", "path": "api"}]}))
    ambient["workspace_file"] = str(root / "acme.code-workspace")
    return api


@pytest.fixture
def alongside(
    tmp_path: Path,
    docs: Path,
    write: Callable[[Path, str], Path],
    ambient: dict[str, str],
) -> Path:
    """The docs repo *is* the code repo — the single-worktree shape, i.e."""
    (docs / SPEC_REL / "plan-context.json").write_text(
        json.dumps(_plan_context("acme"), indent=2), encoding="utf-8"
    )
    ws = tmp_path / "acme.code-workspace"
    write(ws, json.dumps({"folders": [{"name": "acme", "path": str(docs)}]}))
    ambient["workspace_file"] = str(ws)
    return docs




class _Agent:
    """The owner turn and the resolver, scripted on the axes the states branch on."""

    def __init__(
        self,
        *,
        author_status: str = "documented",
        author_nodes: tuple[str, ...] = ("docs/features/widget.md",),
        nodes_until: int | None = None,
        blocked: int = 0,
        explode: set[str] | None = None,
        explode_after: int = 1,
        resolver_decision: str = "escalated",
        resolver_answer: str = "",
        resolver_scope: str = "story",
    ) -> None:
        self.author_status = author_status
        self.author_nodes = author_nodes
        self.nodes_until = nodes_until
        self.blocked = blocked
        self.explode = explode or set()
        self.explode_after = explode_after
        self.resolver_decision = resolver_decision
        self.resolver_answer = resolver_answer
        self.resolver_scope = resolver_scope
        self.calls: list[str] = []
        self.args: list[dict[str, Any]] = []

    AUTHOR_STEM = "document-story"

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        stem = Path(node.prompt).stem
        data = ctx.as_dict()
        self.calls.append(stem)
        self.args.append(data)
        nth = self.counts()[stem]
        if stem in self.explode and nth >= self.explode_after:
            raise RuntimeError(f"killed during {stem}")
        handler = getattr(self, f"_{stem.replace('-', '_')}")
        return f"(scripted) {node.prompt}", handler(data, nth)

    def counts(self) -> Counter[str]:
        return Counter(self.calls)

    def authored(self) -> int:
        """How many owner turns have run."""
        return self.counts()[self.AUTHOR_STEM]

    def args_for(self, stem: str) -> list[dict[str, Any]]:
        return [a for s, a in zip(self.calls, self.args, strict=True) if s == stem]

    def author_args(self) -> list[dict[str, Any]]:
        """Every owner turn's brief in order."""
        return self.args_for(self.AUTHOR_STEM)

    def _document_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if nth <= self.blocked:
            return {"status": "blocked", "nodes": [], "notes": BLOCK_NOTE}
        named = self.nodes_until is None or nth <= self.nodes_until
        return {
            "status": self.author_status,
            "nodes": list(self.author_nodes) if named else [],
            "notes": f"documented on pass {nth}",
        }

    def _resolve_operator(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """The author standing in for itself on a block, `context.md` and all."""
        if self.resolver_decision == "answered":
            context = Path(data["story_path"]).parent / "context.md"
            context.write_text(
                f"STATUS: ANSWERED\nSCOPE: {self.resolver_scope}\n\n"
                f"## Your answers\n\n{self.resolver_answer}\n",
                encoding="utf-8",
            )
        return {"decision": self.resolver_decision, "summary": "resolved the docs block"}


def _sha256(path: Path) -> str:
    """The digest `snapshot_worktree_state` records for one worktree file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _output(run_env: RunEnv, node: Any) -> dict[str, Any]:
    """A node's recorded output — the artifact, not the return value the flow saw."""
    path = run_env.writer.run_dir / node.__name__ / "output.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _answers(seen: list[str], scope: str = "story") -> Callable[..., None]:
    """A stand-in for the human the `Await` is waiting on."""

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text(encoding="utf-8"))
        path.write_text(
            f"STATUS: ANSWERED\nSCOPE: {scope}\n\n{OPERATOR_ANSWER}\n", encoding="utf-8"
        )

    return answered


def _never_waits(path: Path, **kwargs: Any) -> None:
    """The driver's wait, replaced by the assertion that nothing may reach it."""
    raise AssertionError(f"the flow parked on {path}")


class _Grounding(_Agent):
    """An owner that closes the worklist from turn `grounds_on` on."""

    def __init__(self, root: Path, *, grounds_on: int = 1, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.root = root
        self.grounds_on = grounds_on

    def _document_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if nth >= self.grounds_on:
            path = self.root / "docs/features/widget.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "---\ntype: concept\nslug: widget\ntitle: Widget\n---\n"
                "# Widget\n\n- code: `api/widget.go::Widget`\n",
                encoding="utf-8",
            )
        return super()._document_story(data, nth)




def test_a_repo_with_no_okf_book_ends_successfully_without_an_agent_turn(
    repo: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`not_applicable` is a success, and the cheap detector is what makes it cheap."""
    agent = _Agent()

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "not_applicable", result
    assert result.notes == "no OKF configuration or features tree", result
    assert agent.calls == [], agent.calls


def test_an_unresolvable_story_fails_before_anything_else(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A blank slug resolves to no story path, and documenting nothing is not a success."""
    with pytest.raises(WorkflowFailed, match="nothing to document"):
        drive_flow(Docs(), env(), _Agent())




def test_sources_outside_the_docs_worktree_take_the_semantic_route(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The multi-repo case: no diff to map, so no packet is built and doctor is the authority."""
    agent = _Agent()
    run_env = env()

    result = drive_flow(Docs(story=STORY, epic=EPIC), run_env, agent)

    assert result.status == "passed", result
    assert result.authored_nodes == ["docs/features/widget.md"], result
    assert _output(run_env, classify_documentation_context)["mode"] == "semantic"
    assert not (run_env.writer.run_dir / build_okf_context.__name__).exists()
    assert agent.counts() == {"document-story": 1}
    first = agent.author_args()[0]
    assert first["epic_path"] == "docs/epics/EPIC-1/epic.md", first
    assert first["context_mode"] == "semantic", first
    assert first["report"] == "", first
    assert first["operator_context"] == "", first


def test_minted_story_maps_an_external_repository_from_its_story_commit(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    git: Callable[..., subprocess.CompletedProcess],
    write: Callable[[Path, str], Path],
) -> None:
    story_id = "x-01ABCDEF"
    story = docs / STORY_REL / "story.md"
    story.write_text(
        story.read_text(encoding="utf-8").replace(
            "type: story", f"id: {story_id}\ntype: story"
        ),
        encoding="utf-8",
    )
    write(elsewhere / "widget.go", "package api\n\nfunc Widget() {}\n")
    git(elsewhere, "add", "widget.go")
    git(
        elsewhere,
        "commit",
        "-q",
        "-m",
        f"feat(api): add widget\n\nStory: {story_id}",
    )

    class _ExternalGrounding(_Agent):
        def _document_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
            write(
                docs / "docs/features/widget.md",
                "---\ntype: concept\nslug: widget\ntitle: Widget\n---\n"
                "# Widget\n\n- code: `repo://api/widget.go::Widget`\n",
            )
            return super()._document_story(data, nth)

    run_env = env()
    result = drive_flow(Docs(story=STORY, epic=EPIC), run_env, _ExternalGrounding())

    assert result.status == "passed", result
    assert _output(run_env, classify_documentation_context)["mode"] == "semantic"
    packet = _output(run_env, build_okf_context)["ostler"]
    assert packet["version"] == 2
    assert packet["repositories"][0]["id"] == "api"
    assert packet["changedUnits"][0]["repository"] == "api"


def test_sources_inside_the_docs_worktree_take_the_local_route(
    docs: Path,
    alongside: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The single-worktree case: the diff is mapped onto the graph before anyone reads prose."""
    agent = _Agent()
    run_env = env()

    result = drive_flow(Docs(story=STORY, epic=EPIC), run_env, agent)

    assert result.status == "passed", result
    classification = _output(run_env, classify_documentation_context)
    assert classification["mode"] == "local", classification
    assert classification["source_roots"] == ["acme=."], classification
    assert _output(run_env, build_okf_context)["status"] == "passed"
    assert _output(run_env, validate_okf_context)["status"] == "passed"
    gate = _output(run_env, verify_story_documentation)
    assert gate["status"] == "passed", gate


def test_the_owner_is_handed_the_grounding_worklist_before_it_writes(
    docs: Path,
    alongside: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    write: Callable[[Path, str], Path],
) -> None:
    """The join the gate does after the owner, done once before it instead."""
    write(alongside / "api" / "widget.go", "package api\n\nfunc Widget() {}\n")
    agent = _Grounding(alongside, grounds_on=2)

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    first, second = agent.author_args()
    assert first["obligations"] == ["api/widget.go::Widget"], first["obligations"]
    assert second["obligations"] == ["api/widget.go::Widget"], second["obligations"]
    assert "api/widget.go::Widget" in second["report"], second["report"]


def test_an_owner_that_closes_the_worklist_ends_the_lane_in_one_turn(
    docs: Path,
    alongside: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    write: Callable[[Path, str], Path],
) -> None:
    """The review runs inside the owner's turn, so a green check needs no further turn."""
    write(alongside / "api" / "widget.go", "package api\n\nfunc Widget() {}\n")
    agent = _Grounding(alongside)
    run_env = env()

    result = drive_flow(Docs(story=STORY, epic=EPIC), run_env, agent)

    assert result.status == "passed", result
    assert agent.counts() == {"document-story": 1}, agent.counts()
    assert agent.author_args()[0]["obligations"] == ["api/widget.go::Widget"]
    assert _output(run_env, verify_story_documentation)["status"] == "passed"



_GATE_NAMES = itertools.count(1)


def _stage_gate(
    monkeypatch: pytest.MonkeyPatch, *, passes_on: int | None, note: str = "not grounded"
) -> list[tuple[Any, ...]]:
    """Stage the grounding gate's verdict on a schedule: red until `passes_on`, or forever."""
    seen: list[tuple[Any, ...]] = []

    def _gate(*args: Any, **kwargs: Any) -> DocumentationGate:
        seen.append(args)
        if passes_on is not None and len(seen) >= passes_on:
            return DocumentationGate(status="passed", notes="")
        return DocumentationGate(
            status="invalid", notes=note, failures=["G:api/widget.go::Widget"]
        )

    _gate.__name__ = f"_staged_gate_{next(_GATE_NAMES)}"
    monkeypatch.setattr(docs_flow, "verify_story_documentation", blueprint.node(_gate))
    return seen


def test_a_failed_check_goes_back_to_the_owner_as_one_report(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gate's brief reaches the owner verbatim, with what it still owes as the worklist."""
    _stage_gate(monkeypatch, passes_on=2, note="one symbol is not directly grounded")
    agent = _Agent()

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    assert agent.authored() == 2, agent.counts()
    first, second = agent.author_args()
    assert first["report"] == "", first
    assert "one symbol is not directly grounded" in second["report"], second
    assert second["obligations"] == ["api/widget.go::Widget"], second


def test_a_repair_lap_with_nothing_left_to_edit_keeps_the_nodes_already_named(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The nodes accumulate across passes; the last pass does not replace them."""
    seen = _stage_gate(monkeypatch, passes_on=2)
    agent = _Agent(nodes_until=1)

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    assert agent.authored() == 2, agent.counts()
    assert [call[7] for call in seen] == [("docs/features/widget.md",)] * 2, seen
    assert result.authored_nodes == ["docs/features/widget.md"], result


def test_checks_that_stay_red_past_the_lap_budget_park_instead_of_failing(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A spent repair budget is a block: the resolver escalates, and the answer resumes the owner."""
    _stage_gate(monkeypatch, passes_on=MAX_LAPS + 2, note="one symbol is not directly grounded")
    agent = _Agent()
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", _answers(seen)):
        result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    assert agent.counts() == {"document-story": MAX_LAPS + 2, "resolve-operator": 1}
    (gate,) = seen
    assert f"The checks still fail after {MAX_LAPS} repair turn(s)." in gate, gate
    assert "one symbol is not directly grounded" in gate, gate
    turns = agent.author_args()
    assert all(t["report"] for t in turns[1 : MAX_LAPS + 1]), turns
    assert OPERATOR_ANSWER in turns[-1]["operator_context"], turns[-1]


def test_the_grounding_failure_names_the_symbols_not_the_files(
    docs: Path,
    logger: logging.Logger,
    write_json: Callable[[Path, Any], Path],
) -> None:
    """The rework brief has to name what the gate actually tested, or the loop cannot end."""
    controller = "api/internal/app/controllers/link.go"
    settled = "api/internal/app/exceptions/errors.go"
    write_json(
        docs / SPEC_REL / CONTEXT_FILE,
        {
            "changedCode": [
                {
                    "path": controller,
                    "basePath": controller,
                    "headPath": controller,
                    "baseSymbols": [],
                    "headSymbols": ["(*LinkController).Create", "(*LinkController).Resolve"],
                },
                {
                    "path": settled,
                    "basePath": settled,
                    "headPath": settled,
                    "baseSymbols": [],
                    "headSymbols": ["ErrNotFound"],
                },
                {
                    "path": "api/config.yaml",
                    "basePath": "api/config.yaml",
                    "headPath": "api/config.yaml",
                    "baseSymbols": [],
                    "headSymbols": [],
                },
            ],
            "directNodes": [
                {
                    "node": "docs/features/widget.md#links",
                    "reasons": [
                        {"kind": "changed-code", "ref": f"{controller}::(*LinkController).Create"},
                        {"kind": "changed-code", "ref": f"{settled}::ErrNotFound"},
                    ],
                }
            ],
        },
    )

    gate = verify_story_documentation(
        logger,
        spec_dir=SPEC_REL,
        author_status="documented",
        build_status="passed",
        validation_status="passed",
        context_mode="local",
        author_nodes=("docs/features/widget.md#links",),
    )

    assert gate.status == "invalid", gate
    assert f"{controller}::(*LinkController).Resolve" in gate.notes, gate.notes
    assert "Create" not in gate.notes, gate.notes
    assert settled not in gate.notes, gate.notes
    assert "api/config.yaml" in gate.notes, gate.notes
    assert "2 changed production symbol(s)" in gate.notes, gate.notes
    assert sorted(gate.failures) == [
        "G:api/config.yaml",
        f"G:{controller}::(*LinkController).Resolve",
    ], gate.failures


def test_grounding_the_enclosing_unit_grounds_what_is_nested_inside_it(
    docs: Path,
    logger: logging.Logger,
    write_json: Callable[[Path, Any], Path],
) -> None:
    """A nested symbol has no documentable surface of its own, so it cannot be owed alone."""
    panel = "web/app/components/panel.tsx"
    write_json(
        docs / SPEC_REL / CONTEXT_FILE,
        {
            "changedCode": [
                {
                    "path": panel,
                    "basePath": panel,
                    "headPath": panel,
                    "baseSymbols": [],
                    "headSymbols": ["Panel", "Panel.status", "Panel.el", "Badge.tone"],
                }
            ],
            "directNodes": [
                {
                    "node": "docs/features/widget.md#panel",
                    "reasons": [{"kind": "changed-code", "ref": f"{panel}::Panel"}],
                }
            ],
        },
    )

    gate = verify_story_documentation(
        logger,
        spec_dir=SPEC_REL,
        author_status="documented",
        build_status="passed",
        validation_status="passed",
        context_mode="local",
        author_nodes=("docs/features/widget.md#panel",),
    )

    assert gate.status == "invalid", gate
    assert "1 changed production symbol(s)" in gate.notes, gate.notes
    assert f"{panel}::Badge.tone" in gate.notes, gate.notes
    assert "Panel.status" not in gate.notes, gate.notes
    assert "Panel.el" not in gate.notes, gate.notes
    assert gate.failures == [f"G:{panel}::Badge.tone"], gate.failures


def test_a_doctor_refusal_carries_the_form_the_checker_would_accept(
    docs: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    write_json: Callable[[Path, Any], Path],
) -> None:
    """The same trap as the grounding message above, one gate over."""
    screen = "docs/features/groom/gui/screens/s.md"
    write(
        docs / screen,
        "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
        "## Components\n\n### body\n- role: article\n- name: none\n"
        "- placement: mostly the middle\n",
    )
    write_json(docs / SPEC_REL / CONTEXT_FILE, {"changedCode": [], "directNodes": []})

    gate = verify_story_documentation(
        logger,
        spec_dir=SPEC_REL,
        author_status="documented",
        build_status="passed",
        validation_status="passed",
        context_mode="local",
        author_nodes=(screen,),
    )

    assert gate.status == "invalid", gate
    assert "malformed-placement" in gate.notes, gate.notes
    assert "expected form: - placement: width 60-100%, x 0-20%" in gate.notes, gate.notes


def test_every_affected_doctor_error_reaches_the_repair_turn() -> None:
    """Nothing is omitted, because omitting is what made the loop."""
    findings = [
        {
            "path": "docs/features/groom/gui/screens/s.md",
            "line": index,
            "code": "unparsed-check",
            "message": "`verify:` names a test id instead of an observation",
            "suggestion": '- verify: visible(locator="button")',
        }
        for index in range(40)
    ]

    notes = _doctor_errors_note(findings)

    assert len(notes.splitlines()) == 41, notes
    assert "omitted" not in notes, notes
    assert ":39 [unparsed-check]" in notes, notes


def test_an_over_long_doctor_list_is_spilled_to_a_file_the_note_names(
    docs: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    write_json: Callable[[Path, Any], Path],
) -> None:
    """A list too big for an argv becomes a path, never a truncation."""
    screen = "docs/features/groom/gui/screens/s.md"
    components = "".join(
        f"### body{index}\n- role: article\n- name: none\n- placement: mostly the middle\n\n"
        for index in range(200)
    )
    write(
        docs / screen,
        "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n## Components\n\n" + components,
    )
    write_json(docs / SPEC_REL / CONTEXT_FILE, {"changedCode": [], "directNodes": []})
    spill = docs / SPEC_REL / DOCTOR_ERRORS_FILE

    gate = verify_story_documentation(
        logger,
        spec_dir=SPEC_REL,
        author_status="documented",
        build_status="passed",
        validation_status="passed",
        context_mode="local",
        author_nodes=(screen,),
    )

    assert gate.status == "invalid", gate
    assert str(spill) in gate.notes, gate.notes
    assert f"{gate.doctor_error_count} doctor errors" in gate.notes, gate.notes
    assert len(gate.notes) < 12000, gate.notes
    assert len(spill.read_text(encoding="utf-8").splitlines()) == gate.doctor_error_count + 1
    assert len(gate.failures) == gate.doctor_error_count

    write(
        docs / screen,
        "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
        "## Components\n\n### body\n- role: article\n- name: none\n"
        "- placement: mostly the middle\n",
    )
    again = verify_story_documentation(
        logger,
        spec_dir=SPEC_REL,
        author_status="documented",
        build_status="passed",
        validation_status="passed",
        context_mode="local",
        author_nodes=(screen,),
    )

    assert again.status == "invalid", again
    assert "malformed-placement" in again.notes, again.notes
    assert not spill.exists()


def test_checkpointed_repair_notes_are_compacted_for_the_agent_brief() -> None:
    """A resumed run may already carry the old oversized gate notes in its checkpoint."""
    notes = _prompt_note("x" * 20000)

    assert len(notes) < 12100, notes
    assert "note truncated for the agent prompt" in notes, notes


def test_a_deletion_needs_no_code_bullet(
    docs: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    write_json: Callable[[Path, Any], Path],
) -> None:
    """A deletion is satisfied on its own — no `code:` bullet names it, because a live bullet pointing at a gone target is exactly what `ostler doctor` rejects as a dangling reference, and there is no marker that exempts a ref from having to exist."""
    deleted = "api/legacy/handler.go"
    write(
        docs / "docs/features/widget.md",
        """---
type: concept
slug: widget
title: Widget
---
# Widget

The old handler was retired.
""",
    )
    write_json(
        docs / SPEC_REL / CONTEXT_FILE,
        {
            "changedCode": [
                {
                    "path": deleted,
                    "basePath": deleted,
                    "headPath": "",
                    "baseSymbols": ["Handle"],
                    "headSymbols": [],
                    "status": "deleted",
                },
            ],
            "directNodes": [],
        },
    )

    gate = verify_story_documentation(
        logger,
        spec_dir=SPEC_REL,
        author_status="documented",
        build_status="passed",
        validation_status="passed",
        context_mode="local",
        author_nodes=("docs/features/widget.md",),
    )

    assert gate.status == "passed", gate


def test_the_snapshot_records_what_was_already_dirty_with_its_bytes(
    docs: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
) -> None:
    """Modified *and* untracked, because the case that motivated this is untracked."""
    write(docs / "api" / "legacy.go", "package api\n\nfunc Orphan() {}\n")
    (docs / "README.md").write_text("# acme, edited\n", encoding="utf-8")

    snapshot = snapshot_worktree_state(logger)

    recorded = dict(entry.partition("\0")[::2] for entry in snapshot.entries)
    assert recorded["api/legacy.go"] == _sha256(docs / "api" / "legacy.go"), recorded
    assert recorded["README.md"] == _sha256(docs / "README.md"), recorded


def test_work_already_dirty_when_the_story_started_is_not_this_story_s_to_ground(
    docs: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    write_json: Callable[[Path, Any], Path],
) -> None:
    """The cascade this gate had: one abandoned story disabling it for the whole repo."""
    orphan = "api/legacy.go"
    write(docs / orphan, "package api\n\nfunc Orphan() {}\n")
    write_json(
        docs / SPEC_REL / CONTEXT_FILE,
        {
            "changedCode": [
                {
                    "path": orphan,
                    "basePath": orphan,
                    "headPath": orphan,
                    "baseSymbols": [],
                    "headSymbols": ["Orphan"],
                }
            ],
            "directNodes": [],
        },
    )

    def _gate(preexisting: tuple[str, ...]) -> Any:
        return verify_story_documentation(
            logger,
            spec_dir=SPEC_REL,
            author_status="not_required",
            build_status="passed",
            validation_status="passed",
            context_mode="local",
            preexisting=preexisting,
        )

    assert f"{orphan}::Orphan" in _gate(()).notes

    stale = f"{orphan}\0{_sha256(docs / orphan)}"
    assert "not directly grounded" not in _gate((stale,)).notes

    (docs / orphan).write_text("package api\n\nfunc Orphan() { println(1) }\n", encoding="utf-8")
    assert f"{orphan}::Orphan" in _gate((stale,)).notes


def test_not_required_is_a_real_answer_and_still_goes_through_the_gate(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """"This story changed nothing the book describes" is a claim, so it is checkable."""
    agent = _Agent(author_status="not_required", author_nodes=())
    run_env = env()

    result = drive_flow(Docs(story=STORY, epic=EPIC), run_env, agent)

    assert result.status == "passed", result
    assert agent.counts() == {"document-story": 1}
    assert _output(run_env, verify_story_documentation)["status"] == "passed"


def test_an_owner_that_did_not_speak_fails_the_flow(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A blank status fails, and does not spend a lap."""
    agent = _Agent(author_status="")

    with pytest.raises(WorkflowFailed, match="is not a DocumentationResult"):
        drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert agent.authored() == 1, agent.counts()


def test_a_block_the_resolver_cannot_answer_parks_and_resumes_with_the_answer(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """In `auto` mode an escalating resolver hands the block to a person, and the lane waits."""
    agent = _Agent(blocked=1)
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", _answers(seen)):
        result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    assert agent.counts() == {"document-story": 2, "resolve-operator": 1}, agent.counts()
    (gate,) = seen
    assert BLOCK_NOTE in gate, gate
    first, second = agent.author_args()
    assert first["operator_context"] == "", first
    assert OPERATOR_ANSWER in second["operator_context"], second


def test_a_block_is_put_to_the_author_before_anyone_is_asked(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The specs were authored by a workflow, so the author is who ratifies the contract."""
    agent = _Agent(blocked=1, resolver_decision="answered", resolver_answer=OPERATOR_ANSWER)

    with patch.object(pyflow_park, "wait_for_answer", _never_waits):
        result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    assert agent.counts() == {"document-story": 2, "resolve-operator": 1}, agent.counts()
    assert OPERATOR_ANSWER in agent.author_args()[1]["operator_context"]


def test_the_author_is_consulted_on_a_budget_and_a_person_after_it(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The cap is on the resolver, not the block: `MAX_BLOCKS` consults, then the lane parks."""
    agent = _Agent(
        blocked=MAX_BLOCKS + 1, resolver_decision="answered", resolver_answer="Pick A."
    )
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", _answers(seen)):
        result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    assert agent.counts() == {
        "document-story": MAX_BLOCKS + 2,
        "resolve-operator": MAX_BLOCKS,
    }, agent.counts()
    assert len(seen) == 1, seen


def test_an_epic_scoped_answer_blocks_the_story_with_the_answer_as_the_finding(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`SCOPE: epic` means the decision is bigger than this story, so this story cannot fix it."""
    agent = _Agent(
        blocked=99,
        resolver_decision="answered",
        resolver_scope="epic",
        resolver_answer="The whole publishing epic targets an environment that does not exist.",
    )

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "blocked", result
    assert "targets an environment that does not exist" in result.notes, result
    assert agent.counts() == {"document-story": 1, "resolve-operator": 1}, agent.counts()


def test_operator_mode_human_waits_for_a_person(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Someone who asked to be asked is asked: no resolver turn, the driver's `Await` instead."""
    paths: list[Path] = []
    agent = _Agent(blocked=1)

    def _answer(path: Path, **kwargs: Any) -> None:
        paths.append(path)
        path.write_text(
            f"STATUS: ANSWERED\nSCOPE: story\n\n{OPERATOR_ANSWER}\n", encoding="utf-8"
        )

    with patch.object(pyflow_park, "wait_for_answer", _answer):
        result = drive_flow(Docs(story=STORY, epic=EPIC, operator_mode="human"), env(), agent)

    assert result.status == "passed", result
    assert agent.counts() == {"document-story": 2}, agent.counts()
    assert paths == [docs / STORY_REL / "context.md"], paths


def test_a_run_killed_mid_repair_resumes_knowing_what_was_outstanding(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The lap, the report and the worklist survive the kill, so the resumed owner repairs."""
    _stage_gate(monkeypatch, passes_on=2, note="one symbol is not directly grounded")
    run_env = env()
    run_dir = run_env.writer.run_dir

    with pytest.raises(RuntimeError, match="killed during document-story"):
        drive_flow(
            Docs(story=STORY, epic=EPIC),
            run_env,
            _Agent(explode={"document-story"}, explode_after=2),
        )

    checkpoint = parse_checkpoint((run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    resume = read_resume(checkpoint)
    assert resume.state == "work", resume
    assert resume.flow == "Docs", resume
    assert resume.params["laps"] == 1, resume.params
    assert "one symbol is not directly grounded" in resume.params["report"], resume.params
    assert list(resume.params["obligations"]) == ["api/widget.go::Widget"], resume.params
    assert list(resume.params["authored_nodes"]) == ["docs/features/widget.md"], resume.params

    agent = _Agent()
    result = drive_flow(Docs(**resume.inputs), env(run_dir=run_dir), agent, resume)

    assert result.status == "passed", result
    assert agent.counts() == {"document-story": 1}, agent.counts()
    assert "one symbol is not directly grounded" in agent.author_args()[0]["report"]
