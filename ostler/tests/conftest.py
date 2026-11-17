"""Shared fixtures + builders: a minimal on-disk org tree in the new markdown Concept format."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterator

import pytest

from ostler import index, registry


FOO_ID = "t-01foo"
BAR_ID = "t-01bar"
EPIC_A = "t-1"
EPIC_B = "t-2"
FOO_STORY = f"{EPIC_A}/stories/{FOO_ID}/story.md"
BAR_STORY = f"{EPIC_B}/stories/{BAR_ID}/story.md"


def present[T](value: T | None) -> T:
    """``value`` with its ``None`` ruled out — for a lookup the test arranged to hit."""
    assert value is not None
    return value


def specs_root() -> Path:
    """The specs root the per-test artifacts folder gives every repo."""
    return Path(os.environ["STABLEMATE_ARTIFACTS_DIR"]).resolve() / "specs"


def epics_root() -> Path:
    """The epics root the per-test artifacts folder gives every repo."""
    return Path(os.environ["STABLEMATE_ARTIFACTS_DIR"]).resolve() / "epics"


def staged_books(into: Path) -> list[Path]:
    """Every benchmark book of the corpus, copied under *into* and staged the way a trial stages it, with its epics and specs in the copy's artifacts dir."""
    from paddock import loader, paths
    from paddock.tasks.stablemate import upgrade_layout

    root = paths.root()
    books: list[Path] = []
    for repo in loader.data_repos(root):
        if not (repo / "docs").is_dir():
            continue
        copy = into / "-".join(repo.relative_to(paths.gold_dir(root)).parts)
        copy.mkdir(parents=True)
        for entry in repo.iterdir():
            if entry.name == "docs":
                shutil.copytree(entry, copy / "docs", symlinks=True)
            elif entry.name != ".git":
                (copy / entry.name).symlink_to(entry)
        upgrade_layout(copy)
        books.append(copy)
    return books


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data: dict) -> None:
    """A JSON file under a test root."""
    write(path, json.dumps(data, indent=2) + "\n")


def write_prefix(root: Path, prefix: str = "X") -> None:
    """A manifest at *root* whose ``repo.id_prefix`` is *prefix*, so a mint there has one to read."""
    write(root / "agents.yml", f"repo:\n  id_prefix: {prefix}\n")


def epic_md(eid: str, title: str, seeds: list[tuple[str, str, str]],
            stories: list[tuple[str, str, list[str]]] | list[tuple[str, str, list[str], str]],
            slug: str | None = None) -> str:
    """seeds: (id, status, summary); stories: (slug, title, covers) or (slug, title, covers, id)."""
    out = ["---", "type: epic", f"id: {eid}", *([f"slug: {slug}"] if slug else []),
           f"title: {title}", "---",
           f"# Epic: {title}", ""]
    for spec in registry.EPIC_SECTIONS:
        out += [f"## {spec.heading}", "", f"What {title} holds to for {spec.heading.lower()}.", ""]
    if seeds:
        out += ["## Seeds", ""]
        for sid, status, summary in seeds:
            out += [f"### {sid}", f"- status: {status}", "", summary, ""]
    out += ["## Stories", ""]
    for slug_, stitle, covers, *sid in stories:
        out += [f"### {slug_}",
                *([f"- id: {sid[0]}"] if sid else []),
                f"- title: {stitle}",
                f"- covers: {', '.join(covers) if covers else '(none)'}",
                ""]
    return "\n".join(out) + "\n"


