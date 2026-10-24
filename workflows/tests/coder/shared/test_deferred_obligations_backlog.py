"""A required obligation the book gives no runnable check lands on the register for the book, not in the story's QA."""
from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from ostler import Ostler
from ostler.register import Record
from workhorse._vendor.stablemate_core import config as core_config
from workhorse.pyflow.blueprint import node_spec
from workhorse_workflows.coder.shared.backlog import file_deferred_obligations, select_fix_item
from workhorse_workflows.coder.shared.docs import CONTEXT_FILE

PAGE = "docs/services/web-app/gui/screens/reports.md"
UNTYPED = (
    f"`{PAGE}#empty-alert` sits under a heading that gives its sections no type, "
    "so no `verify:` bullet in it binds to a claim"
)


def _obligation(node: str, detail: str, *, required: bool = True) -> dict:
    return {
        "id": f"okf:{node}:contract",
        "node": node,
        "source": node.partition("#")[0],
        "required": required,
        "deferred": {"kind": "no-verify-declared", "detail": detail},
    }


def _spec(
    tmp_path: Path, *obligations: dict, services: str = "docs/services", story: dict | None = None
) -> str:
    spec = tmp_path / "specs" / "ACME-1"
    spec.mkdir(parents=True, exist_ok=True)
    context: dict = {"servicesRoot": services, "obligations": [*obligations, {"id": "okf:proved", "required": True}]}
    if story is not None:
        context["story"] = story
    (spec / CONTEXT_FILE).write_text(json.dumps(context), encoding="utf-8")
    return str(spec)


@pytest.fixture(autouse=True)
def _agents_dir_is_ignored(repo: Path, git: Callable[..., subprocess.CompletedProcess]) -> None:
    (repo / ".gitignore").write_text(".agents/\n", encoding="utf-8")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-qm", "ignore the agents dir")


@pytest.fixture
def artifacts() -> Path:
    root = core_config.ensure_artifacts_repo()
    subprocess.run(["git", "-C", str(root), "commit", "-q", "--allow-empty", "-m", "init"], check=True)
    return root


@pytest.fixture
def two_repos(
    tmp_path: Path,
    name_workspace: Callable[[dict[str, Path]], None],
) -> dict[str, Path]:
    repos = {name: tmp_path / "ws" / name for name in ("api-service", "web-app")}
    for path in repos.values():
        path.mkdir(parents=True)
    name_workspace(repos)
    return repos


def _subjects(root: Path) -> list[str]:
    return subprocess.run(
        ["git", "-C", str(root), "log", "--format=%s"], capture_output=True, text=True, check=True
    ).stdout.splitlines()


def _records(repo: Path) -> list[Record]:
    return list(Ostler(repo).records().records)


def test_the_filer_is_a_node_a_flow_can_call() -> None:
    assert node_spec(file_deferred_obligations)


