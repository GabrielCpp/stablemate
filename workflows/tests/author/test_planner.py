from __future__ import annotations

import logging
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from ostler import select
from ostler.model import Epic, Graph, Milestone, SeedItem, Story
from workhorse_workflows.author.main.nodes import planner
from workhorse_workflows.author.shared.story_split_receipt import story_split_digest

ROADMAP = "docs/roadmaps/account-access.md"


def _story(
    slug: str,
    *,
    dependencies: list[str] | None = None,
    authored: bool = True,
) -> Story:
    return Story(
        slug=slug,
        title=slug,
        path=f"docs/epics/example/{slug}/story.md",
        seed_items=[slug],
        dependencies=list(dependencies or []),
        story_md=Path(f"/{slug}/story.md"),
        unwritten_sections=[] if authored else ["Context"],
        unwritten_detail=[] if authored else ["Context (empty)"],
    )


def _epic(name: str, stories: list[Story] | None = None, *, documented: bool = True) -> Epic:
    rows = list(stories or [])
    return Epic(
        name=name,
        directory=Path(f"/docs/epics/{name}"),
        epic_md=Path(f"/docs/epics/{name}/epic.md"),
        seeds=[SeedItem(story.slug, "researched") for story in rows] if documented else [],
        stories=rows,
    )


class _Ostler:
    def __init__(self, root: Path, milestones: list[Milestone], epics: list[Epic]) -> None:
        self.graph = Graph(root=root, org_name="acme", profile="full", doc_roots={},
                           milestones=milestones, epics=epics)
        self.needs: list[str] = []

    def next_story_report(
        self, epic: str, *, need: str = "build", skip: set[str] | None = None
    ) -> dict[str, Any]:
        self.needs.append(need)
        return select.next_story_report(self.graph, epic, need=need, skip=skip)


@pytest.fixture
def install(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Any:
    def _install(milestone_epics: list[str] | None, epics: list[Epic]) -> _Ostler:
        for epic in epics:
            epic_dir = tmp_path / "docs/epics" / epic.name
            epic_dir.mkdir(parents=True, exist_ok=True)
            epic.epic_md = epic_dir / "epic.md"
            for story in epic.stories:
                path = tmp_path / "docs/epics" / epic.name / "stories" / story.slug / "story.md"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"# {story.title}\n", encoding="utf-8")
                story.story_md = path
                if story.authored:
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    (path.parent / "audit-receipt.json").write_text(
                        json.dumps({"status": "passed", "storyDigest": digest}),
                        encoding="utf-8",
                    )
            if planner._story_graph_valid(epic):
                (epic_dir / "story-split-receipt.json").write_text(
                    json.dumps(
                        {"status": "passed", "graphDigest": story_split_digest(epic)}
                    ),
                    encoding="utf-8",
                )
        milestones = []
        if milestone_epics is not None:
            milestones = [
                Milestone(
                    name="account-access",
                    path=tmp_path / "docs/milestones/account-access.md",
                    source_items=[ROADMAP],
                    epics=milestone_epics,
                )
            ]
        fake = _Ostler(tmp_path, milestones, epics)
        monkeypatch.setattr(planner, "Ostler", lambda _root: fake)
        monkeypatch.setattr(planner, "survey_repo_root", lambda _repo: tmp_path)
        monkeypatch.setattr(planner, "approved_roadmap", lambda _root, roadmap: roadmap)
        return fake

    return _install


def _plan() -> Any:
    return planner.plan_author_step(logging.getLogger("test"), ROADMAP, repo_dir="unused")


def test_missing_milestone_is_the_next_unit(install: Any) -> None:
    install(None, [])

    step = _plan()

    assert step.kind == "milestone"
    assert step.roadmap == ROADMAP


def test_milestone_with_an_additional_source_is_invalid(install: Any) -> None:
    fake = install([], [])
    fake.graph.milestones[0].source_items.append("docs/roadmaps/other.md")

    step = _plan()

    assert step.kind == "milestone"


