"""End-to-end tests for the `docs` flow — the OKF pre-gate, the diff gate, the reviewer.

Twenty-two YAML nodes became six states around one loop: an author turn, a fail-closed
grounding gate the author cannot see past, and an independent reviewer downstream of it.
What is worth testing is which of the three OKF arms a repo lands on, which of the two
context modes its source roots pick, and that neither the author's claim nor the reviewer's
approval can skip the gate between them.

**Only the two agent turns are scripted.** `detect_okf_docs` loads a real ostler graph off a
real repo, `classify_documentation_context` really compares resolved source roots against a
real git worktree, and `verify_story_documentation` really runs `ostler doctor` and really
reads the obligation packet. The gate is the reason this flow exists, so a seam through it
would have left nothing under test.

One test calls the gate directly rather than driving the flow: what a *half-grounded* file
does to the rework brief cannot be staged through `ostler qa context`, and it is the case
that decides whether the loop can converge at all.
"""
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
from workhorse_workflows.coder.shared.schemas.docs import DocumentationGate
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

## Implementation Status

- **Status**: Done
"""


def _plan_context(repo_name: str) -> dict[str, Any]:
    """The plan the dev run left behind, naming the one repo the story touched.

    Which repo it names is the whole input to the context classifier: a repo that is not the
    docs worktree makes the mapping partial, and partial is what `semantic` mode exists for.
    """
    return {
        "story": STORY,
        "services": [
            {"repo": repo_name, "path": ".", "type": "go", "plan_file": "plan-api.md"}
        ],
    }


# --------------------------------------------------------------------------- fixtures


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
    """A code repo *outside* the docs worktree — the multi-repo shape, i.e. `semantic`."""
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
    """The docs repo *is* the code repo — the single-worktree shape, i.e. `local`."""
    (docs / SPEC_REL / "plan-context.json").write_text(
        json.dumps(_plan_context("acme"), indent=2), encoding="utf-8"
    )
    ws = tmp_path / "acme.code-workspace"
    write(ws, json.dumps({"folders": [{"name": "acme", "path": str(docs)}]}))
    ambient["workspace_file"] = str(ws)
    return docs


# --------------------------------------------------------------------------- the agent


class _Agent:
    """The flow's two turns, scripted on the two axes the states branch on.

    `author_status`/`author_nodes` are the claim the author reports; the node list is
    advisory, and `nodes_until` is the pass after which it names none — the honest repair
    lap that found nothing left to edit. `review_status` is the reviewer's verdict,
    `approve_after` the pass it stops asking for revisions on. A gate verdict is not one of
    these axes: nothing the author can say makes the gate refuse, so a test that needs a
    refusal stages one with `_stage_gate`.

    `findings_per_pass` varies the reviewer's worklist across passes — the axis a
    *progress* verdict is measured on, where every other axis here is measured per pass.
    `explode_after` picks *which* pass dies, so a kill can be staged after a loop has
    already accumulated a baseline rather than only on the first turn. `cut`/`cut_pass` are
    the softer ending: the named prompt is stopped at its wall-clock budget on exactly that
    pass, which is a turn that wrote something and never replied.

    The three `resolver_*` knobs script the author's say on a block: whether it decides at
    all, what it decided, and whether the decision is this story's or the whole epic's. The
    default is `escalated`, so a test that says nothing about the resolver gets the verdict
    the block asked for and nothing else.
    """

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
        self.resolver_decision = resolver_decision
        self.resolver_answer = resolver_answer
        self.resolver_scope = resolver_scope
        self.calls: list[str] = []
        self.args: list[dict[str, Any]] = []

    #: The author's two prompts. `document-story` writes the first draft and
    #: `repair-documentation` edits the cited nodes on every later pass, so they are one
    #: role and are counted as one: `nth` here means the author's nth turn, not the nth
    #: turn of whichever prompt it happened to reach.
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
        if stem in self.cut and nth == self.cut_pass:
            # The transport-level signal, not the pyflow one: raising `AgentTimeout` here
            # would skip the engine's translation. `retries=0` on the node is what makes
            # this the first and only invocation.
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
        """The author standing in for itself on a block, `context.md` and all.

        An answering resolver really writes the file, because that is the whole protocol
        between this turn and `read_operator_context` — a decision the resolver only
        *reported* would reach the repair lap as an empty brief.
        """
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


# --------------------------------------------------------------------------- the pre-gate


def test_a_repo_with_no_okf_book_ends_successfully_without_an_agent_turn(
    repo: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`not_applicable` is a success, and the cheap detector is what makes it cheap.

    Most repos the coder runs against are not managed by an OKF graph. Under the YAML the
    four call sites treated this exactly like a passed documentation run, and they still do —
    which is only defensible if no author turn was spent discovering it.
    """
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


