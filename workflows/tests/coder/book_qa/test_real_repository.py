"""The touched-books lane against a real git repository, with the real `ostler book` commands."""
from __future__ import annotations

import logging
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from workhorse_workflows.coder.book_qa import nodes as book_nodes

SERVICE = """from ostler.book import App, Screen, Service

{screens}
service = Service(
    name="{name}",
    new_model=lambda today: None,
    surface=lambda env: None,
    journeys=(),
    stack=lambda log: None,
    screens=({names}),
    app=App(roots=("src/{name}",), verified="VERIFIED", ignore=()),
)
"""

SCREEN = """class {cls}(Screen):
    source = ("src/{name}/{file}.py",)

"""

Git = Callable[..., subprocess.CompletedProcess[str]]


def _write(root: Path, rel: str, text: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _book(root: Path, name: str, files: tuple[str, ...]) -> None:
    classes = [file.capitalize() for file in files]
    screens = "".join(SCREEN.format(cls=cls, name=name, file=file) for cls, file in zip(classes, files, strict=True))
    _write(root, f"services/{name}/__init__.py", "")
    _write(root, f"services/{name}/service.py", SERVICE.format(name=name, screens=screens, names="".join(f"{cls}, " for cls in classes)))
    for file in files:
        _write(root, f"src/{name}/{file}.py", "one\n")


def _head(git: Git, root: Path) -> str:
    return git(root, "rev-parse", "HEAD").stdout.strip()


def _commit(git: Git, root: Path, message: str, *paths: str) -> None:
    git(root, "add", *paths)
    git(root, "commit", "-qm", message, "--", *paths)


def _verified(root: Path, name: str) -> str:
    return (root / "services" / name / "VERIFIED").read_text(encoding="utf-8").strip()


@pytest.fixture
def books(repo: Path, git: Git) -> Path:
    """Three books verified at the first commit, then an older commit that moved `c` with no story behind it."""
    _write(repo, "services/__init__.py", "")
    _book(repo, "a", ("home",))
    _book(repo, "b", ("page",))
    _book(repo, "c", ("old", "new"))
    _commit(git, repo, "chore: add the books", "services", "src")
    first = _head(git, repo)
    for name in ("a", "b", "c"):
        _write(repo, f"services/{name}/VERIFIED", first + "\n")
    _commit(git, repo, "chore: verify the books", "services")
    _write(repo, "src/c/old.py", "two\n")
    _commit(git, repo, "fix: change c on its own", "src/c/old.py")
    _write(repo, "src/b/page.py", "two\n")
    _commit(git, repo, "feat: change b for the story\n\nStory: S-1", "src/b/page.py")
    return repo


def test_a_story_that_declares_one_service_covers_it_and_the_book_its_commits_touched(
    books: Path, logger: logging.Logger
) -> None:
    covered = book_nodes.covered_services(logger, ["a"], repo_dir=str(books), story_slug="s-1", story_id="S-1")

    assert covered.services == ["a", "b"], covered


def test_a_book_current_at_the_story_base_is_stamped_and_a_current_book_is_left_alone(
    books: Path, git: Git, logger: logging.Logger
) -> None:
    first = _verified(books, "a")

    played = book_nodes.stamp_books_verified(logger, ["a", "b"], story_slug="s-1", story_id="S-1", repo_dir=str(books))

    assert played.exit_code == 0, played
    assert _head(git, books).startswith(_verified(books, "b"))
    assert _verified(books, "a") == first


def test_a_second_visit_after_a_commit_that_changes_no_app_source_stamps_nothing(
    books: Path, git: Git, logger: logging.Logger
) -> None:
    book_nodes.stamp_books_verified(logger, ["b"], story_slug="s-1", story_id="S-1", repo_dir=str(books))
    stamped = _verified(books, "b")
    _write(books, "README.md", "# changed\n")
    _commit(git, books, "docs: reword the readme", "README.md")

    book_nodes.stamp_books_verified(logger, ["b"], story_slug="s-1", story_id="S-1", repo_dir=str(books))

    assert _verified(books, "b") == stamped
    assert not _head(git, books).startswith(stamped)


def test_a_book_the_story_did_not_touch_is_not_covered(books: Path, logger: logging.Logger) -> None:
    covered = book_nodes.covered_services(logger, ["a"], repo_dir=str(books), story_slug="s-1", story_id="S-1")

    assert "c" not in covered.services, covered


def test_a_book_behind_before_the_story_is_covered_when_the_story_touches_it_and_never_stamped(
    books: Path, git: Git, logger: logging.Logger
) -> None:
    first = _verified(books, "c")
    _write(books, "src/c/new.py", "two\n")
    _commit(git, books, "feat: change c for the second story\n\nStory: S-2", "src/c/new.py")

    covered = book_nodes.covered_services(logger, ["a"], repo_dir=str(books), story_slug="s-2", story_id="S-2")
    played = book_nodes.stamp_books_verified(logger, covered.services, story_slug="s-2", story_id="S-2", repo_dir=str(books))

    assert covered.services == ["a", "c"], covered
    assert played.exit_code == 0, played
    assert _verified(books, "c") == first


def test_the_selection_runs_for_real_over_the_story_diff(books: Path, logger: logging.Logger, tmp_path: Path) -> None:
    plan = book_nodes.book_plan(logger, "b", str(tmp_path / "spec"), story_slug="s-1", story_id="S-1", repo_dir=str(books))

    assert plan.exit_code == 0, plan.output
    assert plan.service == "b" and plan.uncovered == [], plan
    assert plan.changed == 1, plan
    assert (tmp_path / "spec" / "qa" / "book" / "b-affected.json").is_file()


def test_on_a_shared_trunk_a_foreign_commits_unnamed_file_leaves_the_stamp_and_sends_no_refusal(
    books: Path, git: Git, logger: logging.Logger
) -> None:
    before = _verified(books, "b")
    _write(books, "src/b/extra.py", "x\n")
    _commit(git, books, "feat: other\n\nStory: S-9", "src/b/extra.py")

    played = book_nodes.stamp_books_verified(logger, ["b"], story_slug="s-1", story_id="S-1", repo_dir=str(books))

    assert played.exit_code == 0, played
    assert _verified(books, "b") == before


def test_the_storys_own_unnamed_file_is_still_refused(books: Path, git: Git, logger: logging.Logger) -> None:
    _write(books, "src/b/extra.py", "x\n")
    _commit(git, books, "feat: more of the story\n\nStory: S-1", "src/b/extra.py")

    played = book_nodes.stamp_books_verified(logger, ["b"], story_slug="s-1", story_id="S-1", repo_dir=str(books))

    assert played.exit_code == 1, played
    assert "not verified" in played.output


def test_a_foreign_commit_after_the_story_does_not_widen_the_covered_books(
    books: Path, git: Git, logger: logging.Logger
) -> None:
    _write(books, "src/c/new.py", "two\n")
    _commit(git, books, "feat: change c for another story\n\nStory: S-9", "src/c/new.py")

    covered = book_nodes.covered_services(logger, ["a"], repo_dir=str(books), story_slug="s-1", story_id="S-1")

    assert covered.services == ["a", "b"], covered


OUTSIDE = """from ostler.book import Documentation, Environment, Screen, Service, State


class Home(Screen):
    first = True
    source = ("https://vendor.example.com/docs/home",)


service = Service(
    name="vendor",
    new_model=State,
    surface=lambda env: None,
    journeys=(),
    stack=lambda log: None,
    screens=(Home,),
    languages=("en",),
    environments={"live": Environment(name="live", hosts={})},
    default_environment="live",
    documentation=Documentation(sites=("https://vendor.example.com/docs",)),
)
"""


def test_a_book_of_an_outside_system_is_never_touched_stamped_or_refused(
    books: Path, git: Git, logger: logging.Logger, caplog: pytest.LogCaptureFixture
) -> None:
    _write(books, "services/vendor/__init__.py", "")
    _write(books, "services/vendor/service.py", OUTSIDE)
    subprocess.run([sys.executable, "-m", "ostler.book", "index", "services.vendor"], cwd=books, check=True, capture_output=True)
    _commit(git, books, "docs: add the book of the vendor\n\nStory: S-1", "services/vendor")

    covered = book_nodes.covered_services(logger, ["a"], repo_dir=str(books), story_slug="s-1", story_id="S-1")
    with caplog.at_level(logging.INFO, logger=logger.name):
        played = book_nodes.stamp_books_verified(logger, ["vendor"], story_slug="s-1", story_id="S-1", repo_dir=str(books))
    checked = book_nodes.book_check(logger, "vendor", repo_dir=str(books))

    assert "vendor" not in covered.services, covered
    assert played.exit_code == 0, played
    assert not (books / "services" / "vendor" / "VERIFIED").exists()
    assert checked.exit_code == 0, checked
    assert "the book of services.vendor describes an outside system, nothing to stamp" in caplog.text, caplog.text


def test_a_book_of_an_outside_system_selects_no_play_and_is_not_a_usage_error(
    books: Path, git: Git, logger: logging.Logger, tmp_path: Path
) -> None:
    _write(books, "services/vendor/__init__.py", "")
    _write(books, "services/vendor/service.py", OUTSIDE)
    subprocess.run([sys.executable, "-m", "ostler.book", "index", "services.vendor"], cwd=books, check=True, capture_output=True)
    _commit(git, books, "docs: add the book of the vendor\n\nStory: S-1", "services/vendor")

    plan = book_nodes.book_plan(logger, "vendor", str(tmp_path / "spec"), story_slug="s-1", story_id="S-1", repo_dir=str(books))

    assert plan.exit_code == 0, plan
    assert plan.plan == "none", plan
    assert not plan.only and not plan.by_journey and not plan.uncovered, plan
    assert "services.vendor describes an outside system" in plan.reason, plan