def test_missing_epic_split_follows_a_valid_milestone(install: Any) -> None:
    install([], [])

    step = _plan()

    assert step.kind == "epic-split"


def test_duplicate_epic_split_is_invalid(install: Any) -> None:
    epic = _epic("accounts", documented=False)
    install(["accounts", "accounts"], [epic])

    step = _plan()

    assert step.kind == "epic-split"


def test_first_undocumented_epic_uses_milestone_order(install: Any) -> None:
    later = _epic("later", documented=False)
    earlier = _epic("earlier", documented=False)
    install(["earlier", "later"], [later, earlier])

    step = _plan()

    assert (step.kind, step.epic) == ("epic-author", "earlier")


def test_epic_author_phase_precedes_an_earlier_invalid_story_graph(install: Any) -> None:
    invalid_graph = _epic("first", [])
    invalid_graph.seeds = [SeedItem("scope", "researched")]
    undocumented = _epic("second", documented=False)
    install(["first", "second"], [invalid_graph, undocumented])

    step = _plan()

    assert (step.kind, step.epic) == ("epic-author", "second")


def test_first_invalid_story_graph_uses_milestone_order(install: Any) -> None:
    second = _epic("second", [])
    first = _epic("first", [])
    second.seeds = [SeedItem("second-scope", "researched")]
    first.seeds = [SeedItem("first-scope", "researched")]
    install(["first", "second"], [second, first])

    step = _plan()

    assert (step.kind, step.epic) == ("story-split", "first")


def test_story_author_uses_story_dag_order_and_author_current(install: Any) -> None:
    dependent = _story("dependent", dependencies=["base"], authored=False)
    base = _story("base", authored=False)
    epic = _epic("accounts", [dependent, base])
    fake = install(["accounts"], [epic])

    step = _plan()

    assert (step.kind, step.epic, step.story) == ("story-author", "accounts", "base")
    assert fake.needs == ["author"]


def test_valid_graph_without_semantic_review_routes_to_story_split(install: Any) -> None:
    epic = _epic("accounts", [_story("sign-in")])
    install(["accounts"], [epic])
    assert epic.epic_md is not None
    epic.epic_md.parent.joinpath("story-split-receipt.json").unlink()

    step = _plan()

    assert (step.kind, step.epic) == ("story-split", "accounts")


def test_story_changed_after_its_audit_is_selected_again(install: Any) -> None:
    story = _story("sign-in")
    install(["accounts"], [_epic("accounts", [story])])
    assert story.story_md is not None
    story.story_md.write_text("# Story: changed after audit\n", encoding="utf-8")

    step = _plan()

    assert (step.kind, step.story) == ("story-author", "sign-in")


def test_blocked_story_is_skipped_for_the_remainder_of_one_main_run(install: Any) -> None:
    first = _story("sign-in")
    second = _story("reset-password")
    install(["accounts"], [_epic("accounts", [first, second])])
    assert first.story_md is not None
    first.story_md.parent.joinpath("audit-receipt.json").unlink()
    assert second.story_md is not None
    second.story_md.parent.joinpath("audit-receipt.json").unlink()

    step = planner.plan_author_step(
        logging.getLogger("test"),
        ROADMAP,
        blocked=("accounts/sign-in",),
        repo_dir="unused",
    )

    assert (step.kind, step.story) == ("story-author", "reset-password")


def test_story_author_uses_milestone_epic_order(install: Any) -> None:
    second = _epic("second", [_story("second-story", authored=False)])
    first = _epic("first", [_story("first-story", authored=False)])
    install(["first", "second"], [second, first])

    step = _plan()

    assert (step.kind, step.epic, step.story) == (
        "story-author",
        "first",
        "first-story",
    )


def test_current_authored_graph_finalizes(install: Any) -> None:
    current = _story("current")
    install(["accounts"], [_epic("accounts", [current])])

    step = _plan()

    assert step.kind == "finalize"
    assert not step.epic
    assert not step.story
