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
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from workhorse.artifacts import ArtifactWriter
from workhorse.pyflow import Continue, WorkflowFailed
from workhorse.runner.failure import BackendInvocationError
from workhorse.pyflow import driver as pyflow_driver
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
from workhorse_workflows.coder.shared.schemas.docs import (
    ContextClassification,
    DocsLoop,
    DocsProgress,
    DocumentationFinding,
    DocumentationGate,
    DocumentationResult,
    DocumentationReview,
)
from workhorse_workflows.coder.shared.okf import build_okf_context, validate_okf_context
from workhorse_workflows.coder.shared.worktree import snapshot_worktree_state

STORY = "STORY-1"
EPIC = "EPIC-1"
SPEC_REL = f"docs/specs/{STORY}"
STORY_REL = f"docs/epics/{EPIC}/stories/{STORY}"

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
    """The flow's two turns, scripted on the two axes the states branch on."""

    def __init__(
        self,
        *,
        author_status: str = "documented",
        author_nodes: tuple[str, ...] = ("docs/features/widget.md",),
        nodes_until: int | None = None,
        review_status: str = "approved",
        approve_after: int = 1,
        structured_findings: bool = True,
        review_findings: list[dict[str, Any]] | None = None,
        findings_per_pass: list[list[dict[str, Any]]] | None = None,
        explode: set[str] | None = None,
        explode_after: int = 1,
        cut: set[str] | None = None,
        cut_pass: int = 1,
        cut_from: int | None = None,
        resolver_decision: str = "escalated",
        resolver_answer: str = "",
        resolver_scope: str = "story",
    ) -> None:
        self.author_status = author_status
        self.author_nodes = author_nodes
        self.nodes_until = nodes_until
        self.review_status = review_status
        self.approve_after = approve_after
        self.structured_findings = structured_findings
        self.review_findings = review_findings
        self.findings_per_pass = findings_per_pass
        self.explode = explode or set()
        self.explode_after = explode_after
        self.cut = cut or set()
        self.cut_pass = cut_pass
        self.cut_from = cut_from
        self.resolver_decision = resolver_decision
        self.resolver_answer = resolver_answer
        self.resolver_scope = resolver_scope
        self.calls: list[str] = []
        self.args: list[dict[str, Any]] = []

    AUTHOR_STEMS = ("document-story", "repair-documentation")

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        stem = Path(node.prompt).stem
        data = ctx.as_dict()
        self.calls.append(stem)
        self.args.append(data)
        nth = self.authored() if stem in self.AUTHOR_STEMS else self.counts()[stem]
        if stem in self.explode and nth >= self.explode_after:
            raise RuntimeError(f"killed during {stem}")
        handler = getattr(self, f"_{stem.replace('-', '_')}")
        answer = handler(data, nth)
        cut_now = nth == self.cut_pass or (
            self.cut_from is not None and nth >= self.cut_from
        )
        if stem in self.cut and cut_now:
            raise BackendInvocationError(f"timed out after {node.timeout}s", timed_out=True)
        return f"(scripted) {node.prompt}", answer

    def counts(self) -> Counter[str]:
        return Counter(self.calls)

    def authored(self) -> int:
        """How many author turns have run, across the draft and every repair."""
        return sum(self.counts()[stem] for stem in self.AUTHOR_STEMS)

    def args_for(self, stem: str) -> list[dict[str, Any]]:
        return [a for s, a in zip(self.calls, self.args, strict=True) if s == stem]

    def author_args(self) -> list[dict[str, Any]]:
        """Every author turn's brief in order, whichever of its two prompts served it."""
        return [a for s, a in zip(self.calls, self.args, strict=True) if s in self.AUTHOR_STEMS]

    def _document_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        named = self.nodes_until is None or nth <= self.nodes_until
        return {
            "status": self.author_status,
            "nodes": list(self.author_nodes) if named else [],
            "notes": f"documented on pass {nth}",
        }

    def _repair_documentation(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """The repair turn answers in the author's own shape — same schema, same gate."""
        return self._document_story(data, nth)

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

    def _review_story_documentation(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if nth >= self.approve_after:
            return {"status": self.review_status, "findings": [], "notes": "reads as built"}
        if not self.structured_findings:
            return {"status": "revise", "findings": [], "notes": "free-form only"}
        if self.findings_per_pass is not None:
            pass_findings = self.findings_per_pass[min(nth, len(self.findings_per_pass)) - 1]
            return {
                "status": "revise",
                "findings": pass_findings,
                "notes": f"structured findings for pass {nth}",
            }
        if self.review_findings is not None:
            return {
                "status": "revise",
                "findings": self.review_findings,
                "notes": "structured but incomplete",
            }
        return {
            "status": "revise",
            "findings": [
                {
                    "id": "D1",
                    "kind": "overclaim",
                    "target": "docs/features/widget.md#states",
                    "issue": "The widget's states are not described",
                    "repair": "Document the as-built states",
                }
            ],
            "notes": "the widget's states are not described",
        }


def _sha256(path: Path) -> str:
    """The digest `snapshot_worktree_state` records for one worktree file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _output(run_env: RunEnv, node: Any) -> dict[str, Any]:
    """A node's recorded output — the artifact, not the return value the flow saw."""
    path = run_env.writer.run_dir / node.__name__ / "output.json"
    return json.loads(path.read_text(encoding="utf-8"))




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
    assert _output(run_env, classify_documentation_context)["mode"] == "semantic"
    assert not (run_env.writer.run_dir / build_okf_context.__name__).exists()
    assert agent.counts() == {"document-story": 1, "review-story-documentation": 1}
    assert agent.args_for("document-story")[0]["epic_path"] == "docs/epics/EPIC-1/epic.md"
    assert agent.args_for("review-story-documentation")[0]["epic_path"] == (
        "docs/epics/EPIC-1/epic.md"
    )


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

    class _Grounding(_Agent):
        def _document_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
            write(
                docs / "docs/features/widget.md",
                "---\ntype: concept\nslug: widget\ntitle: Widget\n---\n"
                "# Widget\n\n- code: `repo://api/widget.go::Widget`\n",
            )
            return super()._document_story(data, nth)

    run_env = env()
    result = drive_flow(Docs(story=STORY, epic=EPIC), run_env, _Grounding())

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


def test_the_author_is_handed_the_grounding_worklist_before_it_writes(
    docs: Path,
    alongside: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    write: Callable[[Path, str], Path],
) -> None:
    """The join the gate does after the author, done once before it instead."""
    write(alongside / "api" / "widget.go", "package api\n\nfunc Widget() {}\n")
    agent = _Agent()
    run_env = env()

    result = drive_flow(Docs(story=STORY, epic=EPIC), run_env, agent)

    assert result.status == "blocked", result
    first = agent.args_for("document-story")[0]
    assert first["obligations"] == ["api/widget.go::Widget"], first["obligations"]
    gate = _output(run_env, verify_story_documentation)
    grounding = [f for f in gate["failures"] if f.startswith("G:")]
    assert grounding == ["G:api/widget.go::Widget"], gate
    assert agent.author_args()[1]["obligations"] == ["api/widget.go::Widget"]


def test_the_reviewer_is_handed_the_unnarrowed_story_delta(
    docs: Path,
    alongside: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    write: Callable[[Path, str], Path],
) -> None:
    """The reviewer's scope is what this story changed, and it does not shrink."""
    write(alongside / "api" / "widget.go", "package api\n\nfunc Widget() {}\n")

    class _Grounding(_Agent):
        """An author that actually closes the worklist, so the gate lets the reviewer run."""

        def _document_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
            write(
                alongside / "docs/features/widget.md",
                "---\ntype: concept\nslug: widget\ntitle: Widget\n---\n"
                "# Widget\n\n- code: `api/widget.go::Widget`\n",
            )
            return super()._document_story(data, nth)

    agent = _Grounding(approve_after=2)

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    assert agent.args_for("document-story")[0]["obligations"] == ["api/widget.go::Widget"]
    assert agent.author_args()[1]["obligations"] == []
    review = agent.args_for("review-story-documentation")
    assert len(review) == 2, agent.calls
    assert [r["obligations"] for r in review] == [["api/widget.go::Widget"]] * 2, review



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


def test_a_failed_gate_reworks_before_the_reviewer_ever_runs(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gate is upstream of the reviewer, and its brief reaches the author verbatim."""
    _stage_gate(monkeypatch, passes_on=2, note="one symbol is not directly grounded")
    agent = _Agent()

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    assert agent.authored() == 2, agent.counts()
    assert agent.counts()["review-story-documentation"] == 1, agent.counts()
    assert "one symbol is not directly grounded" in agent.author_args()[1]["gate_notes"]


def test_a_repair_turn_cut_at_its_budget_is_dispatched_again_rather_than_reported_done(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An overrun `repair-documentation` is run again; it is never reported as an author."""
    _stage_gate(monkeypatch, passes_on=3, note="one symbol is not directly grounded")
    agent = _Agent(cut={"repair-documentation"}, cut_pass=2)

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    assert agent.authored() == 4, agent.counts()
    assert agent.counts()["repair-documentation"] == 3, agent.counts()
    brief = agent.author_args()[2]["gate_notes"]
    assert brief.startswith("Your previous turn was stopped at its wall-clock budget"), brief
    assert "one symbol is not directly grounded" in brief, brief


def test_a_repair_turn_that_never_finishes_escalates_instead_of_lapping(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-dispatching a cut turn is bounded, and the bound is the author gate."""
    _stage_gate(monkeypatch, passes_on=None)
    agent = _Agent(cut={"repair-documentation"}, cut_from=2)

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "blocked", result
    assert "wall-clock budget" in result.notes, result.notes
    assert agent.counts()["repair-documentation"] == Docs.MAX_REPAIR_OVERRUNS, agent.counts()
    assert agent.counts()["resolve-operator"] == 1, agent.counts()


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

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    assert agent.counts() == {"document-story": 1, "review-story-documentation": 1}


def test_an_author_that_did_not_speak_fails_the_flow(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A blank status fails, and does not spend a rework."""
    agent = _Agent(author_status="")

    with pytest.raises(WorkflowFailed, match="is not a DocumentationResult"):
        drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert agent.counts()["document-story"] == 1, agent.counts()


def test_a_blocked_author_returns_a_verdict_instead_of_failing_the_run(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A block is a finding about the story, and it must not take the queue down with it."""
    agent = _Agent(author_status="blocked")

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "blocked", result
    assert result.notes == "documented on pass 1", result
    assert agent.counts() == {"document-story": 1, "resolve-operator": 1}, agent.counts()




def _never_waits(path: Path, **kwargs: Any) -> None:
    """The driver's wait, replaced by the assertion that nothing may reach it."""
    raise AssertionError(f"the flow parked on {path} in auto mode")


class _BlocksOnce(_Agent):
    """An author that refuses the first draft and writes the book once someone decides."""

    def _document_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if nth == 1:
            return {"status": "blocked", "nodes": [], "notes": "the slug contract is ambiguous"}
        return super()._document_story(data, nth)


def test_a_block_is_put_to_the_author_before_it_ends_the_flow(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The specs were authored by a workflow, so the author is who ratifies the contract."""
    agent = _BlocksOnce(resolver_decision="answered", resolver_answer="One slug per locale.")

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    assert agent.counts() == {
        "document-story": 1,
        "resolve-operator": 1,
        "repair-documentation": 1,
        "review-story-documentation": 1,
    }, agent.counts()
    brief = agent.author_args()[1]["review_notes"]
    assert brief.startswith("Ratified by the author:"), brief
    assert "One slug per locale." in brief, brief
    assert "the slug contract is ambiguous" in brief, brief


def test_an_escalating_resolver_blocks_without_parking_the_queue(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """In `auto` mode a resolver that will not decide gives up — it never waits on a person."""
    agent = _Agent(author_status="blocked")

    with patch.object(pyflow_driver, "wait_for_answer", _never_waits):
        result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "blocked", result


def test_the_author_is_consulted_on_a_budget_and_the_block_after_it_stands(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The cap is on the resolver, not the block — `MAX_DOCS_BLOCKS` consults, then it stands."""
    agent = _Agent(author_status="blocked", resolver_decision="answered", resolver_answer="Pick A.")

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "blocked", result
    assert agent.counts() == {
        "document-story": 1,
        "resolve-operator": Docs.MAX_DOCS_BLOCKS,
        "repair-documentation": Docs.MAX_DOCS_BLOCKS,
    }, agent.counts()


def test_an_epic_scoped_answer_blocks_the_story_with_the_answer_as_the_finding(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`SCOPE: epic` means the decision is bigger than this story, so this story cannot fix it."""
    agent = _Agent(
        author_status="blocked",
        resolver_decision="answered",
        resolver_scope="epic",
        resolver_answer="The whole publishing epic targets an environment that does not exist.",
    )

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "blocked", result
    assert "targets an environment that does not exist" in result.notes, result
    assert agent.counts()["repair-documentation"] == 0, agent.counts()


def test_operator_mode_human_still_waits_for_a_person(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Someone who asked to be asked is asked: no resolver turn, the driver's `Await` instead."""
    seen: list[Path] = []
    agent = _Agent(author_status="blocked")

    def _answer(path: Path, **kwargs: Any) -> None:
        seen.append(path)
        path.write_text(
            "STATUS: ANSWERED\nSCOPE: story\n\nOne slug per locale.\n", encoding="utf-8"
        )

    with patch.object(pyflow_driver, "wait_for_answer", _answer):
        result = drive_flow(Docs(story=STORY, epic=EPIC, operator_mode="human"), env(), agent)

    assert result.status == "blocked", result
    assert agent.counts()["resolve-operator"] == 0, agent.counts()
    assert seen == [docs / STORY_REL / "context.md"] * Docs.MAX_DOCS_BLOCKS, seen




def test_a_revision_request_reworks_and_carries_the_notes_forward(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The reviewer's brief reaches the author, and the gate's brief is not dropped for it."""
    agent = _Agent(approve_after=2)

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    assert agent.counts() == {
        "document-story": 1,
        "repair-documentation": 1,
        "review-story-documentation": 2,
    }, agent.counts()
    second = agent.author_args()[1]
    assert "D1 [overclaim] docs/features/widget.md#states" in second["review_notes"]
    assert "The widget's states are not described" in second["review_notes"]
    assert "direct OKF grounding" in second["gate_notes"]
    second_review = agent.args_for("review-story-documentation")[1]
    assert "D1 [overclaim] docs/features/widget.md#states" in second_review["review_notes"]


def test_a_blocked_review_fails_rather_than_reworking(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`blocked` is the reviewer saying no pass will fix this, so spending three is wrong."""
    agent = _Agent(review_status="blocked")

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "blocked", result
    assert agent.counts()["document-story"] == 1, agent.counts()


def test_a_reviewer_reaching_for_a_synonym_of_blocked_is_refused_by_the_schema(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The refusal words are one signal, and the flow no longer has to sort them by spelling."""
    agent = _Agent(review_status="unfixable")

    with pytest.raises(WorkflowFailed, match="is not a DocumentationReview"):
        drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert agent.counts()["repair-documentation"] == 0, agent.counts()


class _RefusesWithEvidence(_Agent):
    """A reviewer that refuses *and* names what it read as wrong."""

    def _review_story_documentation(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return {
            "status": "blocked",
            "findings": [
                {
                    "id": "D9",
                    "kind": "author-decision",
                    "target": "docs/features/widget.md#slug",
                    "issue": "the plan and the spec disagree on the slug contract",
                    "repair": "Ratify one contract and amend the other document",
                }
            ],
            "notes": "the slug contract is ambiguous",
        }


def test_the_reviewers_findings_travel_to_the_operator_gate(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A gate that says only "documentation is impossible" is a gate nobody can answer."""
    agent = _RefusesWithEvidence()
    asked: list[str] = []

    def _answer(path: Path, **kwargs: Any) -> None:
        asked.append(path.read_text(encoding="utf-8"))
        path.write_text("STATUS: ANSWERED\nSCOPE: story\n\nOne slug.\n", encoding="utf-8")

    with patch.object(pyflow_driver, "wait_for_answer", _answer):
        result = drive_flow(Docs(story=STORY, epic=EPIC, operator_mode="human"), env(), agent)

    assert result.status == "blocked", result
    gate = "".join(asked)
    assert "docs/features/widget.md#slug" in gate, gate
    assert "Ratify one contract" in gate, gate


def test_only_the_first_pass_authors_and_every_pass_after_it_repairs(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both the gate and the reviewer send the book to `repair`, not back to `document`."""
    _stage_gate(monkeypatch, passes_on=2)
    agent = _Agent(approve_after=3)

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["document-story"] == 1, agent.counts()
    assert agent.counts()["repair-documentation"] == 3, agent.counts()
    assert agent.calls[0] == "document-story", agent.calls


def test_a_revision_request_without_structured_findings_fails_the_flow(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A prose-only revision request cannot be a repair contract anymore."""
    agent = _Agent(approve_after=99, structured_findings=False)

    with pytest.raises(WorkflowFailed, match="no findings"):
        drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)


def test_a_revision_request_with_an_empty_finding_fails_the_flow(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A nonempty findings list cannot bypass the actionable-fields gate."""
    agent = _Agent(approve_after=99, review_findings=[{"kind": "overclaim"}])

    with pytest.raises(
        WorkflowFailed,
        match="finding 1 missing id, target, issue, repair",
    ):
        drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)


def test_a_finding_id_is_an_opaque_handle(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The id only has to name the same defect twice — no consumer parses its shape."""
    agent = _Agent(approve_after=2, review_findings=[_finding("F1")])

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    assert agent.authored() == 2, agent.counts()
    second = agent.author_args()[1]
    assert "F1 [overclaim] docs/features/widget.md#f1" in second["review_notes"]


class _RoutingSpy:
    """The gate or review result a directly-called state reads."""

    def __init__(
        self,
        *,
        gate: DocumentationGate | None = None,
        review: DocumentationReview | None = None,
    ) -> None:
        self.gate = gate
        self.review = review
        self.calls: list[str] = []


def _routing_docs(monkeypatch: pytest.MonkeyPatch, spy: _RoutingSpy) -> Docs:
    """A docs flow with only the engine seams needed by `verify` and `review`."""
    flow = Docs(story=STORY, epic=EPIC)
    flow._ctx = SimpleNamespace(
        story_slug=STORY,
        story_id="",
        story_path=f"{STORY_REL}/story.md",
        story_epic=EPIC,
        spec_dir=SPEC_REL,
        qa_dir="",
    )

    def fake_call(self: Docs, node: Any, *args: Any, **kwargs: Any) -> Any:
        spy.calls.append(node.__name__)
        assert node is docs_flow.verify_story_documentation
        assert spy.gate is not None
        return spy.gate

    def fake_agent(self: Docs, prompt: str, **kwargs: Any) -> DocumentationReview:
        spy.calls.append(Path(prompt).stem)
        assert spy.review is not None
        return spy.review

    def fake_output(self: Docs, node: Any) -> Any:
        if node is classify_documentation_context:
            return ContextClassification(mode="semantic")
        if node is docs_flow.documentation_obligations:
            return SimpleNamespace(refs=[])
        raise AssertionError(f"unexpected output read: {node.__name__}")

    monkeypatch.setattr(Docs, "call", fake_call)
    monkeypatch.setattr(Docs, "agent", fake_agent)
    monkeypatch.setattr(Docs, "output", fake_output)
    monkeypatch.setattr(Docs, "reset_session", lambda *args: None)
    monkeypatch.setattr(Docs, "logger", property(lambda _: logging.getLogger("test")))
    monkeypatch.setattr(Docs, "_epic_path", property(lambda _: f"docs/epics/{EPIC}/epic.md"))
    monkeypatch.setattr(docs_flow, "workspace_dirs", lambda _: [])
    monkeypatch.setattr(docs_flow, "features_root", lambda _: "docs/features")
    return flow


def _finding(fid: str) -> dict[str, Any]:
    """One well-formed reviewer finding, distinguished from the next only by its id."""
    return {
        "id": fid,
        "kind": "overclaim",
        "target": f"docs/features/widget.md#{fid.lower()}",
        "issue": f"{fid} is not described",
        "repair": f"Document {fid}",
    }


@pytest.mark.parametrize(
    ("rework", "previous", "failures", "expected_state", "expected_progress"),
    [
        pytest.param(0, [], ["G:a"], "repair", "first_pass", id="first-failure-reworks"),
        pytest.param(
            Docs.MAX_REWORKS,
            ["G:a"],
            ["G:a"],
            "resolve_author",
            "stalled",
            id="stalled-budget-blocks",
        ),
        pytest.param(
            Docs.MAX_REWORKS,
            ["E:a", "E:b"],
            ["E:a"],
            "resolve_author",
            "reduced",
            id="shrinking-budget-still-blocks",
        ),
    ],
)
def test_grounding_gate_budget_routes_directly(
    monkeypatch: pytest.MonkeyPatch,
    rework: int,
    previous: list[str],
    failures: list[str],
    expected_state: str,
    expected_progress: str,
) -> None:
    """Grounding progress diagnoses the final pass but never waives its budget."""
    spy = _RoutingSpy(
        gate=DocumentationGate(status="invalid", notes="synthetic findings", failures=failures)
    )
    flow = _routing_docs(monkeypatch, spy)
    loop = DocsLoop(
        rework=rework,
        progress=DocsProgress(gate_ids=previous),
    )

    result = flow.verify(DocumentationResult(status="documented"), loop)

    assert spy.calls == ["verify_story_documentation"]
    assert isinstance(result, Continue) and result.state == expected_state
    routed = result.params["loop"]
    assert isinstance(routed, DocsLoop)
    if expected_state == "repair":
        assert routed.rework == rework + 1
    else:
        assert routed.blocks == 1
        assert "4 grounding passes" in result.params["notes"]
    assert routed.progress.gate_progress_verdict == expected_progress


@pytest.mark.parametrize(
    ("review_rework", "previous", "findings", "expected_state", "expected_progress"),
    [
        pytest.param(0, [], ["D1"], "repair", "first_pass", id="first-revision-reworks"),
        pytest.param(
            Docs.MAX_REVIEW_REWORKS,
            ["D1", "D2"],
            ["D1", "D2"],
            "resolve_author",
            "stalled",
            id="stalled-budget-blocks",
        ),
        pytest.param(
            Docs.MAX_REVIEW_REWORKS,
            ["D1", "D2"],
            ["D3", "D4"],
            "resolve_author",
            "churned",
            id="churned-budget-blocks",
        ),
    ],
)
def test_reviewer_budget_routes_directly(
    monkeypatch: pytest.MonkeyPatch,
    review_rework: int,
    previous: list[str],
    findings: list[str],
    expected_state: str,
    expected_progress: str,
) -> None:
    """Reviewer progress distinguishes stalled work from productive churn at the same cap."""
    review = DocumentationReview(
        status="revise",
        findings=[DocumentationFinding.model_validate(_finding(fid)) for fid in findings],
        notes="synthetic findings",
    )
    spy = _RoutingSpy(review=review)
    flow = _routing_docs(monkeypatch, spy)
    loop = DocsLoop(
        review_rework=review_rework,
        progress=DocsProgress(review_ids=previous),
    )

    result = flow.review(DocumentationResult(status="documented"), loop)

    assert spy.calls == ["review-story-documentation"]
    assert isinstance(result, Continue) and result.state == expected_state
    routed = result.params["loop"]
    assert isinstance(routed, DocsLoop)
    if expected_state == "repair":
        assert routed.review_rework == review_rework + 1
    else:
        assert routed.blocks == 1
        assert "did not converge in 4 passes" in result.params["notes"]
    assert routed.progress.review_progress_verdict == expected_progress



def test_the_gates_failure_does_not_spend_the_reviewers_budget(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One mechanical grounding fix must not cost a semantic round."""
    _stage_gate(monkeypatch, passes_on=2)
    agent = _Agent(approve_after=4)

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    assert agent.counts() == {
        "document-story": 1,
        "repair-documentation": 4,
        "review-story-documentation": 4,
    }, agent.counts()




def test_a_run_killed_mid_review_resumes_without_re_documenting(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The reason `document`, `verify` and `review` are three states rather than one."""
    run_env = env()
    run_dir = run_env.writer.run_dir

    with pytest.raises(RuntimeError, match="killed during review-story-documentation"):
        drive_flow(
            Docs(story=STORY, epic=EPIC),
            run_env,
            _Agent(explode={"review-story-documentation"}),
        )

    checkpoint = parse_checkpoint((run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    resume = read_resume(checkpoint)
    assert resume.state == "review", resume
    assert resume.flow == "Docs", resume
    loop = resume.params["loop"]
    assert loop["rework"] == 0, loop
    assert resume.params["author"]["nodes"] == ["docs/features/widget.md"], resume.params
    assert loop["progress"]["gate_verdict"] == "passed", loop
    assert loop["progress"]["gate_progress_verdict"] == "cleared", loop

    agent = _Agent()
    result = drive_flow(Docs(**resume.inputs), env(run_dir=run_dir), agent, resume)

    assert result.status == "passed", result
    assert agent.counts() == {"review-story-documentation": 1}, agent.counts()


def test_a_run_killed_mid_rework_resumes_knowing_what_was_outstanding(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The baseline a progress verdict is measured against has to survive the kill."""
    run_env = env()
    run_dir = run_env.writer.run_dir

    with pytest.raises(RuntimeError, match="killed during repair-documentation"):
        drive_flow(
            Docs(story=STORY, epic=EPIC),
            run_env,
            _Agent(
                approve_after=99,
                findings_per_pass=[[_finding("D1"), _finding("D2")]],
                explode={"repair-documentation"},
                explode_after=2,
            ),
        )

    checkpoint = parse_checkpoint((run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    resume = read_resume(checkpoint)
    assert resume.state == "repair", resume
    progress = resume.params["loop"]["progress"]
    assert progress["review_disposition"] == "revise", progress
    assert progress["review_ids"] == ["D1", "D2"], progress
    assert progress["review_findings"] == 2, progress
    assert progress["review_progress_verdict"] == "first_pass", progress

    agent = _Agent(
        approve_after=99, findings_per_pass=[[_finding("D1"), _finding("D2")]]
    )
    result = drive_flow(Docs(**resume.inputs), env(run_dir=run_dir), agent, resume)

    assert result.status == "blocked", result
    assert "(stalled)" in result.notes, result.notes
