from __future__ import annotations

import builtins
import logging
import subprocess
from pathlib import Path
from typing import Any

import pytest
from _fakes import StubRunner
from _pm import verdict
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow import Registry, WorkflowFailed
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv
from workhorse_workflows import author
from workhorse_workflows.author.pm.nodes import blueprint as pm_blueprint
from workhorse_workflows.author.shared.nodes import blueprint as shared_blueprint
from workhorse_workflows.author.shared.schemas import Defects, Feedback, MockupGate
from workhorse_workflows.author.story_author import StoryAuthor
from workhorse_workflows.author.story_author.nodes import blueprint, prepare_story
from workhorse_workflows.author.story_author.schemas import StoryAuthorDone, StoryTarget
from _epics import epics_root


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()


def _head(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=repo,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    ).stdout.strip()


class _Agent:
    def __init__(
        self, events: list[str], mockup: dict[str, Any] | None = None
    ) -> None:
        self.events = events
        self.mockup = mockup or {"status": "created", "mockup": "docs/mockup.html"}
        self.args: dict[str, dict[str, Any]] = {}

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        stem = Path(node.prompt).stem
        self.events.append(stem)
        self.args[stem] = ctx.as_dict()
        replies = {
            "design-mockup": self.mockup,
            "write-story": {"status": "written"},
            "review-inline": verdict("story"),
        }
        return f"scripted {stem}", replies[stem]


def _env(tmp_path: Path, nodes: Any, agent: _Agent) -> RunEnv:
    writer = ArtifactWriter("story-author", tmp_path / "runs", run_id="t")
    return RunEnv(
        writer=writer,
        nodes=nodes,
        workflow_dir=Path(author.__file__).parent,
        session_id_path=writer.run_dir / ".session_id",
        config=RunConfig(),
        agent_runner=StubRunner(agent),
    )


def _drive_story(
    repo: Path, tmp_path: Path, design: dict[str, Any] | None = None
) -> tuple[Any, list[str], _Agent, StoryTarget]:
    events: list[str] = []
    target = StoryTarget(
        epic="accounts",
        story="sign-in",
        story_id="ACME-01TEST",
        epic_dir=str(epics_root() / "0001-accounts"),
        story_dir=str(epics_root() / "0001-accounts/stories/sign-in"),
        story_path=str(epics_root() / "0001-accounts/stories/sign-in/story.md"),
        scaffolded=True,
    )
    story_file = repo / target.story_path
    story_file.parent.mkdir(parents=True, exist_ok=True)
    story_file.write_text("# Story: Sign in\n", encoding="utf-8")

    def prepare(
        logger: logging.Logger,
        epic: str = "",
        story: str = "",
        repo_dir: str = "",
    ) -> StoryTarget:
        events.append("prepare")
        assert (epic, story, repo_dir) == ("accounts", "sign-in", str(repo))
        return target

    def mockup(
        logger: logging.Logger, story_id: str = "", repo_dir: str = ""
    ) -> MockupGate:
        events.append("mockup-gate")
        assert story_id == "ACME-01TEST"
        return MockupGate(required=True)

    def valid(logger: logging.Logger, *args: Any, **kwargs: Any) -> Defects:
        events.append("validate")
        return Defects(ok=True)

    def grounded(logger: logging.Logger, *args: Any, **kwargs: Any) -> Defects:
        events.append("ground")
        return Defects(ok=True)

    def no_feedback(logger: logging.Logger, run_dir: str = "") -> Feedback:
        events.append("feedback")
        return Feedback()

    registry = Registry("story-author-test").add_blueprints(shared_blueprint, blueprint, pm_blueprint)
    nodes = registry.override(
        prepare_story=prepare,
        check_mockup_needed=mockup,
        validate_story=valid,
        check_story_grounding=grounded,
        check_story_feedback=no_feedback,
    )
    agent = _Agent(events, design)
    result = drive(
        StoryAuthor(epic="accounts", story="sign-in", repo_dir=str(repo)),
        _env(tmp_path, nodes, agent),
    )
    return result, events, agent, target


