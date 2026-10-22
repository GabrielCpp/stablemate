"""A story's `services:` frontmatter: parsed, dumped, schema-checked and resolved against the books."""
from __future__ import annotations

from pathlib import Path

from ostler import Ostler, doctor
from ostler.model import load

from conftest import FOO_ID, present, write
from test_milestones import add_mobile_book


def _services(repo: Path, line: str) -> None:
    story_md = present(present(load(repo).find_story("01-foo"))[1].story_md)
    text = story_md.read_text(encoding="utf-8")
    story_md.write_text(text.replace(f"id: {FOO_ID}\n", f"id: {FOO_ID}\n{line}\n", 1), encoding="utf-8")


def _schema_findings(repo: Path) -> list:
    return [f for f in doctor.run(load(repo)).findings if f.code == "schema" and "01-foo" in f.message]


def test_a_story_without_services_has_an_empty_tuple(repo: Path):
    _, story = present(load(repo).find_story("01-foo"))

    assert story.services == ()


def test_story_services_are_read_from_the_frontmatter_list(repo: Path):
    _services(repo, "services: [web, api, web]")

    _, story = present(load(repo).find_story("01-foo"))

    assert story.services == ("web", "api")
    assert story.raw["services"] == ["web", "api"]


def test_a_story_row_carries_its_services(repo: Path):
    _services(repo, "services: [api]")

    rows = {row["slug"]: row for row in Ostler(repo).list("story")}

    assert rows["01-foo"]["services"] == ["api"]
    assert rows["01-bar"]["services"] == []


def test_the_schema_accepts_a_services_list(repo: Path):
    _services(repo, "services: [api, web]")

    assert _schema_findings(repo) == []


def test_the_schema_rejects_services_that_is_not_a_list(repo: Path):
    _services(repo, "services: api")

    assert _schema_findings(repo)


def test_the_books_are_the_directories_under_services(repo: Path):
    assert Ostler(repo).service_books() == {"area"}


def test_only_a_web_or_mobile_book_is_a_ui_service(repo: Path):
    add_mobile_book(repo)
    write(repo / "docs/services/api/rec.md", "---\ntype: feature\nslug: rec\ntitle: Rec\n---\n# Rec\n")

    okf = Ostler(repo)

    assert okf.ui_services(["mobile-app", "api", "area"]) == {"mobile-app"}
    assert okf.ui_services([]) == set()
