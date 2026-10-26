from __future__ import annotations

import logging
from pathlib import Path

from ostler import Ostler

from workhorse_workflows.author.shared.nodes.coverage import validate_coverage
from workhorse_workflows.author.story_split.nodes.services import derive_story_services


def _books(repo: Path) -> None:
    for name in ("api-service", "worker"):
        (repo / "docs/services" / name).mkdir(parents=True, exist_ok=True)


def _epic(repo: Path) -> str:
    _books(repo)
    okf = Ostler(repo)
    okf.create_epic("accounts", "Accounts", prefix="acme")
    for seed_id, services in (
        ("a", ["worker", "api-service"]),
        ("b", ["api-service"]),
        ("c", []),
    ):
        meta: dict[str, object] = {"services": services} if services else {}
        assert okf.add_seed("accounts", seed_id, status="researched", summary=seed_id, meta=meta).ok
    assert okf.create_story("accounts", "01-both", "Both", covers=["a", "b"]).ok
    assert okf.create_story("accounts", "02-bare", "Bare", covers=["c"]).ok
    return str(Ostler(repo).list("epic")[0]["name"])


def _list_services(repo: Path, slug: str, services: list[str]) -> Path:
    story_md = next(repo.glob(f"docs/epics/*/stories/{slug}/story.md"))
    raw = story_md.read_text(encoding="utf-8")
    story_md.write_text(
        raw.replace("---\n", f"---\nservices: [{', '.join(services)}]\n", 1), encoding="utf-8"
    )
    return story_md


def test_a_story_takes_the_sorted_union_of_its_seeds_services(
    logger: logging.Logger, repo: Path
) -> None:
    epic = _epic(repo)

    result = derive_story_services(logger, epic, repo_dir=str(repo))

    assert result.services == {"01-both": ["api-service", "worker"], "02-bare": []}
    stories = {row["slug"]: row for row in Ostler(repo).list("story", epic=epic)}
    assert stories["01-both"]["services"] == ["api-service", "worker"]
    assert stories["02-bare"]["services"] == []


def test_a_story_keeps_a_narrower_list_inside_its_seeds_union(
    logger: logging.Logger, repo: Path
) -> None:
    epic = _epic(repo)
    _list_services(repo, "01-both", ["worker"])

    result = derive_story_services(logger, epic, repo_dir=str(repo))

    assert result.services["01-both"] == ["worker"]
    stories = {row["slug"]: row for row in Ostler(repo).list("story", epic=epic)}
    assert stories["01-both"]["services"] == ["worker"]


def test_a_story_naming_a_book_outside_its_seeds_takes_the_union(
    logger: logging.Logger, repo: Path
) -> None:
    epic = _epic(repo)
    _list_services(repo, "01-both", ["worker", "web-app"])

    result = derive_story_services(logger, epic, repo_dir=str(repo))

    assert result.services["01-both"] == ["api-service", "worker"]


def test_deriving_twice_leaves_the_story_files_alone(
    logger: logging.Logger, repo: Path
) -> None:
    epic = _epic(repo)
    derive_story_services(logger, epic, repo_dir=str(repo))
    story_md = next(repo.glob("docs/epics/*/stories/01-both/story.md"))
    before = story_md.read_bytes()

    derive_story_services(logger, epic, repo_dir=str(repo))

    assert story_md.read_bytes() == before


def test_the_coverage_lint_fails_a_story_with_no_services(
    logger: logging.Logger, repo: Path
) -> None:
    epic = _epic(repo)
    derive_story_services(logger, epic, repo_dir=str(repo))

    report = validate_coverage(logger, f"docs/epics/{epic}", require_authored=False)

    assert not report.ok
    assert "`02-bare` lists no `services:`" in report.errors
    assert "01-both" not in report.errors


def test_the_coverage_lint_fails_a_story_naming_an_unknown_book(
    logger: logging.Logger, repo: Path
) -> None:
    epic = _epic(repo)
    assert Ostler(repo).add_seed(
        "accounts", "c", status="researched", summary="c", meta={"services": ["ghost-service"]}
    ).ok
    derive_story_services(logger, epic, repo_dir=str(repo))

    report = validate_coverage(logger, f"docs/epics/{epic}", require_authored=False)

    assert not report.ok
    assert "ghost-service" in report.errors
