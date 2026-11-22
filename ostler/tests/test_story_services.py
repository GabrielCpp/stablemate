"""A story's `services:` frontmatter: parsed, dumped, schema-checked and resolved against the books."""
from __future__ import annotations

from pathlib import Path

from ostler import Ostler, doctor
from ostler.model import load

from conftest import FOO_ID, keep_book_in_repo, present, write


def _services(repo: Path, line: str) -> None:
    story_md = present(present(load(repo).story_by_slug("01-foo"))[1].story_md)
    text = story_md.read_text(encoding="utf-8")
    story_md.write_text(text.replace(f"id: {FOO_ID}\n", f"id: {FOO_ID}\n{line}\n", 1), encoding="utf-8")


def _schema_findings(repo: Path) -> list:
    return [f for f in doctor.run(load(repo)).findings if f.code == "schema" and "t-01foo" in (f.message + f.path)]


def test_a_story_without_services_has_an_empty_tuple(repo: Path):
    _, story = present(load(repo).story_by_slug("01-foo"))

    assert story.services == ()


def test_story_services_are_read_from_the_frontmatter_list(repo: Path):
    _services(repo, "services: [web, api, web]")

    _, story = present(load(repo).story_by_slug("01-foo"))

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


def test_a_page_folder_is_no_book(repo: Path):
    assert Ostler(repo).service_books() == set()


def test_a_python_book_is_a_book_with_no_page_folder(repo: Path):
    keep_book_in_repo(repo)
    write(repo / "services/billing/service.py", "")
    write(repo / "services/desk/web/service.py", "")
    write(repo / "services/ops/stack.yml", "services: {}\n")

    assert Ostler(repo).service_books() == {"billing", "desk"}


def test_a_book_with_screens_is_a_ui_service(repo: Path):
    keep_book_in_repo(repo)
    write(repo / "services/web-app/service.py", "")
    write(repo / "services/web-app/screens/__init__.py", "")
    write(repo / "services/desk/web/service.py", "")
    write(repo / "services/desk/web/screens.py", "")
    write(repo / "services/billing/service.py", "")

    assert Ostler(repo).ui_services(["web-app", "desk", "billing"]) == {"web-app", "desk"}