def test_flow_prepares_explicit_story_before_authoring_without_git_side_effects(
    repo: Path, tmp_path: Path
) -> None:
    (repo / "docs").mkdir(exist_ok=True)
    (repo / "docs/mockup.html").write_text("<html></html>\n", encoding="utf-8")
    branch_before = _git(repo, "branch", "--show-current")
    head_before = _head(repo)

    result, events, agent, target = _drive_story(repo, tmp_path)

    assert isinstance(result, StoryAuthorDone)
    assert result.epic == "accounts"
    assert result.story == "sign-in"
    assert result.story_path == target.story_path
    assert events == [
        "prepare",
        "mockup-gate",
        "design-mockup",
        "write-story",
        "validate",
        "ground",
        "review-inline",
        "feedback",
    ]
    assert agent.args["write-story"]["story_slug"] == "sign-in"
    assert _git(repo, "branch", "--show-current") == branch_before
    assert _head(repo) == head_before


@pytest.mark.parametrize(
    "mockup",
    [
        {"status": "failed", "mockup": "", "notes": "no design system to draw from"},
        {"status": "created", "mockup": "docs/missing.html", "notes": ""},
    ],
)
def test_a_story_with_a_ui_service_and_no_mockup_ends_blocked_before_it_is_written(
    repo: Path, tmp_path: Path, mockup: dict[str, Any]
) -> None:
    result, events, _agent, target = _drive_story(repo, tmp_path, mockup)

    assert isinstance(result, StoryAuthorDone)
    assert result.status == "blocked"
    assert result.story == "sign-in"
    assert result.story_path == target.story_path
    assert "no mockup for a story with a UI service" in result.notes
    assert events == ["prepare", "mockup-gate", "design-mockup"]


def test_the_milestone_mockups_folder_reaches_the_design_turn(
    repo: Path, tmp_path: Path
) -> None:
    (repo / "docs").mkdir(exist_ok=True)
    (repo / "docs/mockup.html").write_text("<html></html>\n", encoding="utf-8")

    _result, _events, agent, _target = _drive_story(repo, tmp_path)

    assert "milestone_mockups_dir" in agent.args["design-mockup"]


def test_prepare_story_rejects_a_story_from_another_epic(
    monkeypatch: pytest.MonkeyPatch, logger: logging.Logger, tmp_path: Path
) -> None:
    class _Ostler:
        def __init__(self, root: Path) -> None:
            pass

        def list(self, kind: str, *, epic: str) -> builtins.list[dict[str, object]]:
            assert kind == "story"
            return []

    from workhorse_workflows.author.story_author.nodes import story as story_nodes

    monkeypatch.setattr(story_nodes, "Ostler", _Ostler)

    with pytest.raises(WorkflowFailed, match="not found in epic 'accounts'"):
        prepare_story(logger, "accounts", "sign-in", repo_dir=str(tmp_path))


def test_prepare_story_scaffolds_the_named_story_through_ostler(
    monkeypatch: pytest.MonkeyPatch, logger: logging.Logger, tmp_path: Path
) -> None:
    calls: list[str] = []

    class _Result:
        ok = True
        message = "added 2 section(s) to story 'sign-in'"

    class _Ostler:
        def __init__(self, root: Path) -> None:
            self.root = root

        def list(self, kind: str, *, epic: str) -> builtins.list[dict[str, object]]:
            calls.append(f"list:{epic}")
            return [
                {
                    "slug": "sign-in",
                    "id": "ACME-01TEST",
                    "path": str(epics_root() / "0001-accounts/stories/sign-in/story.md"),
                }
            ]

        def scaffold_missing_sections(self, story_id: str) -> _Result:
            calls.append(f"scaffold:{story_id}")
            return _Result()

        def epic_dir(self, epic: str) -> Path:
            calls.append(f"epic-dir:{epic}")
            return epics_root() / "0001-accounts"

    from workhorse_workflows.author.story_author.nodes import story as story_nodes

    monkeypatch.setattr(story_nodes, "Ostler", _Ostler)

    target = prepare_story(logger, "accounts", "sign-in", repo_dir=str(tmp_path))

    assert calls == ["list:accounts", "scaffold:ACME-01TEST", "epic-dir:accounts"]
    assert target.scaffolded is True
    assert target.story_id == "ACME-01TEST"
    assert target.story_path == str(epics_root() / "0001-accounts/stories/sign-in/story.md")
