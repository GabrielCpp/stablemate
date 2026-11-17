"""The parse products, served from the index — parsed once per content, reused everywhere."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from ostler import doctor, index, markdown
from ostler.cli import main

from conftest import EPIC_A, entry_files, report_of, warm_index, epics_root


class _Seam:
    """`ostler.model`, resolved at attribute access instead of at import."""

    def __getattr__(self, name: str) -> Any:
        return getattr(importlib.import_module("ostler.model"), name)


model = _Seam()

GRAPH_COMMANDS: dict[str, list[str]] = {
    "doctor": ["doctor"],
    "list": ["list", "--type", "story"],
    "search": ["search", "Foo"],
    "next-epic": ["next-epic"],
    "next-story": ["next-story", "epic-a"],
    "find": ["find", "program"],
}

COMMANDS = pytest.mark.parametrize(
    "argv", list(GRAPH_COMMANDS.values()), ids=list(GRAPH_COMMANDS)
)

GLOBAL_CHECKS = ("_check_milestones", "_check_epic")


def record_parses(monkeypatch: pytest.MonkeyPatch) -> tuple[list[str], list[str]]:
    """Every text handed to the splitter, and every body whose sections were built."""
    texts: list[str] = []
    bodies: list[str] = []
    real_split = markdown.split
    real_sections = markdown._build_sections

    def split(text: str) -> markdown.MarkdownDoc:
        texts.append(text)
        return real_split(text)

    def build(body: str) -> list[markdown.Section]:
        bodies.append(body)
        return real_sections(body)

    monkeypatch.setattr(markdown, "split", split)
    monkeypatch.setattr(markdown, "_build_sections", build)
    return texts, bodies


def planning_docs(book: Path) -> list[Path]:
    """The documents this increment's read-only call sites all read."""
    return sorted(epics_root().rglob("*.md"))


def parse_counts(path: Path, texts: list[str], bodies: list[str]) -> tuple[int, int]:
    """How many times *path*'s content was split, and how many times its body was sectioned."""
    text = path.read_text(encoding="utf-8")
    return (sum(1 for t in texts if t == text),
            sum(1 for b in bodies if b and text.endswith(b)))


def counted(book: Path, texts: list[str], bodies: list[str]) -> dict[str, tuple[int, int]]:
    return {path.relative_to(epics_root()).as_posix(): parse_counts(path, texts, bodies)
            for path in planning_docs(book)}


def recording(name: str, real, seen: set[str]):
    def wrapper(*args, **kwargs):
        seen.add(name)
        return real(*args, **kwargs)

    return wrapper


def test_a_document_is_parsed_once_per_run_however_many_readers_want_it(
        repo: Path, index_home: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    """Cold index, one run: the four in-run readers agree on one parse each."""
    texts, bodies = record_parses(monkeypatch)

    main(["-C", str(repo), "doctor", "--json"])
    capsys.readouterr()

    counts = counted(repo, texts, bodies)
    assert all(sum(c) for c in counts.values()), f"nothing was parsed at all: {counts}"
    repeated = {name: c for name, c in counts.items() if max(c) > 1}
    assert not repeated, f"parsed more than once in one run: {repeated}"


def test_a_second_process_parses_nothing_it_already_has(
        repo: Path, tmp_path: Path, index_home: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    """The point of a *persistent* index: the warm run splits none of the book at all."""
    directory = tmp_path / "index"
    warm_index(repo, directory)
    texts, bodies = record_parses(monkeypatch)

    assert main(["-C", str(repo), "doctor", "--json", "--index-dir", str(directory)]) == 0
    report = report_of(capsys)

    reparsed = {name: c for name, c in counted(repo, texts, bodies).items() if any(c)}
    assert not reparsed, f"re-parsed against a warm index: {reparsed}"
    assert report["index"]["hits"] > 0



def test_a_second_process_reads_the_epics_and_stories_off_the_index_too(
        repo: Path, tmp_path: Path, index_home: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    directory = tmp_path / "index"
    warm_index(repo, directory)
    texts, bodies = record_parses(monkeypatch)

    assert main(["-C", str(repo), "doctor", "--json", "--index-dir", str(directory)]) == 0
    _ = report_of(capsys)

    planning = sorted(epics_root().rglob("*.md"))
    reparsed = {path.relative_to(epics_root()).as_posix(): parse_counts(path, texts, bodies)
                for path in planning}
    assert planning and not {name: c for name, c in reparsed.items() if any(c)}

def test_the_read_only_accessor_hands_back_one_document_per_file(repo: Path, index_home: Path):
    path = epics_root() / EPIC_A / "epic.md"

    with index.session(repo):
        first = model.read_doc(path)
        second = model.read_doc(path)

    assert second is first
    assert (first.frontmatter or {})["type"] == "epic"
    assert first.sections, "the shared document carries its parsed sections, not just frontmatter"


def test_a_writer_never_receives_a_shared_cached_document(repo: Path, index_home: Path):
    """`replace_body` mutates in place and drops the parsed sections."""
    path = epics_root() / EPIC_A / "epic.md"

    with index.session(repo):
        shared = model.read_doc(path)
        titles = [s.title for s in shared.sections]

        writer_doc = markdown.split(path.read_text(encoding="utf-8"))
        assert writer_doc is not shared

        writer_doc.replace_body(["# Replaced", ""])

        assert model.read_doc(path) is shared
        assert [s.title for s in model.read_doc(path).sections] == titles


@COMMANDS
def test_every_graph_loading_command_populates_the_index(
        repo: Path, tmp_path: Path, index_home: Path, argv: list[str], capsys):
    """Including the read-only query and listing commands."""
    directory = tmp_path / "index"

    main(["-C", str(repo), *argv, "--index-dir", str(directory)])
    capsys.readouterr()

    assert entry_files(directory), f"`{' '.join(argv)}` loaded a graph and indexed nothing"


def test_the_graph_global_checks_run_again_against_a_warm_index(
        repo: Path, tmp_path: Path, index_home: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    directory = tmp_path / "index"
    warm_index(repo, directory)
    seen: set[str] = set()
    for name in GLOBAL_CHECKS:
        monkeypatch.setattr(doctor, name, recording(name, getattr(doctor, name), seen))

    assert main(["-C", str(repo), "doctor", "--json", "--index-dir", str(directory)]) == 0
    report = report_of(capsys)

    assert report["index"]["hits"] > 0, "the run has to be a warm one for this to mean anything"
    assert seen == set(GLOBAL_CHECKS), f"not recomputed on a warm run: {set(GLOBAL_CHECKS) - seen}"

