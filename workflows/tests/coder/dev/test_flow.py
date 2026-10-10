"""End-to-end tests for the `dev` flow: one dev turn, then the plan, gate and answer checks."""
from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from workhorse.pyflow import park as pyflow_park
from workhorse.pyflow.engine import RunEnv

from workhorse_workflows.coder.dev.flow import Dev
from workhorse_workflows.coder.shared.owner import MAX_LAPS
from workhorse_workflows.coder.shared import commits
from workhorse_workflows.coder.shared.schemas.dev_story import DevOutcome
from workhorse_workflows.kit.git import commit_all

EPIC = "EPIC-1"
STORY = "STORY-1"

INDEX = f"""# Epics

The epic queue, front first.

- [{EPIC}]({EPIC}/epic.md) — Epic One
"""

STORY_MD = """---
type: story
---

# Story STORY-1

## Dependencies

(none)

## Fixtures

(none)

## Context

Users need links that only point inside the site.

## Acceptance Criteria

- a relative link destination is rejected

## Non-Functional Acceptance Criteria

(none)

## Technical Notes

- the check lives in the api's link validator

## Implementation Status

- **Status**: Not started
"""

RED_MAKEFILE = "lint:\n\t@echo 'links.go:1: undefined: allowList'; exit 1\n"

TEST_NAME = "TestRejectsRelativeDestination"

BLOCK_NOTE = "nobody has said whether a protocol-relative link counts as relative"

OPERATOR_ANSWER = "A protocol-relative link counts as external, so reject it."

API_SERVICE: dict[str, Any] = {
    "repo": "api",
    "path": ".",
    "type": "go",
    "plan_file": "plan-api.md",
}

FINDINGS: list[dict[str, Any]] = [
    {
        "target": "api/links.go:3",
        "issue": "a destination starting with `//` passes as internal",
        "repair": "treat a protocol-relative destination as external",
        "category": "Bug",
        "score": 90,
    },
    {
        "target": "api/links.go:1",
        "issue": "the validator could reuse the url package's parser",
        "repair": "parse with net/url",
        "category": "Reuse",
        "score": 40,
    },
]


@pytest.fixture
def docs(
    repo: Path,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
) -> Path:
    """The docs repo, carrying one epic with one story, committed so the tree starts clean."""
    write(
        repo / "docs" / "epics" / EPIC / "epic.md",
        f"---\ntitle: Epic One\nstatus: active\n---\n\n# Epic One\n\n## Stories\n\n"
        f"### {STORY}\n\n- title: Story {STORY}\n",
    )
    write(repo / "docs" / "epics" / EPIC / "stories" / STORY / "story.md", STORY_MD)
    write(repo / "docs" / "epics" / "index.md", INDEX)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "Queue one epic")
    return repo


@pytest.fixture
def workspace(
    tmp_path: Path,
    docs: Path,
    git: Callable[..., subprocess.CompletedProcess],
    write: Callable[[Path, str], Path],
    ambient: dict[str, str],
) -> dict[str, Path]:
    """One real code repo and the workspace file that names it, outside the docs tree."""
    root = tmp_path / "ws"
    api = root / "api"
    api.mkdir(parents=True)
    git(api, "init", "-q", "-b", "main")
    write(api / "README.md", "# api\n")
    git(api, "add", "-A")
    git(api, "commit", "-qm", "Initial commit")
    write(root / "acme.code-workspace", json.dumps({"folders": [{"name": "api", "path": "api"}]}))
    ambient["workspace_file"] = str(root / "acme.code-workspace")
    return {"api": api}


