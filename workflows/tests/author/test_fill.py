from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import pytest
from ostler import select
from ostler.model import Epic, Graph, Milestone, SeedItem, Story
from workhorse.pyflow import WorkflowFailed
from workhorse.worklist import WORK_FILE, JsonBackend, WorkList
from workhorse_workflows.author.main.nodes import fill
from workhorse_workflows.author.shared.story_split_receipt import story_split_digest

MILESTONE = "docs/milestones/account-access/milestone.md"


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
        self.skips: list[set[str]] = []

    def approved_milestone(self) -> Milestone:
        return self.graph.milestones[0]

    def next_story_report(
        self, epic: str, *, need: str = "build", skip: set[str] | None = None
    ) -> dict[str, Any]:
        self.needs.append(need)
        self.skips.append(set(skip or ()))
        return select.next_story_report(self.graph, epic, need=need, skip=skip)


@pytest.fixture
def install(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Any:
    def _install(milestone_epics: list[str], epics: list[Epic]) -> _Ostler:
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
            if fill._story_graph_valid(epic):
                (epic_dir / "story-split-receipt.json").write_text(
                    json.dumps(
                        {"status": "passed", "graphDigest": story_split_digest(epic)}
                    ),
                    encoding="utf-8",
                )
        milestones = [
            Milestone(
                name="account-access",
                path=tmp_path / MILESTONE,
                status="approved",
                epics=milestone_epics,
            )
        ]
        fake = _Ostler(tmp_path, milestones, epics)
        monkeypatch.setattr(fill, "Ostler", lambda _root: fake)
        monkeypatch.setattr(fill, "survey_repo_root", lambda _repo: tmp_path)
        return fake

    return _install


def _fill(kind: str, run_dir: Path) -> Any:
    return fill.fill_work(logging.getLogger("test"), kind, str(run_dir), repo_dir="unused")


def _rows(run_dir: Path, kind: str) -> list[tuple[str, str]]:
    work = WorkList(JsonBackend(run_dir / WORK_FILE))
    ordered = sorted(work.items(kind), key=lambda item: item.order or 0)
    return [(item.id, item.status) for item in ordered]


def _settle(run_dir: Path, kind: str) -> None:
    work = WorkList(JsonBackend(run_dir / WORK_FILE))
    work.settle([item.id for item in work.items(kind)], "done")


def test_epics_are_filed_in_milestone_order_and_written_ones_are_done(
    install: Any, tmp_path: Path
) -> None:
    later = _epic("later", documented=False)
    earlier = _epic("earlier", [_story("seed")])
    install(["earlier", "later"], [later, earlier])
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    filled = _fill("epic", run_dir)

    assert (filled.filed, filled.done) == (2, 1)
    assert _rows(run_dir, "epic") == [("epic:earlier", "done"), ("epic:later", "")]
    item = WorkList(JsonBackend(run_dir / WORK_FILE)).items("epic")[0]
    assert item.payload == {"epic": "earlier"}


def test_an_invalid_epic_split_cannot_be_filled(install: Any, tmp_path: Path) -> None:
    install(["accounts", "accounts"], [_epic("accounts")])

    with pytest.raises(WorkflowFailed):
        _fill("epic", tmp_path)


def test_check_epic_split_reports_a_missing_split(install: Any) -> None:
    install([], [])

    result = fill.check_epic_split(logging.getLogger("test"), repo_dir="unused")

    assert not result.ok


def test_check_epic_split_accepts_an_ordered_split(install: Any) -> None:
    install(["accounts"], [_epic("accounts")])

    result = fill.check_epic_split(logging.getLogger("test"), repo_dir="unused")

    assert result.ok


def test_a_story_split_is_filed_only_for_an_epic_whose_row_is_done(
    install: Any, tmp_path: Path
) -> None:
    install(["first", "second"], [_epic("second", documented=False), _epic("first", [_story("a")])])
    _fill("epic", tmp_path)
    work = WorkList(JsonBackend(tmp_path / WORK_FILE))
    assert [item.status for item in work.items("epic")] == ["done", ""]

    _fill("story-split", tmp_path)

    assert _rows(tmp_path, "story-split") == [("story-split:first", "done")]


def test_an_unreviewed_story_graph_is_filed_pending(install: Any, tmp_path: Path) -> None:
    epic = _epic("accounts", [_story("sign-in")])
    install(["accounts"], [epic])
    assert epic.epic_md is not None
    epic.epic_md.parent.joinpath("story-split-receipt.json").unlink()
    _fill("epic", tmp_path)

    _fill("story-split", tmp_path)

    assert _rows(tmp_path, "story-split") == [("story-split:accounts", "")]


def test_stories_follow_dag_order_inside_milestone_epic_order(
    install: Any, tmp_path: Path
) -> None:
    dependent = _story("dependent", dependencies=["base"], authored=False)
    base = _story("base", authored=False)
    second = _epic("second", [_story("second-story", authored=False)])
    first = _epic("first", [dependent, base])
    fake = install(["first", "second"], [second, first])
    _fill("epic", tmp_path)
    _fill("story-split", tmp_path)

    filled = _fill("story", tmp_path)

    assert filled.filed == 3
    assert _rows(tmp_path, "story") == [
        ("first/base", ""),
        ("first/dependent", ""),
        ("second/second-story", ""),
    ]
    assert set(fake.needs) == {"author"}
    item = WorkList(JsonBackend(tmp_path / WORK_FILE)).items("story")[0]
    assert item.payload == {"epic": "first", "story": "base"}


def test_an_authored_and_audited_story_is_filed_done(install: Any, tmp_path: Path) -> None:
    install(["accounts"], [_epic("accounts", [_story("current")])])
    _fill("epic", tmp_path)
    _fill("story-split", tmp_path)

    _fill("story", tmp_path)

    assert _rows(tmp_path, "story") == [("accounts/current", "done")]


def test_a_story_changed_after_its_audit_is_filed_pending(
    install: Any, tmp_path: Path
) -> None:
    story = _story("sign-in")
    install(["accounts"], [_epic("accounts", [story])])
    assert story.story_md is not None
    story.story_md.write_text("# Story: changed after audit\n", encoding="utf-8")
    _fill("epic", tmp_path)
    _fill("story-split", tmp_path)

    _fill("story", tmp_path)

    assert _rows(tmp_path, "story") == [("accounts/sign-in", "")]


def test_every_story_the_report_would_select_is_filed_pending(
    install: Any, tmp_path: Path
) -> None:
    first = _story("sign-in", authored=False)
    second = _story("reset-password", authored=False)
    fake = install(["accounts"], [_epic("accounts", [first, second])])
    _fill("epic", tmp_path)
    _fill("story-split", tmp_path)

    _fill("story", tmp_path)

    assert _rows(tmp_path, "story") == [
        ("accounts/sign-in", ""),
        ("accounts/reset-password", ""),
    ]
    assert fake.skips[0] == set()
    assert any(len(skip) == 2 for skip in fake.skips)


def test_a_second_fill_files_nothing_and_keeps_every_status(
    install: Any, tmp_path: Path
) -> None:
    install(["accounts"], [_epic("accounts", documented=False)])

    first = _fill("epic", tmp_path)
    _settle(tmp_path, "epic")
    second = _fill("epic", tmp_path)

    assert (first.filed, second.filed) == (1, 0)
    assert _rows(tmp_path, "epic") == [("epic:accounts", "done")]


def test_a_fill_leaves_the_other_kinds_alone(install: Any, tmp_path: Path) -> None:
    install(["accounts"], [_epic("accounts", [_story("sign-in", authored=False)])])

    _fill("epic", tmp_path)

    assert _rows(tmp_path, "story-split") == []
    assert _rows(tmp_path, "story") == []


def test_an_unknown_kind_is_refused(install: Any, tmp_path: Path) -> None:
    install(["accounts"], [_epic("accounts")])

    with pytest.raises(WorkflowFailed):
        _fill("mockup", tmp_path)