# ----------------------------------------------------------------------- context modes


def test_sources_outside_the_docs_worktree_take_the_semantic_route(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The multi-repo case: no diff to map, so no packet is built and doctor is the authority.

    A partial mapping would be worse than none — it would ground some changed units and leave
    the rest silently unchecked — so the classifier falls back wholesale rather than per root.
    """
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


def test_sources_inside_the_docs_worktree_take_the_local_route(
    docs: Path,
    alongside: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The single-worktree case: the diff is mapped onto the graph before anyone reads prose.

    A real `ostler qa context` runs here against a real worktree, so this is also the test
    that would catch the builder resolving the wrong repo — and it did, before the fix
    recorded in `nodes/okf.py`: a blank `docs_path` had it discover the *orchestrating*
    repo's graph and report the docs tree as outside it.

    The source roots reach it re-expressed relative to the worktree, which is the form
    `ostler qa context` takes.
    """
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
    """The join the gate does after the author, done once before it instead.

    Without this the first author turn has no gate notes and no worklist, so it derives the
    same join by hand — a real documentation turn was observed spending 128 shell calls
    grepping the book for every changed exported symbol. The list is the packet's, computed
    by the same `ungrounded_refs` the gate calls, so the two cannot disagree; and on a
    rework pass it is the gate's own `G:` identities minus whatever the pass closed.

    The author here never grounds anything, so every pass fails the gate on the same
    reference — which is what makes the two lists directly comparable.
    """
    write(alongside / "api" / "widget.go", "package api\n\nfunc Widget() {}\n")
    agent = _Agent()
    run_env = env()

    result = drive_flow(Docs(story=STORY, epic=EPIC), run_env, agent)

    assert result.status == "blocked", result
    first = agent.args_for("document-story")[0]
    assert first["obligations"] == ["api/widget.go::Widget"], first["obligations"]
    # The rework pass is handed the gate's own `G:` identities, in the same spelling.
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
    """The reviewer's scope is what this story changed, and it does not shrink.

    `review-story-documentation.md` refuses on defects outside the story's obligations, which
    is only bounded if it knows what they are. It reads the same worklist the author gets, but
    the *unnarrowed* one: the author's list shrinks as the grounding gate closes items, and a
    reviewer scope that shrank with it would re-legalize on pass two the findings it had ruled
    out of bounds on pass one — the exact oscillation the bound exists to stop.
    """
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

    # Two reviewer passes, so the second one is reached through `_rework` — which resets the
    # author's `obligations` to empty and is exactly where a shared parameter would lose the
    # scope.
    agent = _Grounding(approve_after=2)

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    assert agent.args_for("document-story")[0]["obligations"] == ["api/widget.go::Widget"]
    assert agent.author_args()[1]["obligations"] == []
    review = agent.args_for("review-story-documentation")
    assert len(review) == 2, agent.calls
    assert [r["obligations"] for r in review] == [["api/widget.go::Widget"]] * 2, review


# --------------------------------------------------------------------------- the gate

#: One registry name per staged gate; see `_stage_gate`.
_GATE_NAMES = itertools.count(1)


def _stage_gate(
    monkeypatch: pytest.MonkeyPatch, *, passes_on: int | None, note: str = "not grounded"
) -> list[tuple[Any, ...]]:
    """Stage the grounding gate's verdict on a schedule: red until `passes_on`, or forever.

    The gate's own judgement is under test a few tests down, against a real book and a real
    `ostler doctor`. What the loop tests need is the *verdict* on a schedule, and since the
    gate stopped scoring the author's self-reported node list — it reads the branch's book
    diff now — no reply the scripted author can give makes it refuse. Staging it is what is
    left, and it is the seam `test_a_shrinking_failure_set_no_longer_waives_the_grounding_budget`
    already opens.

    The failure identity is the same every pass, so the progress verdict a stalled lane
    carries is the real one and not an artefact of the stub. Returns each call's positional
    arguments in order, which is how a test reads what the flow handed the gate.
    """
    seen: list[tuple[Any, ...]] = []

    def _gate(*args: Any, **kwargs: Any) -> DocumentationGate:
        seen.append(args)
        if passes_on is not None and len(seen) >= passes_on:
            return DocumentationGate(status="passed", notes="")
        return DocumentationGate(
            status="invalid", notes=note, failures=["G:api/widget.go::Widget"]
        )

    # A node's name is its identity in the blueprint's registry and a second registration
    # under one name is a definition error, so each staged gate gets its own.
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
    """The gate is upstream of the reviewer, and its brief reaches the author verbatim.

    A book the gate refuses is not a book worth a `power="high"` semantic read: the
    reviewer would spend its budget on prose whose claims are not grounded yet.
    """
    _stage_gate(monkeypatch, passes_on=2, note="one symbol is not directly grounded")
    agent = _Agent()

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    assert agent.authored() == 2, agent.counts()
    # The reviewer never saw the first pass: the gate is upstream of it.
    assert agent.counts()["review-story-documentation"] == 1, agent.counts()
    # And the second author pass was told exactly what was wrong with the first.
    assert "one symbol is not directly grounded" in agent.author_args()[1]["gate_notes"]


def test_a_repair_turn_cut_at_its_budget_is_gated_rather_than_failing_the_run(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An overrun `repair-documentation` goes straight to the gate, because the book is a file.

    The turn's reply is discarded either way — what the gate reads is the graph on disk. So a
    turn stopped at its forty-five-minute cap has still landed the edits it finished, and
    doctor over those is worth more than a dead run. The next lap continues the same session,
    so all it needs is to be told that its own worklist is half-applied.
    """
    _stage_gate(monkeypatch, passes_on=3, note="one symbol is not directly grounded")
    agent = _Agent(cut={"repair-documentation"}, cut_pass=2)

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    assert agent.authored() == 3, agent.counts()
    # The cut turn was not retried, and the pass after it was told why the errors repeat.
    assert agent.counts()["repair-documentation"] == 2, agent.counts()
    brief = agent.author_args()[2]["gate_notes"]
    assert brief.startswith("Your previous turn was stopped at its wall-clock budget"), brief
    # And the gate's own findings are still under it — the prefix explains them, not replaces.
    assert "one symbol is not directly grounded" in brief, brief


def test_a_repair_lap_with_nothing_left_to_edit_keeps_the_nodes_already_named(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The nodes accumulate across passes; the last pass does not replace them.

    `repair`'s brief is "edit the nodes these findings cite", so a lap that correctly
    concludes the finding needs no edit — the symbol was deleted, or is grounded elsewhere
    already — answers `documented` with an empty node list. The nodes are what scopes the
    gate's doctor reading, so taking the last lap's list as the answer would narrow that
    reading to nothing and stop scoring every node an earlier pass had written.
    """
    seen = _stage_gate(monkeypatch, passes_on=2)
    agent = _Agent(nodes_until=1)

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    assert agent.authored() == 2, agent.counts()
    # The second author pass named nothing, and the gate still read the node the first one
    # wrote rather than an empty scope.
    assert [call[7] for call in seen] == [("docs/features/widget.md",)] * 2, seen


def test_the_grounding_failure_names_the_symbols_not_the_files(
    docs: Path,
    logger: logging.Logger,
    write_json: Callable[[Path, Any], Path],
) -> None:
    """The rework brief has to name what the gate actually tested, or the loop cannot end.

    This gate checks `path::symbol` refs and used to report the *files* they live in, which
    made it unwinnable in the one case that matters — a file that is half grounded. The
    author sees the same filename it already wrote a bullet for, adds another plausible
    bullet, and fails on the identical complaint until the four passes are gone; that is
    exactly how the `link-shortener` benchmark run burned its whole rework budget.

    Naming the refs also settles their *spelling*, the second half of the trap: ostler's
    inventory writes a Go method as `(*Type).Method`, so an author writing the natural
    `Type.Method` grounds nothing and no path-level message could ever have said so.

    The gate is called directly here rather than through the flow because the input under
    test is the obligation packet, and in a real `local` run that file is built by
    `ostler qa context` off a diff — a half-grounded Go method is not something the flow
    can be steered into producing.
    """
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
    # The one ungrounded symbol, spelled as the inventory spells it — not `link.go`, and
    # not the receiver-less `LinkController.Resolve` an author would reach for.
    assert f"{controller}::(*LinkController).Resolve" in gate.notes, gate.notes
    # Its already-grounded sibling is not re-litigated, and neither is the file that is
    # wholly settled: everything named is something still owed.
    assert "Create" not in gate.notes, gate.notes
    assert settled not in gate.notes, gate.notes
    # A file the inventory sees no symbols in is still owed *as a path* — the one case
    # where naming the file is naming the reference.
    assert "api/config.yaml" in gate.notes, gate.notes
    assert "2 changed production symbol(s)" in gate.notes, gate.notes
    # The same statement in the form a later pass can be compared against: one entry per
    # owed reference, carrying the inventory's spelling rather than a count. `notes` stays
    # the author's brief and is asserted above unchanged — `failures` is beside it, not
    # instead of it.
    assert sorted(gate.failures) == [
        "G:api/config.yaml",
        f"G:{controller}::(*LinkController).Resolve",
    ], gate.failures


def test_grounding_the_enclosing_unit_grounds_what_is_nested_inside_it(
    docs: Path,
    logger: logging.Logger,
    write_json: Callable[[Path, Any], Path],
) -> None:
    """A nested symbol has no documentable surface of its own, so it cannot be owed alone.

    A React component's every changed line falls inside some local `const`, so the mapper
    charges the story for `Panel.status` and `Panel.el`. Demanding a `code:` bullet per name
    is a demand no book can honestly meet — and a run met it the dishonest way, writing
    bullets that documented local variables as production surface to get past this gate.

    Grounding the owner is the stronger claim, not a weaker one: it says what `Panel` now
    does, which is what a change inside its body actually altered.
    """
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

    # `Badge` is a sibling the book never grounded, so the rollup reaches nothing for it:
    # this closes what an owner covers, it does not forgive an owner that is missing.
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
    """The same trap as the grounding message above, one gate over.

    A doctor finding carries a `suggestion` — the literal bullet the checker would accept —
    and the brief rendered only the complaint about the value it rejected. An author told
    `placement: mostly the middle` is not a placement writes prose again with a percentage in
    it, is refused again, and spends the rework budget inferring a grammar that was sitting
    in the finding all along.
    """
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
    """Nothing is omitted, because omitting is what made the loop.

    The brief used to carry twelve findings and the sentence "rerun the gate for the next
    batch". A story with 124 unparsed `verify:` findings of one shape therefore cost ten
    laps by construction, each one re-reading the book from a fresh session to close a
    twelfth of a list one turn could have walked. The repair prompt now iterates `ostler
    doctor` itself, which only works if it holds the whole set.
    """
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

    assert len(notes.splitlines()) == 41, notes  # the header plus one line per error
    assert "omitted" not in notes, notes
    assert ":39 [unparsed-check]" in notes, notes


def test_an_over_long_doctor_list_is_spilled_to_a_file_the_note_names(
    docs: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    write_json: Callable[[Path, Any], Path],
) -> None:
    """A list too big for an argv becomes a path, never a truncation.

    Both halves matter: the turn still gets every error, and the prompt still fits. A stale
    spill from an earlier pass is removed when the next list is small enough to inline, so
    nothing ever points at a worklist that no longer holds.
    """
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
    # Every identity still travels in `failures`, spilled or not.
    assert len(gate.failures) == gate.doctor_error_count

    # A later pass whose list fits inline clears the stale file rather than leaving it.
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
    """A deletion is satisfied on its own — no `code:` bullet names it, because a live bullet
    pointing at a gone target is exactly what `ostler doctor` rejects as a dangling reference,
    and there is no marker that exempts a ref from having to exist.
    """
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
    """Modified *and* untracked, because the case that motivated this is untracked.

    A story that dies in its docs phase never reaches `commit_story`, so the package it
    wrote stays on disk as untracked files. `git stash create` was the obvious baseline and
    is exactly wrong here: it does not capture untracked paths, i.e. it misses the only
    shape this defect takes.
    """
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
    """The cascade this gate had: one abandoned story disabling it for the whole repo.

    The packet is built `HEAD..WORKTREE`, and the workflow's contract is that a story ends
    in a commit. A story that dies before its commit leaves its production code in the
    tree, and every story selected after it was then held responsible for grounding symbols
    it had never heard of and its book had no reason to mention — the run that forced this
    was a QA-plan fix touching no production code at all, failing on seven Go symbols an
    earlier story had left behind.

    The subtraction is safe in one direction only, which is the third case below: a path
    the story went on to edit no longer matches its recorded bytes and stays owed. The
    filter can shrink by mistake, never grow — a story is never excused from grounding code
    it wrote.
    """
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

    # No snapshot subtracts nothing, which is what the gate did before it existed.
    assert f"{orphan}::Orphan" in _gate(()).notes

    stale = f"{orphan}\0{_sha256(docs / orphan)}"
    assert "not directly grounded" not in _gate((stale,)).notes

    # The same path, edited by this story since the snapshot: back to being its problem.
    (docs / orphan).write_text("package api\n\nfunc Orphan() { println(1) }\n", encoding="utf-8")
    assert f"{orphan}::Orphan" in _gate((stale,)).notes


def test_not_required_is_a_real_answer_and_still_goes_through_the_gate(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """"This story changed nothing the book describes" is a claim, so it is checkable.

    It is exempt from the name-your-nodes rule and from nothing else — it reaches the same
    gate and the same reviewer as a `documented` claim does.
    """
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
    """A blank status fails, and does not spend a rework.

    The refusal is the schema's, not the flow's: `status` is a required `Literal`, so a
    reply carrying none of its three words never becomes a `DocumentationResult` at all.
    There is nothing for a second author pass to be told — the first one did not say what
    stopped it — so looping would be spending turns on the same silence.
    """
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
    """A block is a finding about the story, and it must not take the queue down with it.

    The run that forced this: the author found that the implementation granted every origin
    when `CORS_ALLOWED_ORIGINS` was unset, the opposite of the fail-closed guarantee its own
    plan required, and refused to write the book's claim as true. Correct refusal — and it
    killed the whole run, costing eight epics that had nothing to do with it. The verdict
    comes back for the caller to place instead; the reviewer is never reached, because there
    is nothing written to review.

    The author is consulted on the way out — that is `_blocked` — and this resolver
    escalates, so the verdict is the one the block asked for, unchanged.
    """
    agent = _Agent(author_status="blocked")

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "blocked", result
    assert result.notes == "documented on pass 1", result
    assert agent.counts() == {"document-story": 1, "resolve-operator": 1}, agent.counts()


# --------------------------------------------------------------------- the author's say


def _never_waits(path: Path, **kwargs: Any) -> None:
    """The driver's wait, replaced by the assertion that nothing may reach it."""
    raise AssertionError(f"the flow parked on {path} in auto mode")


class _BlocksOnce(_Agent):
    """An author that refuses the first draft and writes the book once someone decides.

    The shape every real documentation block has: the refusal is not "I cannot write", it is
    "two documents answer this differently and I will not pick one".
    """

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
    """The specs were authored by a workflow, so the author is who ratifies the contract.

    A documentation block is a product decision nobody made — and on a product whose specs
    were themselves written by the author workflow there is no human upstream holding the
    answer. Filing the story as blocked and moving on defers a decision that one turn can
    make, so the flow spends that turn and the guided repair lap writes the book.
    """
    agent = _BlocksOnce(resolver_decision="answered", resolver_answer="One slug per locale.")

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    assert agent.counts() == {
        "document-story": 1,
        "resolve-operator": 1,
        "repair-documentation": 1,
        "review-story-documentation": 1,
    }, agent.counts()
    # The repair lap was told what was ratified, and by whom — not just re-asked. The answer
    # travels verbatim, `STATUS:` line and all, exactly as a human operator would have left it.
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
    """In `auto` mode a resolver that will not decide gives up — it never waits on a person.

    The story drain is single-threaded, so an `Await` here parks every epic queued behind
    this one. The verdict was already survivable; waiting for a human is not.
    """
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
    """The cap is on the resolver, not the block — `MAX_DOCS_BLOCKS` consults, then it stands.

    Each guided lap is the author's answer being applied. If the book still cannot be
    written with it in hand, re-asking the same resolver the same question buys another
    identical answer — so the budget runs out and the deadlock is what the block reports,
    exactly as `MAX_PLAN_BLOCKS` and `MAX_QA_BLOCKS` bound their own lanes.
    """
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
    """`SCOPE: epic` means the decision is bigger than this story, so this story cannot fix it.

    The answer travels out as the verdict's notes rather than being dropped, because the
    caller places the block on the epic and that text is what a human reads there.
    """
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
    """Someone who asked to be asked is asked: no resolver turn, the driver's `Await` instead.

    The auto resolver is a stand-in for the accountable party, and in `human` mode the
    accountable party is present. The recovery path is the same one either way.
    """
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
    # Once per block, on the same budget the resolver spends in `auto` — a person who keeps
    # answering a question the book still cannot be written with is in the same deadlock.
    assert seen == [docs / STORY_REL / "context.md"] * Docs.MAX_DOCS_BLOCKS, seen


# --------------------------------------------------------------------------- the reviewer


def test_a_revision_request_reworks_and_carries_the_notes_forward(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The reviewer's brief reaches the author, and the gate's brief is not dropped for it.

    Both notes are threaded rather than reset, which is what the YAML's two vars did: a later
    pass still shows the author what the reviewer said on an earlier one.
    """
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
    """`blocked` is the reviewer saying no pass will fix this, so spending three is wrong.

    It ends the flow with a verdict rather than an exception, for the reason the author's
    own block does: which story this costs is the caller's call, not the sub-flow's.
    """
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
    """The refusal words are one signal, and the flow no longer has to sort them by spelling.

    `unfixable`, `not_passed` and `invalid` used to reach `status` and fall through to the
    revision arm, which spends the whole rework budget re-asking a question already
    answered and blocks anyway three expensive passes later. The arm reading
    `CoderResult.blocked` caught them; the closed `Literal` means they never arrive, which
    is the earlier and cheaper of the two places to say so.
    """
    agent = _Agent(review_status="unfixable")

    with pytest.raises(WorkflowFailed, match="is not a DocumentationReview"):
        drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert agent.counts()["repair-documentation"] == 0, agent.counts()


class _RefusesWithEvidence(_Agent):
    """A reviewer that refuses *and* names what it read as wrong.

    The realistic shape: a refusal is rarely "I cannot tell", it is "these two documents say
    different things and picking one is not mine to do" — which is a finding with a target.
    """

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
    """A gate that says only "documentation is impossible" is a gate nobody can answer.

    The reviewer that refused still knows *which* contradiction stopped it. Those findings are
    exactly what an operator rules on, so they belong in the body of the question rather than
    in a log line the person reading `context.md` never sees.
    """
    agent = _RefusesWithEvidence()
    asked: list[str] = []

    def _answer(path: Path, **kwargs: Any) -> None:
        # Read before writing: the answer replaces the question in place, so what the
        # operator was shown only exists while they are being asked.
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
    """Both the gate and the reviewer send the book to `repair`, not back to `document`.

    `document`'s brief is "write this story into the book". Handed that instruction plus a
    finding against one bullet, the author revisits nodes nobody complained about — so the
    `power="high"` reviewer meets a changed book each round and, correctly, finds a
    different real defect in it. Only the first pass may be an authoring pass.
    """
    _stage_gate(monkeypatch, passes_on=2)
    agent = _Agent(approve_after=3)

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["document-story"] == 1, agent.counts()
    # One grounding repair, then two the reviewer asked for.
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
    """A nonempty findings list cannot bypass the actionable-fields gate.

    `kind` is required and closed, so the finding carries one — everything the repair turn
    would actually act on is still blank, which is what the gate below reads.
    """
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
    """The id only has to name the same defect twice — no consumer parses its shape.

    The prompt suggests `D1`, and a reviewer that answers `F1` is not reporting a
    malformed review. Enforcing the suggestion raised `WorkflowFailed` out of an
    otherwise routine revise pass and killed the whole coder run with it.
    """
    agent = _Agent(approve_after=2, review_findings=[_finding("F1")])

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    assert agent.authored() == 2, agent.counts()
    second = agent.author_args()[1]
    assert "F1 [overclaim] docs/features/widget.md#f1" in second["review_notes"]


def test_the_loop_is_bounded_at_four_passes(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A reviewer that never approves stops the flow rather than the run.

    Four author passes, not three: `MAX_REWORKS` counts reworks, and the first pass is not
    one. That is the literal `"3"` the YAML's `guard_documentation` compared against.

    The exhausted budget is a `blocked` verdict, not an exception, and that distinction is
    the whole point: it used to raise, and the run that forced this change spent it on the
    `finalize` pass — so a story already implemented, reviewed, documented and QA-passed
    was thrown away uncommitted, along with every epic queued behind it, over one prose
    finding a fifth pass might have closed.
    """
    agent = _Agent(approve_after=99)

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "blocked", result
    assert "review did not converge in 4 passes" in result.notes
    assert agent.counts() == {
        "document-story": 1,
        "repair-documentation": 3,
        "review-story-documentation": 4,
        "resolve-operator": 1,
    }, agent.counts()


def test_a_gate_that_never_passes_is_bounded_on_its_own_budget(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A book the gate never passes never reaches the reviewer — and still blocks, not fails.

    The exhausted grounding budget is a `blocked` verdict, not an exception, the same
    distinction `test_the_loop_is_bounded_at_four_passes` draws for the reviewer's own budget:
    the resolver is consulted in the author's stead before the story ends blocked.
    """
    _stage_gate(monkeypatch, passes_on=None)
    agent = _Agent()

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "blocked", result
    assert "did not converge in 4 grounding passes" in result.notes, result.notes
    assert agent.counts() == {
        "document-story": 1,
        "repair-documentation": 3,
        "resolve-operator": 1,
    }, agent.counts()



def test_the_gates_failure_does_not_spend_the_reviewers_budget(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One mechanical grounding fix must not cost a semantic round.

    The YAML spent one `documentation_rework_count` on both, so this shape — a first pass
    that names no node, then a reviewer that finds a real, distinct, fixable defect each
    round — raised on the third refusal with the book one edit from conformant. That is a
    two-language schema story from a real run, not a hypothetical: the grounding gate is
    deterministic and converges in a pass or two, while `review-story-documentation` is a
    `power="high"` read, and letting the cheap loop draw on the expensive one's budget
    starves it.
    """
    _stage_gate(monkeypatch, passes_on=2)
    agent = _Agent(approve_after=4)

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    assert agent.counts() == {
        "document-story": 1,
        "repair-documentation": 4,
        "review-story-documentation": 4,
    }, agent.counts()


# --------------------------------------------------------------------- was it productive?


def _finding(fid: str) -> dict[str, Any]:
    """One well-formed reviewer finding, distinguished from the next only by its id."""
    return {
        "id": fid,
        "kind": "overclaim",
        "target": f"docs/features/widget.md#{fid.lower()}",
        "issue": f"{fid} is not described",
        "repair": f"Document {fid}",
    }


def test_a_reviewer_handing_back_the_same_worklist_exhausts_as_stalled(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Four passes, one worklist, nothing closed — the budget was not the problem.

    This is the shape `docs.rework=3` alone cannot distinguish from its opposite below, and
    the two want opposite interventions: this one wants the author's prompt fixed, not a
    bigger budget. The verdict rides the reworked author turns as a span label; the run's
    last pass causes no work, so it is carried in the blocking notes instead.
    """
    agent = _Agent(approve_after=99, findings_per_pass=[[_finding("D1"), _finding("D2")]])

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "blocked", result
    assert "did not converge in 4 passes (stalled)" in result.notes, result.notes


def test_a_reviewer_closing_each_worklist_and_opening_another_exhausts_as_churned(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The same four passes and the same two findings a pass — and a different diagnosis.

    Every pass closed the brief it was given and the reviewer found new, distinct defects,
    so the loop was productive and merely unfinished. `_rework`'s own docstring records the
    run this happened on. A count of reworks scores it identically to the stall above.
    """
    agent = _Agent(
        approve_after=99,
        findings_per_pass=[
            [_finding("D1"), _finding("D2")],
            [_finding("D3"), _finding("D4")],
            [_finding("D5"), _finding("D6")],
            [_finding("D7"), _finding("D8")],
        ],
    )

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "blocked", result
    assert "did not converge in 4 passes (churned)" in result.notes, result.notes


def test_the_grounding_lane_carries_its_own_verdict_into_the_block(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A gate handing back the identical failure every pass says so in the block's notes."""
    _stage_gate(monkeypatch, passes_on=None)
    agent = _Agent()

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "blocked", result
    assert "4 grounding passes (stalled)" in result.notes, result.notes


def test_a_shrinking_failure_set_no_longer_waives_the_grounding_budget(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Closing one error a lap is the loop, not a licence to keep laping.

    `verify` used to waive `MAX_REWORKS` for as long as the pass had *reduced* the failure
    set. That is exactly the shape a batched worklist produces — the gate handed over twelve
    of 124 findings and the sentence "rerun the gate for the next batch", so every lap
    reduced, the budget never applied, and one story of one error shape cost ten fresh
    sessions. The gate now hands over all of them and the repair prompt iterates `ostler
    doctor` to zero inside the turn, so a lap that still comes back red has spent a real
    pass and the budget is what bounds it.
    """
    outstanding = [
        ["E:a", "E:b", "E:c", "E:d"],
        ["E:a", "E:b", "E:c"],
        ["E:a", "E:b"],
        ["E:a"],
        [],
    ]

    @blueprint.node
    def _gate(*args: Any, **kwargs: Any) -> DocumentationGate:
        failures = outstanding.pop(0)
        return DocumentationGate(
            status="invalid" if failures else "passed",
            notes="synthetic doctor findings",
            failures=failures,
        )

    monkeypatch.setattr(docs_flow, "verify_story_documentation", _gate)

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), _Agent())

    assert result.status == "blocked", result
    assert "did not converge in 4 grounding passes" in result.notes, result.notes
    # The fifth, passing verdict is never reached: the budget stopped the story on the
    # fourth author pass even though every lap had closed a finding.
    assert outstanding == [[]]


# --------------------------------------------------------------------------- resume


def test_a_run_killed_mid_review_resumes_without_re_documenting(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The reason `document`, `verify` and `review` are three states rather than one.

    The author turn is the expensive thing in this loop and the checkpoint is written before
    a state runs, so a kill after the gate re-enters at the reviewer with the author's result
    revived from JSON — not at a second author pass.
    """
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
    """The baseline a progress verdict is measured against has to survive the kill.

    A verdict comparing this pass to the last one is only as durable as the last pass's
    worklist, and that worklist lives nowhere but the state parameter — which is exactly
    why it is one. Without this, every resume would report `first_pass` and a run that died
    once would score as productive no matter what it did afterwards.
    """
    run_env = env()
    run_dir = run_env.writer.run_dir

    # The kill lands on the *second* author turn, which is a repair and not a re-author.
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
