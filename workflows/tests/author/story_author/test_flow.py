from __future__ import annotations

import builtins
import logging
import subprocess
from pathlib import Path
from typing import Any

import pytest
from _fakes import StubRunner
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow import Registry, WorkflowFailed
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv
from workhorse_workflows import author
from workhorse_workflows.author.main.nodes import blueprint as main_blueprint
from workhorse_workflows.author.shared.schemas import Defects, Feedback, MockupGate
from workhorse_workflows.author.story_author import StoryAuthor
from workhorse_workflows.author.story_author.nodes import blueprint, migrate_story
from workhorse_workflows.author.story_author.schemas import StoryAuthorDone, StoryTarget


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
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.args: dict[str, dict[str, Any]] = {}

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        stem = Path(node.prompt).stem
        self.events.append(stem)
        self.args[stem] = ctx.as_dict()
        replies = {
            "design-mockup": {"status": "complete", "mockup": "docs/mockup.html"},
            "write-story": {"status": "written"},
            "audit-story": {"status": "passed", "findings": []},
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


def test_flow_migrates_explicit_story_before_authoring_without_git_side_effects(
    repo: Path, tmp_path: Path
) -> None:
    events: list[str] = []
    target = StoryTarget(
        epic="accounts",
        story="sign-in",
        epic_dir="docs/epics/0001-accounts",
        story_dir="docs/epics/0001-accounts/stories/sign-in",
        story_path="docs/epics/0001-accounts/stories/sign-in/story.md",
        migrated=True,
    )
    story_file = repo / target.story_path
    story_file.parent.mkdir(parents=True, exist_ok=True)
    story_file.write_text("# Story: Sign in\n", encoding="utf-8")

    def migrate(
        logger: logging.Logger,
        epic: str = "",
        story: str = "",
        epics_dir: str = "",
        repo_dir: str = "",
    ) -> StoryTarget:
        events.append("migrate")
        assert (epic, story, repo_dir) == ("accounts", "sign-in", str(repo))
        return target

    def mockup(
        logger: logging.Logger, story_slug: str = "", repo_dir: str = ""
    ) -> MockupGate:
        events.append("mockup-gate")
        assert story_slug == "sign-in"
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

    registry = Registry("story-author-test").add_blueprints(main_blueprint, blueprint)
    nodes = registry.override(
        migrate_story=migrate,
        check_mockup_needed=mockup,
        validate_story=valid,
        check_story_grounding=grounded,
        check_story_feedback=no_feedback,
    )
    agent = _Agent(events)
    branch_before = _git(repo, "branch", "--show-current")
    head_before = _head(repo)

    result = drive(
        StoryAuthor(epic="accounts", story="sign-in", repo_dir=str(repo)),
        _env(tmp_path, nodes, agent),
    )

    assert isinstance(result, StoryAuthorDone)
    assert result.epic == "accounts"
    assert result.story == "sign-in"
    assert result.story_path == target.story_path
    assert events == [
        "migrate",
        "mockup-gate",
        "design-mockup",
        "write-story",
        "validate",
        "ground",
        "audit-story",
        "feedback",
    ]
    assert agent.args["write-story"]["story_slug"] == "sign-in"
    assert _git(repo, "branch", "--show-current") == branch_before
    assert _head(repo) == head_before


def test_migrate_story_rejects_a_story_from_another_epic(
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
        migrate_story(logger, "accounts", "sign-in", repo_dir=str(tmp_path))


def test_migrate_story_uses_ostler_current_shape_api_for_the_named_story(
    monkeypatch: pytest.MonkeyPatch, logger: logging.Logger, tmp_path: Path
) -> None:
    calls: list[str] = []

    class _Result:
        ok = True
        message = "migrated story 'sign-in' to the current shape"

    class _Ostler:
        def __init__(self, root: Path) -> None:
            self.root = root

        def list(self, kind: str, *, epic: str) -> builtins.list[dict[str, object]]:
            calls.append(f"list:{epic}")
            return [{"slug": "sign-in", "path": "docs/epics/0001-accounts/stories/sign-in/story.md"}]

        def migrate_story_to_current_shape(self, slug: str) -> _Result:
            calls.append(f"migrate:{slug}")
            return _Result()

        def epic_dir(self, epic: str) -> Path:
            calls.append(f"epic-dir:{epic}")
            return self.root / "docs/epics/0001-accounts"

    from workhorse_workflows.author.story_author.nodes import story as story_nodes

    monkeypatch.setattr(story_nodes, "Ostler", _Ostler)

    target = migrate_story(
        logger,
        "accounts",
        "sign-in",
        epics_dir="docs/epics",
        repo_dir=str(tmp_path),
    )

    assert calls == ["list:accounts", "migrate:sign-in", "epic-dir:accounts"]
    assert target.migrated is True
    assert target.story_path == "docs/epics/0001-accounts/stories/sign-in/story.md"