class _Agent:
    """The dev turn and the resolver, scripted on the flow's arms."""

    def __init__(
        self,
        workspace: dict[str, Path],
        *,
        blocked: int = 0,
        red: int = 0,
        unanswered: int = 0,
        stray: int = 0,
    ) -> None:
        self.workspace = workspace
        self.blocked = blocked
        self.red = red
        self.unanswered = unanswered
        self.stray = stray
        self.prefix = ""
        self.calls: list[str] = []
        self.args: list[dict[str, Any]] = []

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        stem = Path(node.prompt).stem
        data = ctx.as_dict()
        self.calls.append(stem)
        self.args.append(data)
        handler = getattr(self, f"_{stem.replace('-', '_')}")
        return f"(scripted) {node.prompt}", handler(data, self.counts()[stem])

    def counts(self) -> Counter[str]:
        return Counter(self.calls)

    def args_for(self, stem: str) -> list[dict[str, Any]]:
        return [a for s, a in zip(self.calls, self.args, strict=True) if s == stem]

    def _dev_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """Build, commit, write the plan and the answers, and report the review's findings once."""
        if nth <= self.blocked:
            return {"status": "blocked", "notes": BLOCK_NOTE}
        spec = Path(str(data["spec_dir"]))
        spec.mkdir(parents=True, exist_ok=True)
        (spec / "plan.md").write_text("# Plan\n\nReject relative links in the api.\n", encoding="utf-8")
        (spec / "plan-api.md").write_text("# Plan: api\n\nValidate in links.go.\n", encoding="utf-8")
        repo = self.workspace["api"]
        (repo / "links.go").write_text(f"package links\n\n// pass {nth}\n", encoding="utf-8")
        (repo / "links_test.go").write_text(
            f"package links\n\nfunc {TEST_NAME}(t *testing.T) {{}}\n", encoding="utf-8"
        )
        makefile = repo / "Makefile"
        if nth <= self.red:
            makefile.write_text(RED_MAKEFILE, encoding="utf-8")
        elif makefile.exists():
            makefile.unlink()
        message = commits.message(
            "feat",
            commits.scope(repo.name),
            "reject relative link destinations",
            epic=str(data["epic"]),
            story=str(data["story_id"]),
        )
        commit_all(repo, message)
        if nth <= self.stray:
            (repo / "scratch.go").write_text("package links\n", encoding="utf-8")
        first = not self.prefix
        if first:
            self.prefix = str(data["review_prefix"])
        if nth > self.unanswered:
            sha = _head(repo)
            Path(str(data["answers_file"])).write_text(
                f"## {self.prefix}1: fixed\n"
                f"- commit: {sha}\n"
                "- path: api/links.go\n"
                f"- test: {TEST_NAME}\n\n"
                f"## {self.prefix}2: declined\n"
                "Reason: the story's technical notes keep the validator free of new imports.\n",
                encoding="utf-8",
            )
        return {
            "status": "ready",
            "summary": "reject relative link destinations in the api",
            "notes": f"built and reviewed on pass {nth}",
            "services": [API_SERVICE],
            "findings": FINDINGS if first else [],
        }

    def _resolve_operator(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """The resolver's say on a block, which this fake declines to give."""
        return {"decision": "escalated", "summary": "only the operator can decide this"}


def _answers(seen: list[str]) -> Callable[..., None]:
    """A stand-in for the human the `Await` is waiting on."""

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text(encoding="utf-8"))
        path.write_text(f"STATUS: ANSWERED\n\n{OPERATOR_ANSWER}\n", encoding="utf-8")

    return answered