def test_each_page_with_deferred_checks_becomes_one_record_in_one_artifacts_commit(
    repo: Path,
    tmp_path: Path,
    artifacts: Path,
    logger: logging.Logger,
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    head = git(repo, "rev-parse", "HEAD").stdout
    spec = _spec(
        tmp_path,
        _obligation(PAGE, "the book declares no check for this obligation to prove"),
        _obligation(f"{PAGE}#empty-alert", UNTYPED),
        _obligation(f"{PAGE}#export", UNTYPED.replace("#empty-alert", "#export")),
        _obligation("docs/services/web-app/gui/screens/home.md#banner", "skipped", required=False),
        story={"id": "ACME-1", "externalKey": "", "slug": "reports"},
    )

    drained = file_deferred_obligations(logger, spec_dir=spec, repo_dir=str(repo))

    assert (drained.appended, drained.skipped) == (1, 0), drained
    [record] = _records(repo)
    assert (record.repo, record.area, record.filed_by, record.pattern, record.status) == (
        "acme", "book", "qa-deferred", "add-runnable-check", "open")
    assert record.symbols == ["web-app/gui/screens/reports.md"]
    assert record.source_story == "ACME-1"
    assert record.summary == "Book page `docs/services/web-app/gui/screens/reports.md` gives QA no check it can run"
    assert "the page itself, `#empty-alert`, `#export`" in record.body, record.body
    assert record.body.count("A section sits under a heading") == 1, record.body
    assert "home.md" not in record.body
    assert _subjects(artifacts) == ["chore(acme): file the book checks qa could not run", "init"]
    assert git(repo, "rev-parse", "HEAD").stdout == head
    assert git(repo, "status", "--porcelain").stdout == ""


def test_the_same_page_twice_files_once(
    repo: Path,
    tmp_path: Path,
    artifacts: Path,
    logger: logging.Logger,
) -> None:
    spec = _spec(tmp_path, _obligation(f"{PAGE}#export", UNTYPED))

    first = file_deferred_obligations(logger, spec_dir=spec, repo_dir=str(repo))
    again = file_deferred_obligations(logger, spec_dir=spec, repo_dir=str(repo))

    assert (first.appended, first.skipped) == (1, 0), first
    assert (again.appended, again.skipped) == (0, 1), again
    assert len(_records(repo)) == 1
    assert len(_subjects(artifacts)) == 2


def test_a_story_less_context_files_an_empty_source_story(
    repo: Path,
    tmp_path: Path,
    artifacts: Path,
    logger: logging.Logger,
) -> None:
    file_deferred_obligations(logger, spec_dir=_spec(tmp_path, _obligation(PAGE, "none")), repo_dir=str(repo))

    [record] = _records(repo)
    assert record.source_story == ""


def test_a_two_repo_workspace_places_the_page_by_its_book_prefix(
    repo: Path,
    tmp_path: Path,
    artifacts: Path,
    two_repos: dict[str, Path],
    logger: logging.Logger,
) -> None:
    page = "web-app/docs/services/gui/screens/reports.md"
    spec = _spec(tmp_path, _obligation(f"{page}#export", UNTYPED), services="web-app/docs/services")

    drained = file_deferred_obligations(logger, spec_dir=spec, repo_dir=str(repo), workspace="acme")

    assert drained.appended == 1, drained
    [record] = _records(repo)
    assert (record.repo, record.symbols) == ("web-app", ["gui/screens/reports.md"])
    assert _subjects(artifacts)[0] == "chore(web-app): file the book checks qa could not run"
    assert all(not any(p.iterdir()) for p in two_repos.values())


def test_an_absolute_services_root_still_places_the_page_by_its_book_prefix(
    repo: Path,
    tmp_path: Path,
    artifacts: Path,
    two_repos: dict[str, Path],
    logger: logging.Logger,
) -> None:
    page = "api-service/docs/services/gui/screens/reports.md"
    spec = _spec(tmp_path, _obligation(f"{page}#export", UNTYPED), services=str(repo / "api-service" / "docs" / "services"))

    file_deferred_obligations(logger, spec_dir=spec, repo_dir=str(repo), workspace="acme")

    [record] = _records(repo)
    assert (record.repo, record.symbols) == ("api-service", ["gui/screens/reports.md"])


def test_a_page_no_repository_of_a_two_repo_workspace_owns_is_refused_with_the_known_names(
    repo: Path,
    tmp_path: Path,
    artifacts: Path,
    two_repos: dict[str, Path],
    logger: logging.Logger,
    caplog: pytest.LogCaptureFixture,
) -> None:
    spec = _spec(tmp_path, _obligation(f"{PAGE}#export", UNTYPED))

    with caplog.at_level("INFO"):
        drained = file_deferred_obligations(logger, spec_dir=spec, repo_dir=str(repo), workspace="acme")

    assert (drained.appended, drained.skipped) == (0, 1), drained
    assert _records(repo) == []
    assert _subjects(artifacts) == ["init"]
    messages = [r.getMessage() for r in caplog.records]
    assert any(PAGE in m and "api-service" in m and "web-app" in m for m in messages), messages


def test_the_fix_lane_leaves_book_checks_for_the_book(
    repo: Path,
    tmp_path: Path,
    artifacts: Path,
    logger: logging.Logger,
) -> None:
    spec = _spec(tmp_path, _obligation(f"{PAGE}#export", UNTYPED), services=str(repo / "docs" / "services"))

    file_deferred_obligations(logger, spec_dir=spec, repo_dir=str(repo))

    assert len(_records(repo)) == 1
    assert not select_fix_item(logger, repo_dir=str(repo)).has_fix


def test_a_context_with_nothing_deferred_files_and_commits_nothing(
    repo: Path,
    tmp_path: Path,
    artifacts: Path,
    logger: logging.Logger,
) -> None:
    drained = file_deferred_obligations(logger, spec_dir=_spec(tmp_path), repo_dir=str(repo))

    assert drained.appended == 0, drained
    assert _subjects(artifacts) == ["init"]
