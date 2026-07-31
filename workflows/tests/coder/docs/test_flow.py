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
"""
from __future__ import annotations

import json
import subprocess
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from workhorse.artifacts import ArtifactWriter
from workhorse.pyflow import WorkflowFailed
from workhorse.pyflow.driver import read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import parse_checkpoint

from workhorse_workflows.coder.docs.flow import Docs
from workhorse_workflows.coder.shared.docs import (
    classify_documentation_context,
    verify_story_documentation,
)
from workhorse_workflows.coder.shared.okf import build_okf_context, validate_okf_context

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

    `author_status`/`author_nodes` are the claim the gate checks — `nodes_after` is the pass
    from which the author starts naming what it touched, which is how a gate failure and its
    recovery are separable. `review_status` is the reviewer's verdict, `approve_after` the
    pass it stops asking for revisions on.
    """

    def __init__(
        self,
        *,
        author_status: str = "documented",
        author_nodes: tuple[str, ...] = ("docs/features/widget.md",),
        nodes_after: int = 1,
        review_status: str = "approved",
        approve_after: int = 1,
        explode: set[str] | None = None,
    ) -> None:
        self.author_status = author_status
        self.author_nodes = author_nodes
        self.nodes_after = nodes_after
        self.review_status = review_status
        self.approve_after = approve_after
        self.explode = explode or set()
        self.calls: list[str] = []
        self.args: list[dict[str, Any]] = []

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

    def _document_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return {
            "status": self.author_status,
            "nodes": list(self.author_nodes) if nth >= self.nodes_after else [],
            "notes": f"documented on pass {nth}",
        }

    def _review_story_documentation(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if nth >= self.approve_after:
            return {"status": self.review_status, "notes": "reads as built"}
        return {"status": "revise", "notes": "the widget's states are not described"}


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


# --------------------------------------------------------------------------- the gate


def test_a_documented_claim_naming_no_nodes_is_sent_back(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The gate's cheapest check, and the one the reviewer could never make.

    An author that says it documented the story but cannot name a node it touched has
    reported success without evidence. That is a rework brief, not a review.
    """
    agent = _Agent(nodes_after=2)

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    assert agent.counts()["document-story"] == 2, agent.counts()
    # The reviewer never saw the first pass: the gate is upstream of it.
    assert agent.counts()["review-story-documentation"] == 1, agent.counts()
    # And the second author pass was told exactly what was wrong with the first.
    assert "did not identify affected OKF nodes" in agent.args_for("document-story")[1][
        "gate_notes"
    ]


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
    """`blocked` and a blank both fail, and neither spends a rework.

    There is no brief to hand a second author pass — the first one did not say what stopped
    it — so looping would be spending turns on the same silence.
    """
    agent = _Agent(author_status="blocked")

    with pytest.raises(WorkflowFailed, match="documentation author reported blocked"):
        drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert agent.counts()["document-story"] == 1, agent.counts()


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
    assert agent.counts() == {"document-story": 2, "review-story-documentation": 2}
    second = agent.args_for("document-story")[1]
    assert second["review_notes"] == "the widget's states are not described"
    assert "direct OKF grounding" in second["gate_notes"]


def test_a_blocked_review_fails_rather_than_reworking(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`blocked` is the reviewer saying no pass will fix this, so spending three is wrong."""
    agent = _Agent(review_status="blocked")

    with pytest.raises(WorkflowFailed, match="documentation review blocked"):
        drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert agent.counts()["document-story"] == 1, agent.counts()


def test_the_loop_is_bounded_at_four_passes(
    docs: Path,
    elsewhere: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A reviewer that never approves stops the flow rather than the run.

    Four author passes, not three: `MAX_REWORKS` counts reworks, and the first pass is not
    one. That is the literal `"3"` the YAML's `guard_documentation` compared against.
    """
    agent = _Agent(approve_after=99)

    with pytest.raises(WorkflowFailed, match="did not converge in 4 passes"):
        drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert agent.counts() == {"document-story": 4, "review-story-documentation": 4}


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
    assert resume.params["rework"] == 0, resume.params
    assert resume.params["author"]["nodes"] == ["docs/features/widget.md"], resume.params

    agent = _Agent()
    result = drive_flow(Docs(**resume.inputs), env(run_dir=run_dir), agent, resume)

    assert result.status == "passed", result
    assert agent.counts() == {"review-story-documentation": 1}, agent.counts()
