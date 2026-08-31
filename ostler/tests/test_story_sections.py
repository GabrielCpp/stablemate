"""One story contract, checked against the document rather than against a stamp.

Everything here is a variation on the same question: can two stories saying the same thing be
judged differently? Under a persisted shape key they could, so these tests hold the pieces that
replaced it — `required_section_problems` reading the body, `section_order_problems` holding the
order, and `scaffold_missing_sections` repairing either — to the property that no frontmatter and
no history changes the answer.
"""
from __future__ import annotations

from pathlib import Path

from ostler import Ostler, crud, markdown, registry
from ostler.model import load, section_order_problems

from conftest import present


def _story(root: Path) -> Path:
    """A story whose prose is written but whose last two prose sections were never added."""
    crud.create_epic(load(root), "e", "E", prefix="x")
    crud.create_story(load(root), "e", "a", "A")
    story_md = present(present(load(root).find_story("a"))[1].story_md)
    text = story_md.read_text(encoding="utf-8")
    text = text.replace("## Context\n", "## Context\n\nExisting context.\n")
    text = text.replace(
        "## Acceptance Criteria\n", "## Acceptance Criteria\n\n- Existing criterion.\n"
    )
    text = text.replace("## Non-Functional Acceptance Criteria\n\n", "")
    text = text.replace("## Technical Notes\n\n", "")
    text = text.replace(
        "## Implementation Status",
        "Existing prose immediately before status.\n\n## Implementation Status",
    )
    story_md.write_text(text, encoding="utf-8")
    return story_md


def _drop_section(text: str, heading: str) -> str:
    """The document without ``heading`` and its body — how a rework empties a story out."""
    doc = markdown.split(text)
    section = present(doc.find_section(heading))
    lines = doc.body.split("\n")
    doc.replace_body(lines[: section.line_start] + lines[section.line_end :])
    return doc.render()


def _stamp(story_md: Path, line: str) -> None:
    text = story_md.read_text(encoding="utf-8")
    story_md.write_text(
        text.replace("status: Not started\n", f"status: Not started\n{line}\n"), encoding="utf-8"
    )


def test_a_stamped_story_and_an_unstamped_one_are_judged_identically(tmp_path: Path) -> None:
    """Byte-identical prose, one carrying the old shape key: one verdict.

    This is the whole point of deleting the stamp. The stamped copy used to select a weaker
    section table and read as complete; now the frontmatter is inert text and the body answers.
    """
    story_md = _story(tmp_path)
    _, plain = present(load(tmp_path).find_story("a"))

    _stamp(story_md, "storyShape: 1")
    _, stamped = present(load(tmp_path).find_story("a"))

    assert stamped.unwritten_sections == plain.unwritten_sections
    assert stamped.misordered_sections == plain.misordered_sections
    assert stamped.authored is plain.authored is False


def test_removing_a_stale_shape_line_changes_nothing(tmp_path: Path) -> None:
    story_md = _story(tmp_path)
    _stamp(story_md, "storyShape: 2")
    Ostler(tmp_path).scaffold_missing_sections("a")
    stamped = story_md.read_text(encoding="utf-8")
    _, before = present(load(tmp_path).find_story("a"))

    story_md.write_text(stamped.replace("storyShape: 2\n", ""), encoding="utf-8")
    _, after = present(load(tmp_path).find_story("a"))

    assert after.unwritten_sections == before.unwritten_sections
    assert after.misordered_sections == before.misordered_sections
    assert after.authored is before.authored


def test_scaffold_converges_from_any_state_to_one_document(tmp_path: Path) -> None:
    """Scaffold an old story, empty it out again, scaffold again — one result, not three.

    A story written before the contract grew and a story a rework just emptied are the same
    document to this operation, which is why no lane has to know which one it is holding.
    """
    story_md = _story(tmp_path)
    before = markdown.split(story_md.read_text(encoding="utf-8"))

    result = Ostler(tmp_path).scaffold_missing_sections("a")

    assert result.ok
    scaffolded = story_md.read_text(encoding="utf-8")
    doc = markdown.split(scaffolded)
    assert doc.frontmatter == before.frontmatter
    assert "Existing context." in doc.body
    assert "- Existing criterion." in doc.body
    assert "Existing prose immediately before status." in doc.body
    assert [s.title for s in doc.walk_sections() if s.level == 2] == [
        spec.heading for spec in registry.STORY_SECTIONS
    ]

    assert Ostler(tmp_path).scaffold_missing_sections("a").ok
    assert story_md.read_text(encoding="utf-8") == scaffolded

    emptied = scaffolded
    for heading in ("Non-Functional Acceptance Criteria", "Technical Notes"):
        emptied = _drop_section(emptied, heading)
    story_md.write_text(emptied, encoding="utf-8")

    assert Ostler(tmp_path).scaffold_missing_sections("a").ok
    assert story_md.read_text(encoding="utf-8") == scaffolded


def test_a_story_is_unauthored_until_every_required_section_carries_prose(
    tmp_path: Path,
) -> None:
    story_md = _story(tmp_path)
    Ostler(tmp_path).scaffold_missing_sections("a")

    _, story = present(load(tmp_path).find_story("a"))
    assert story.unwritten_sections == ["Non-Functional Acceptance Criteria", "Technical Notes"]
    assert story.authored is False

    text = story_md.read_text(encoding="utf-8")
    text = text.replace(
        "## Non-Functional Acceptance Criteria\n", "## Non-Functional Acceptance Criteria\n\n- Fast.\n"
    )
    text = text.replace("## Technical Notes\n", "## Technical Notes\n\n`a.py::b` is the seam.\n")
    story_md.write_text(text, encoding="utf-8")

    _, written = present(load(tmp_path).find_story("a"))
    assert written.unwritten_sections == []
    assert written.authored is True


def test_section_order_is_part_of_the_contract(tmp_path: Path) -> None:
    """Presence alone would let a hand-written story and a scaffolded one read differently."""
    story_md = _story(tmp_path)
    Ostler(tmp_path).scaffold_missing_sections("a")
    doc = markdown.split(story_md.read_text(encoding="utf-8"))
    assert section_order_problems(doc, registry.STORY_SECTIONS) == []

    lines = doc.body.split("\n")
    notes = present(doc.find_section("Technical Notes"))
    block = lines[notes.line_start : notes.line_end]
    rest = lines[: notes.line_start] + lines[notes.line_end :]
    at = rest.index(f"## {registry.STORY_SECTIONS[2].heading}")
    doc.replace_body(rest[:at] + block + rest[at:])
    story_md.write_text(doc.render(), encoding="utf-8")

    _, story = present(load(tmp_path).find_story("a"))
    assert story.misordered_sections == [
        "`## Technical Notes` must come after `## Non-Functional Acceptance Criteria`"
    ]
