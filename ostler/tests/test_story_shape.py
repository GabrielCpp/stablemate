from __future__ import annotations

from pathlib import Path

import pytest

from ostler import Ostler, crud, markdown, registry, select
from ostler.model import load

from conftest import present


def _legacy_story(root: Path) -> Path:
    crud.create_epic(load(root), "e", "E", prefix="x")
    crud.create_story(load(root), "e", "a", "A")
    _, story = present(load(root).find_story("a"))
    story_md = present(story.story_md)
    text = story_md.read_text(encoding="utf-8")
    text = text.replace(
        "storyShape: 2\n",
        "labels: [preserve-me] # retain author formatting\n",
    )
    text = text.replace("## Context\n", "## Context\n\nExisting context.\n")
    text = text.replace(
        "## Acceptance Criteria\n",
        "## Acceptance Criteria\n\n- Existing criterion.\n",
    )
    text = text.replace("## Non-Functional Acceptance Criteria\n\n", "")
    text = text.replace("## Technical Notes\n\n", "")
    text = text.replace(
        "## Implementation Status",
        "Existing prose immediately before status.\n\n## Implementation Status",
    )
    story_md.write_text(text, encoding="utf-8")
    return story_md


def test_story_exposes_its_persisted_shape(tmp_path: Path) -> None:
    story_md = _legacy_story(tmp_path)

    _, legacy = present(load(tmp_path).find_story("a"))
    assert legacy.story_shape is None

    story_md.write_text(
        story_md.read_text(encoding="utf-8").replace(
            "status: Not started\n", "status: Not started\nstoryShape: 1\n"
        ),
        encoding="utf-8",
    )
    _, versioned = present(load(tmp_path).find_story("a"))
    assert versioned.story_shape == 1


def test_author_current_selects_a_legacy_story_without_changing_author_mode(
    tmp_path: Path,
) -> None:
    _legacy_story(tmp_path)
    graph = load(tmp_path)

    assert select.next_story_report(graph, "e", need="author")["state"] == "done"

    report = select.next_story_report(graph, "e", need="author-current")
    assert report["state"] == "ready"
    assert report["story"]["slug"] == "a"
    assert report["story"]["storyShape"] is None
    assert report["story"]["authored"] is True

    story_md = present(graph.find_story("a"))[1].story_md
    assert story_md is not None
    story_md.write_text(
        story_md.read_text(encoding="utf-8").replace(
            "status: Not started\n", "status: Not started\nstoryShape: 1\n"
        ),
        encoding="utf-8",
    )
    versioned = select.next_story_report(load(tmp_path), "e", need="author-current")
    assert versioned["state"] == "ready"
    assert versioned["story"]["storyShape"] == 1


@pytest.mark.parametrize("legacy_shape", [None, 1])
def test_migrate_story_to_current_shape_preserves_content_and_is_idempotent(
    tmp_path: Path, legacy_shape: int | None,
) -> None:
    story_md = _legacy_story(tmp_path)
    if legacy_shape is not None:
        story_md.write_text(
            story_md.read_text(encoding="utf-8").replace(
                "status: Not started\n",
                f"status: Not started\nstoryShape: {legacy_shape}\n",
            ),
            encoding="utf-8",
        )
    before = markdown.split(story_md.read_text(encoding="utf-8"))

    result = Ostler(tmp_path).migrate_story_to_current_shape("a")

    assert result.ok
    migrated_text = story_md.read_text(encoding="utf-8")
    migrated = markdown.split(migrated_text)
    expected_frontmatter = dict(before.frontmatter or {})
    expected_frontmatter[registry.STORY_SHAPE_KEY] = registry.CURRENT_STORY_SHAPE
    assert migrated.frontmatter == expected_frontmatter
    assert "labels: [preserve-me] # retain author formatting" in migrated_text
    assert "Existing context." in migrated.body
    assert "- Existing criterion." in migrated.body
    assert "Existing prose immediately before status." in migrated.body
    assert migrated.body.count("## Non-Functional Acceptance Criteria") == 1
    assert migrated.body.count("## Technical Notes") == 1
    assert migrated.body.index("## Non-Functional Acceptance Criteria") < migrated.body.index(
        "## Technical Notes"
    ) < migrated.body.index("## Implementation Status")

    _, story = present(Ostler(tmp_path).graph.find_story("a"))
    assert story.story_shape == registry.CURRENT_STORY_SHAPE
    assert story.unwritten_sections == [
        "Non-Functional Acceptance Criteria",
        "Technical Notes",
    ]

    second = Ostler(tmp_path).migrate_story_to_current_shape("a")
    assert second.ok
    assert story_md.read_text(encoding="utf-8") == migrated_text