def story_md(slug: str, title: str, status: str,
             doc_ref: str | None = None, depends: list[str] | None = None,
             fixtures: list[str] | None = None, eid: str | None = None) -> str:
    deps = [f"- Blocked by: {d}" for d in (depends or [])] or ["(none)"]
    fixes = [f"- Fixture: {name}" for name in (fixtures or [])] or ["(none)"]
    body = ["---", "type: story", f"slug: {slug}", *([f"id: {eid}"] if eid else []),
            f"status: {status}", "---",
            f"# Story: {title}", "", "## Dependencies", "", *deps, "",
            "## Fixtures", "", *fixes, "",
            "## Context", "",
            f"Why {title} matters.", "",
            *([f"Feature doc: [reference]({doc_ref}).", ""] if doc_ref else []),
            "## Acceptance Criteria", "", "- The thing works.", "",
            "## Non-Functional Acceptance Criteria", "", "- It stays fast.", "",
            "## Technical Notes", "", "`src/thing.py::run` is the seam.", "",
            "## Implementation Status", "",
            f"- **Status**: {status}"]
    return "\n".join(body) + "\n"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A clean two-epic repo."""
    root = tmp_path

    write(epics_root() / EPIC_A / "epic.md", epic_md(
        EPIC_A, "epic-a",
        seeds=[("seed-a1", "researched", "first"), ("seed-a2", "resolved", "done")],
        stories=[("01-foo", "Foo", ["seed-a1"], FOO_ID)],
        slug="epic-a",
    ))
    write(epics_root() / FOO_STORY,
          story_md("01-foo", "Foo", "Not started", eid=FOO_ID))

    write(epics_root() / EPIC_B / "epic.md", epic_md(
        EPIC_B, "epic-b",
        seeds=[("seed-b1", "researched", "bee")],
        stories=[("01-bar", "Bar", ["seed-b1"], BAR_ID)],
        slug="epic-b",
    ))
    write(epics_root() / BAR_STORY,
          story_md("01-bar", "Bar", "Not started", eid=BAR_ID))

    return root


@pytest.fixture
def index_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The resolved index directory, with the operator's real config and cache out of reach."""
    monkeypatch.setenv("STABLEMATE_CONFIG", str(tmp_path / "config" / "config.toml"))
    monkeypatch.setenv("STABLEMATE_CACHE_DIR", str(tmp_path / "cache"))
    resolved = tmp_path / "resolved-index"
    monkeypatch.setenv("OSTLER_INDEX_DIR", str(resolved))
    return resolved


def entry_files(directory: Path) -> list[Path]:
    """Every entry the store has written under *directory* — none, when it was never created."""
    if not directory.exists():
        return []
    return sorted(p for p in directory.rglob("*")
                  if p.is_file() and p.name != index.PRUNE_STAMP_NAME)


def report_of(capsys) -> dict:
    """The `--json` payload a command just printed."""
    return json.loads(capsys.readouterr().out)


def ostler_process(book: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    """One `ostler` invocation in a process of its own."""
    code = "import sys; from ostler.cli import main; sys.exit(main(sys.argv[1:]))"
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", code, "-C", str(book), *argv],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1],
        stdin=subprocess.DEVNULL, timeout=300, check=False,
    )


def warm_index(book: Path, directory: Path) -> None:
    """Populate *directory* the way a real run does — from a process that then exits."""
    done = ostler_process(book, "doctor", "--json", "--index-dir", str(directory))
    assert done.returncode in (0, 1), done.stderr or done.stdout
    assert entry_files(directory), (
        f"a run that loads a graph must populate the index, but {directory} is empty")



@pytest.fixture(autouse=True)
def _artifacts_dir_is_per_test(tmp_path_factory, monkeypatch):
    """Specs live in the user's artifacts folder, so no test may resolve to the real one."""
    monkeypatch.setenv("STABLEMATE_ARTIFACTS_DIR", str(tmp_path_factory.mktemp("artifacts")))


@pytest.fixture
def minting_root(tmp_path: Path) -> Path:
    """The test's own root, carrying the ``repo.id_prefix`` a mint there reads."""
    write_prefix(tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def _ostler_defects_raise(monkeypatch):
    """A defect inside ostler raises in a test instead of becoming the one-line internal error."""
    monkeypatch.setenv("OSTLER_DEBUG", "1")


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch):
    """Tests commit to the artifacts repo, and a CI runner has no git identity of its own."""
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "ostler tests")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "tests@example.com")


@pytest.fixture
def module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    package = tmp_path / "shop_book"
    (package / "decisions").mkdir(parents=True)
    (package / "__init__.py").write_text("")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield "shop_book"
    sys.modules.pop("shop_book", None)


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A copy of the todo fixture, the working directory and the `services` package of a book test."""
    from book_todo import FIXTURE, services_from

    copy = tmp_path / "book_todo"
    shutil.copytree(FIXTURE, copy, ignore=shutil.ignore_patterns("__pycache__", "node_modules"))
    monkeypatch.chdir(copy)
    with services_from(copy):
        yield copy


@pytest.fixture
def todo_app() -> Iterator:
    from book_todo import module

    server = module("app").TodoServer().start()
    yield server
    server.stop()


@pytest.fixture
def own_book(monkeypatch) -> None:
    """The fixture's `services` package imported anew, so its address is read from this test's port."""
    for name in [n for n in sys.modules if n == "services" or n.startswith("services.")]:
        monkeypatch.delitem(sys.modules, name)