def _head(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _dev(docs: Path, operator_mode: str = "auto") -> Dev:
    return Dev(story=STORY, epic=EPIC, docs_path=str(docs), operator_mode=operator_mode)


def test_a_clean_pass_settles_the_fix_and_records_the_decline(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """One ready turn with a fixed and a declined answer finishes the run on its first check."""
    agent = _Agent(workspace)

    result = drive_flow(_dev(docs), env(), agent)

    assert isinstance(result, DevOutcome), result
    assert result.status == "ready", result
    assert result.settled == [f"{STORY}/review-1.1"], result
    assert result.declined == [f"{STORY}/review-1.2"], result
    assert agent.counts() == {"dev-story": 1}, agent.counts()

    (first,) = agent.args_for("dev-story")
    assert str(first["review_prefix"]).endswith("/review-1."), first
    assert first["review_prefix"] == f"{STORY}/review-1.", first
    assert first["report"] == "", first
    assert first["operator_context"] == "", first


def test_a_red_gate_sends_its_output_back_and_a_green_turn_finishes(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The check's failure is the next turn's report, and the run ends once the gates pass."""
    agent = _Agent(workspace, red=1)

    result = drive_flow(_dev(docs), env(), agent)

    assert result.status == "ready", result
    assert result.settled == [f"{STORY}/review-1.1"], result
    assert result.declined == [f"{STORY}/review-1.2"], result
    assert agent.counts() == {"dev-story": 2}, agent.counts()

    first, second = agent.args_for("dev-story")
    assert first["report"] == "", first
    report = str(second["report"])
    assert report.startswith("Gate: "), report
    assert "lint" in report, report
    assert "undefined: allowList" in report, report


def test_an_unanswered_finding_comes_back_named_in_the_report(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A finding with no section in the answer file stays open and buys another turn."""
    agent = _Agent(workspace, unanswered=1)

    result = drive_flow(_dev(docs), env(), agent)

    assert result.settled == [f"{STORY}/review-1.1"], result
    assert result.declined == [f"{STORY}/review-1.2"], result
    assert agent.counts() == {"dev-story": 2}, agent.counts()

    second = agent.args_for("dev-story")[1]
    report = str(second["report"])
    assert "Answers: 2 finding(s) are still open." in report, report
    assert f"`{STORY}/review-1.1`" in report, report
    assert f"`{STORY}/review-1.2`" in report, report
    assert f"{STORY}/review-1.1" in str(second["findings"]), second


def test_a_blocked_turn_in_human_mode_parks_and_resumes_with_the_answer(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A human operator is asked directly, and the answer reaches the next dev turn."""
    agent = _Agent(workspace, blocked=1)
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", _answers(seen)):
        result = drive_flow(_dev(docs, operator_mode="human"), env(), agent)

    assert result.status == "ready", result
    (gate,) = seen
    assert BLOCK_NOTE in gate, gate
    assert agent.counts() == {"dev-story": 2}, agent.counts()

    first, second = agent.args_for("dev-story")
    assert first["operator_context"] == "", first
    assert OPERATOR_ANSWER in str(second["operator_context"]), second


def test_checks_that_stay_red_past_the_lap_budget_park_instead_of_failing(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A spent repair budget is a block: the resolver escalates, and the answer resumes the dev owner."""
    agent = _Agent(workspace, red=MAX_LAPS + 1)
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", _answers(seen)):
        result = drive_flow(_dev(docs), env(), agent)

    assert result.status == "ready", result
    assert agent.counts() == {"dev-story": MAX_LAPS + 2, "resolve-operator": 1}, agent.counts()

    (gate,) = seen
    assert f"The checks still fail after {MAX_LAPS} repair turn(s)." in gate, gate
    assert "undefined: allowList" in gate, gate

    turns = agent.args_for("dev-story")
    assert all(t["report"] for t in turns[1 : MAX_LAPS + 1]), turns
    assert OPERATOR_ANSWER in str(turns[-1]["operator_context"]), turns[-1]


def test_work_the_turn_left_uncommitted_comes_back_named_in_the_report(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A path the story wrote and did not commit fails the check, so the owner records it."""
    agent = _Agent(workspace, stray=1)

    result = drive_flow(_dev(docs), env(), agent)

    assert result.status == "ready", result
    assert agent.counts() == {"dev-story": 2}, agent.counts()
    report = str(agent.args_for("dev-story")[1]["report"])
    assert "Uncommitted work" in report, report
    assert "scratch.go" in report, report
    assert subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=workspace["api"], check=True, capture_output=True, text=True,
    ).stdout == ""


def test_a_path_dirty_before_the_story_began_is_not_the_story_s_to_commit(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`preexisting` is subtracted, so the operator's own edit costs the owner no turn."""
    mine = workspace["api"] / "notes.go"
    mine.write_text("package links\n", encoding="utf-8")
    entry = f"notes.go\0{hashlib.sha256(mine.read_bytes()).hexdigest()}"
    agent = _Agent(workspace)
    dev = _dev(docs).model_copy(update={"preexisting": (entry,)})

    result = drive_flow(dev, env(), agent)

    assert result.status == "ready", result
    assert agent.counts() == {"dev-story": 1}, agent.counts()
    assert mine.exists()
