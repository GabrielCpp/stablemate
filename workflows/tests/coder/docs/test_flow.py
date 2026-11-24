"""Composition and direct-state tests for the `docs` flow."""
from __future__ import annotations

import json
import shutil
import subprocess
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from workhorse._vendor.stablemate_core import config as core_config
from workhorse.artifacts import ArtifactWriter
from workhorse.pyflow import WorkflowFailed
from workhorse.pyflow import park as pyflow_park
from workhorse.pyflow.driver import read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import parse_checkpoint
from workhorse.runner.failure import TurnDeadlineExceeded

import workhorse_workflows.coder.book_qa.nodes as book_nodes
from workhorse_workflows.coder.docs.flow import Docs
from workhorse_workflows.coder.shared.owner import MAX_BLOCKS, MAX_LAPS
from workhorse_workflows.coder.shared.schemas.book_qa import BookPlay
from _epics import epics_root
from _workspace import Workspace

STORY = "STORY-1"
EPIC = "EPIC-1"


def spec_dir() -> Path:
    """The story's spec folder under this test's artifacts dir."""
    return core_config.resolve_artifacts_dir() / "specs" / STORY

STORY_REL = f"{EPIC}/stories/{STORY}"
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
id: STORY-1
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
    write(epics_root() / EPIC / "epic.md", EPIC_MD)
    write(epics_root() / STORY_REL / "story.md", STORY_MD)
    write(repo / spec_dir() / "plan-context.json", json.dumps(_plan_context("api"), indent=2))
    return repo


