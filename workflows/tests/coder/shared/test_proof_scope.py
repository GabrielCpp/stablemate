"""What a leftover change reopens: nothing, the scenarios that cover its citing pages, or the whole plan."""
from __future__ import annotations

from pathlib import Path

from workhorse_workflows.coder.shared.proof_scope import inert_paths, scope

PAGE = "repo:docs/services/api/http/x.md"
OTHER = "repo:docs/services/api/http/y.md"


def test_the_storys_own_markdown_is_inert_and_nothing_else_is(tmp_path: Path) -> None:
    dirty = [
        "repo:docs/epics/E/stories/S/story.md",
        "repo:docs/epics/E/stories/S/notes.md",
        "repo:docs/epics/E/stories/S/data.json",
        "repo:docs/epics/E/stories/S/sub/deep.md",
        "repo:src/app.py",
        "other:docs/epics/E/stories/S/story.md",
    ]

    inert = inert_paths("repo", tmp_path, "docs/epics/E/stories/S/story.md", dirty)

    assert inert == {
        "repo:docs/epics/E/stories/S/story.md",
        "repo:docs/epics/E/stories/S/notes.md",
    }


def test_only_inert_paths_reopen_nothing() -> None:
    assert scope(["repo:story.md"], {"repo:story.md"}, {}, {}).kind == "inert"
    assert scope([], set(), {}, {}).kind == "inert"


def test_a_cited_file_reopens_the_scenarios_covering_its_pages() -> None:
    result = scope(
        ["repo:src/a.py"],
        set(),
        {"repo:src/a.py": {PAGE}},
        {"one": {PAGE}, "two": {OTHER}, "three": {PAGE, OTHER}},
    )

    assert (result.kind, result.scenarios) == ("claims", ["one", "three"])


def test_an_uncited_file_reopens_the_whole_plan() -> None:
    result = scope(["repo:fixtures/seed.json"], set(), {}, {"one": {PAGE}})

    assert result.kind == "whole"
    assert result.reasons == ["repo:fixtures/seed.json: no book page cites it"]


def test_a_cited_file_no_scenario_covers_reopens_the_whole_plan() -> None:
    result = scope(["repo:src/a.py"], set(), {"repo:src/a.py": {PAGE}}, {"two": {OTHER}})

    assert result.kind == "whole"
    assert "no scenario covers" in result.reasons[0]


def test_an_edited_book_page_reopens_its_own_scenarios() -> None:
    result = scope([PAGE], set(), {}, {"one": {PAGE}}, pages={PAGE})

    assert (result.kind, result.scenarios) == ("claims", ["one"])


def test_one_uncited_path_among_cited_ones_widens_the_scope() -> None:
    result = scope(
        ["repo:src/a.py", "repo:uv.lock"],
        set(),
        {"repo:src/a.py": {PAGE}},
        {"one": {PAGE}},
    )

    assert result.kind == "whole"