@pytest.fixture
def alongside(
    tmp_path: Path,
    docs: Path,
    git: Callable[..., subprocess.CompletedProcess],
    write: Callable[[Path, str], Path],
    name_workspace: Callable[[dict[str, Path]], None],
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """The docs repo *is* the code repo — the single-worktree shape, i.e."""
    (docs / spec_dir() / "plan-context.json").write_text(
        json.dumps(_plan_context("acme"), indent=2), encoding="utf-8"
    )
    name_workspace({"acme": docs})
    shutil.copytree(epics_root(), docs / "epics")
    monkeypatch.setenv("STABLEMATE_ARTIFACTS_DIR", str(docs))
    git(docs, "commit", "-q", "--allow-empty", "-m", f"feat: seed\n\nStory: {STORY}")
    return docs


def _served_by(root: Path, write: Callable[[Path, str], Path], *services: str, covered: tuple[str, ...], under: str = "services") -> None:
    """Name the story's services, and give each covered one an executable book."""
    write(
        epics_root() / STORY_REL / "story.md",
        STORY_MD.replace("type: story\n", f"type: story\nservices: [{', '.join(services)}]\n"),
    )
    for name in covered:
        write(root / under / name / "service.py", "SERVICE = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "the story and its books"], cwd=root, check=True)


class _Checks:
    """The book tool's `check`, scripted by the exit code of each call."""

    def __init__(self, *exits: int) -> None:
        self.exits = list(exits)
        self.argv: list[list[str]] = []

    def __call__(self, argv: list[str], cwd: Path) -> BookPlay:
        self.argv.append(argv)
        code = self.exits.pop(0) if self.exits else 0
        return BookPlay(exit_code=code, output="" if code == 0 else "claim unreadable")


@pytest.fixture
def booked(
    docs: Path,
    alongside: Path,
    write: Callable[[Path, str], Path],
    monkeypatch: pytest.MonkeyPatch,
) -> _Checks:
    """A story naming `api`, whose executable book exists and checks green."""
    _served_by(docs, write, "api", covered=("api",))
    checks = _Checks()
    monkeypatch.setattr(book_nodes, "_play", checks)
    return checks


class _Agent:
    """The owner turn and the resolver, scripted on the axes the states branch on."""

    def __init__(
        self,
        *,
        author_status: str = "documented",
        blocked: int = 0,
        explode: set[str] | None = None,
        explode_after: int = 1,
        resolver_decision: str = "escalated",
        resolver_answer: str = "",
        resolver_scope: str = "story",
        cut: tuple[str, ...] = (),
    ) -> None:
        self.cut = set(cut)
        self.nodes: list[Any] = []
        self.kwargs: list[dict[str, Any]] = []
        self.author_status = author_status
        self.blocked = blocked
        self.explode = explode or set()
        self.explode_after = explode_after
        self.resolver_decision = resolver_decision
        self.resolver_answer = resolver_answer
        self.resolver_scope = resolver_scope
        self.calls: list[str] = []
        self.args: list[dict[str, Any]] = []

    AUTHOR_STEM = "specify-story"

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        stem = Path(node.prompt).stem
        data = ctx.as_dict()
        self.calls.append(stem)
        self.args.append(data)
        nth = self.counts()[stem]
        self.nodes.append(node)
        self.kwargs.append(kwargs)
        if stem in self.cut:
            self.cut.discard(stem)
            raise TurnDeadlineExceeded(stem, node.deadline, node.deadline + 1.0)
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

    def _specify_story(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if nth <= self.blocked:
            return {"status": "blocked", "notes": BLOCK_NOTE}
        return {"status": self.author_status, "notes": f"specified on pass {nth}"}

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


def test_an_unresolvable_story_fails_before_anything_else(
    docs: Path,
    alongside: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A blank slug resolves to no story path, and documenting nothing is not a success."""
    with pytest.raises(WorkflowFailed, match="nothing to document"):
        drive_flow(Docs(), env(), _Agent())


def test_a_story_naming_a_service_without_a_book_stops_before_the_spec_turn(
    docs: Path,
    alongside: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    write: Callable[[Path, str], Path],
) -> None:
    _served_by(docs, write, "api", "web", covered=("api",))
    agent = _Agent()

    with pytest.raises(WorkflowFailed) as refused:
        drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert "`web`" in str(refused.value) and "`api`" not in str(refused.value), refused.value
    assert "workhorse-okf-book run python_book" in str(refused.value), refused.value
    assert agent.counts() == {}, agent.counts()


def test_in_a_workspace_a_story_whose_book_is_in_the_artifacts_folder_is_not_refused(
    workspace: Workspace,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    write: Callable[[Path, str], Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write(epics_root() / EPIC / "epic.md", EPIC_MD)
    write(spec_dir() / "plan-context.json", json.dumps(_plan_context("api"), indent=2))
    _served_by(workspace.artifacts, write, "api", covered=("api",), under="services/api")
    monkeypatch.setattr(book_nodes, "_play", _Checks())

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), _Agent())

    assert result.status == "passed", result


def test_a_story_whose_book_is_missing_is_refused_naming_where_the_book_goes(
    workspace: Workspace,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    write: Callable[[Path, str], Path],
) -> None:
    write(epics_root() / EPIC / "epic.md", EPIC_MD)
    write(spec_dir() / "plan-context.json", json.dumps(_plan_context("api"), indent=2))
    write(
        epics_root() / STORY_REL / "story.md",
        STORY_MD.replace("type: story\n", "type: story\nservices: [api]\n"),
    )

    with pytest.raises(WorkflowFailed) as refused:
        drive_flow(Docs(story=STORY, epic=EPIC), env(), _Agent())

    assert f"{workspace.artifacts}/services/api/<name>/service.py" in str(refused.value), refused.value


def test_a_surface_book_under_a_service_is_a_book(
    docs: Path,
    alongside: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    write: Callable[[Path, str], Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _served_by(docs, write, "api", "web", covered=("api",))
    write(docs / "services" / "web" / "http" / "service.py", "SERVICE = 1\n")
    monkeypatch.setattr(book_nodes, "_play", _Checks())
    agent = _Agent()

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    assert agent.authored() == 1, agent.counts()


def test_a_story_naming_no_service_is_not_applicable_with_no_turn(
    docs: Path,
    alongside: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = _Agent()

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "not_applicable", result
    assert agent.counts() == {}, agent.counts()


def test_the_spec_pass_writes_the_book_before_any_diff_exists(
    docs: Path,
    booked: _Checks,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = _Agent()

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    assert [argv[2:] for argv in booked.argv] == [
        ["ostler.book", "check", "services.api", "--app", str(docs)]
    ]
    assert agent.counts() == {"specify-story": 1}
    brief = agent.author_args()[0]
    assert brief["epic_path"].endswith(f"{EPIC}/epic.md"), brief
    assert brief["book_services"] == ["api"], brief
    assert "markdown_services" not in brief and "services_root" not in brief, brief


def test_not_required_is_a_real_answer_and_still_goes_through_the_book_check(
    booked: _Checks,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = _Agent(author_status="not_required")

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    assert len(booked.argv) == 1, booked.argv


def test_a_red_book_check_sends_the_spec_pass_back_with_its_output(
    docs: Path,
    alongside: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    write: Callable[[Path, str], Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _served_by(docs, write, "api", covered=("api",))
    monkeypatch.setattr(book_nodes, "_play", _Checks(1, 0))
    agent = _Agent()

    result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    assert agent.counts() == {"specify-story": 2}
    report = agent.author_args()[1]["report"]
    assert "`ostler book check services.api` exited 1" in report and "claim unreadable" in report


def test_checks_that_stay_red_past_the_lap_budget_park_instead_of_failing(
    docs: Path,
    alongside: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    write: Callable[[Path, str], Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A spent repair budget is a block: the resolver escalates, and the answer resumes the owner."""
    _served_by(docs, write, "api", covered=("api",))
    monkeypatch.setattr(book_nodes, "_play", _Checks(*([1] * (MAX_LAPS + 1))))
    agent = _Agent()
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", _answers(seen)):
        result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    assert agent.counts() == {"specify-story": MAX_LAPS + 2, "resolve-operator": 1}
    (gate,) = seen
    assert f"The checks still fail after {MAX_LAPS} repair turn(s)." in gate, gate
    assert "claim unreadable" in gate, gate
    turns = agent.author_args()
    assert all(t["report"] for t in turns[1 : MAX_LAPS + 1]), turns
    assert OPERATOR_ANSWER in turns[-1]["operator_context"], turns[-1]


def test_an_owner_that_did_not_speak_fails_the_flow(
    booked: _Checks,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A blank status fails, and does not spend a lap."""
    agent = _Agent(author_status="")

    with pytest.raises(WorkflowFailed, match="is not a SpecResult"):
        drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert agent.authored() == 1, agent.counts()


def test_a_block_the_resolver_cannot_answer_parks_and_resumes_with_the_answer(
    booked: _Checks,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """In `auto` mode an escalating resolver hands the block to a person, and the lane waits."""
    agent = _Agent(blocked=1)
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", _answers(seen)):
        result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    assert agent.counts() == {"specify-story": 2, "resolve-operator": 1}, agent.counts()
    (gate,) = seen
    assert BLOCK_NOTE in gate, gate
    first, second = agent.author_args()
    assert first["operator_context"] == "", first
    assert OPERATOR_ANSWER in second["operator_context"], second


def test_a_block_is_put_to_the_author_before_anyone_is_asked(
    booked: _Checks,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The specs were authored by a workflow, so the author is who ratifies the contract."""
    agent = _Agent(blocked=1, resolver_decision="answered", resolver_answer=OPERATOR_ANSWER)

    with patch.object(pyflow_park, "wait_for_answer", _never_waits):
        result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    assert agent.counts() == {"specify-story": 2, "resolve-operator": 1}, agent.counts()
    assert OPERATOR_ANSWER in agent.author_args()[1]["operator_context"]


def test_the_author_is_consulted_on_a_budget_and_a_person_after_it(
    booked: _Checks,
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
        "specify-story": MAX_BLOCKS + 2,
        "resolve-operator": MAX_BLOCKS,
    }, agent.counts()
    assert len(seen) == 1, seen


def test_an_epic_scoped_answer_blocks_the_story_with_the_answer_as_the_finding(
    booked: _Checks,
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
    assert agent.counts() == {"specify-story": 1, "resolve-operator": 1}, agent.counts()


def test_operator_mode_human_waits_for_a_person(
    booked: _Checks,
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
    assert agent.counts() == {"specify-story": 2}, agent.counts()
    assert paths == [epics_root() / STORY_REL / "context.md"], paths


def test_a_docs_turn_cut_at_its_deadline_parks_and_resumes_on_the_same_session(
    booked: _Checks,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = _Agent(cut=("specify-story",))
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", _answers(seen)):
        result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    (gate,) = seen
    assert "was cut after 180 minutes" in gate, gate
    assert "Its session is kept" in gate, gate
    assert "resolve-operator" not in agent.calls, agent.calls
    first, second = agent.kwargs[0], agent.kwargs[1]
    assert first["session_chain"] == second["session_chain"] != ""
    assert second["resume_session"] is True
    assert OPERATOR_ANSWER in agent.author_args()[1]["operator_context"]
    assert agent.nodes[0].deadline == agent.nodes[0].timeout == 10800.0


def test_a_cut_resolver_turn_lands_on_the_gate(
    booked: _Checks,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = _Agent(blocked=1, cut=("resolve-operator",))
    seen: list[str] = []

    with patch.object(pyflow_park, "wait_for_answer", _answers(seen)):
        result = drive_flow(Docs(story=STORY, epic=EPIC), env(), agent)

    assert result.status == "passed", result
    (gate,) = seen
    assert BLOCK_NOTE in gate, gate
    assert "The resolver turn was cut after 180 minutes" in gate, gate


def test_turn_minutes_sets_the_owner_deadline(
    booked: _Checks,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = _Agent()

    drive_flow(Docs(story=STORY, epic=EPIC, turn_minutes=7), env(), agent)

    assert agent.nodes[0].deadline == agent.nodes[0].timeout == 420.0


def test_a_run_killed_mid_repair_resumes_knowing_what_was_outstanding(
    docs: Path,
    alongside: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    write: Callable[[Path, str], Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The lap and the report survive the kill, so the resumed owner repairs."""
    _served_by(docs, write, "api", covered=("api",))
    monkeypatch.setattr(book_nodes, "_play", _Checks(1, 0))
    run_env = env()
    run_dir = run_env.writer.run_dir

    with pytest.raises(RuntimeError, match="killed during specify-story"):
        drive_flow(
            Docs(story=STORY, epic=EPIC),
            run_env,
            _Agent(explode={"specify-story"}, explode_after=2),
        )

    checkpoint = parse_checkpoint((run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    resume = read_resume(checkpoint)
    assert resume.state == "work", resume
    assert resume.flow == "Docs", resume
    assert resume.params["laps"] == 1, resume.params
    assert "claim unreadable" in resume.params["report"], resume.params

    agent = _Agent()
    result = drive_flow(Docs(**resume.inputs), env(run_dir=run_dir), agent, resume)

    assert result.status == "passed", result
    assert agent.counts() == {"specify-story": 1}, agent.counts()
    assert "claim unreadable" in agent.author_args()[0]["report"]
