"""The parse products, served from the index — parsed once per content, reused everywhere."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from ostler import doctor, index, markdown
from ostler.cli import main

from conftest import UI_DASH_UNLINKED, entry_files, report_of, screen_md, warm_index, write


class _Seam:
    """`ostler.model`, resolved at attribute access instead of at import."""

    def __getattr__(self, name: str) -> Any:
        return getattr(importlib.import_module("ostler.model"), name)


model = _Seam()

GRAPH_COMMANDS: dict[str, list[str]] = {
    "doctor": ["doctor"],
    "trace": ["trace", "seed-a1"],
    "list": ["list", "--type", "story"],
    "search": ["search", "Foo"],
    "graph": ["graph"],
    "reach": ["reach", "--from", "docs/features/ui/dash.md"],
    "locators": ["locators"],
    "next-epic": ["next-epic"],
    "next-story": ["next-story", "epic-a"],
    "find": ["find", "program"],
}

COMMANDS = pytest.mark.parametrize(
    "argv", list(GRAPH_COMMANDS.values()), ids=list(GRAPH_COMMANDS)
)

GLOBAL_CHECKS = ("_check_reachability", "_check_locators", "_check_milestones",
                 "_check_epic", "_check_frozen")


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


def feature_docs(book: Path) -> list[Path]:
    """The documents this increment's five read-only call sites all read."""
    return sorted((book / "docs" / "features").rglob("*.md"))


def parse_counts(path: Path, texts: list[str], bodies: list[str]) -> tuple[int, int]:
    """How many times *path*'s content was split, and how many times its body was sectioned."""
    text = path.read_text(encoding="utf-8")
    return (sum(1 for t in texts if t == text),
            sum(1 for b in bodies if b and text.endswith(b)))


def counted(book: Path, texts: list[str], bodies: list[str]) -> dict[str, tuple[int, int]]:
    return {path.relative_to(book).as_posix(): parse_counts(path, texts, bodies)
            for path in feature_docs(book)}


def recording(name: str, real, seen: set[str]):
    def wrapper(*args, **kwargs):
        seen.add(name)
        return real(*args, **kwargs)

    return wrapper


def test_a_document_is_parsed_once_per_run_however_many_readers_want_it(
        ui_book: Path, index_home: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    """Cold index, one run: the four in-run readers agree on one parse each."""
    texts, bodies = record_parses(monkeypatch)

    main(["-C", str(ui_book), "doctor", "--json"])
    capsys.readouterr()

    counts = counted(ui_book, texts, bodies)
    assert all(sum(c) for c in counts.values()), f"nothing was parsed at all: {counts}"
    repeated = {name: c for name, c in counts.items() if max(c) > 1}
    assert not repeated, f"parsed more than once in one run: {repeated}"


def test_a_second_process_parses_nothing_it_already_has(
        ui_book: Path, tmp_path: Path, index_home: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    """The point of a *persistent* index: the warm run splits none of the book at all."""
    directory = tmp_path / "index"
    warm_index(ui_book, directory)
    texts, bodies = record_parses(monkeypatch)

    assert main(["-C", str(ui_book), "doctor", "--json", "--index-dir", str(directory)]) == 0
    report = report_of(capsys)

    reparsed = {name: c for name, c in counted(ui_book, texts, bodies).items() if any(c)}
    assert not reparsed, f"re-parsed against a warm index: {reparsed}"
    assert report["index"]["hits"] > 0


def test_the_ui_nodes_come_off_the_index_too(
        ui_book: Path, tmp_path: Path, index_home: Path, monkeypatch: pytest.MonkeyPatch):
    """Not only the document — the nodes derived from it."""
    real = importlib.import_module("ostler.model")
    directory = tmp_path / "index"
    expected = {(n.id, n.type, n.line, n.parent, n.path) for n in real.load(ui_book).ui_nodes}
    assert expected, "the fixture book has no UI nodes to serve"
    warm_index(ui_book, directory)

    real._DOC_CACHE.clear()
    real._FEATURE_DOC_CACHE.clear()
    derived: list[Path] = []
    parse_ui_nodes = real._parse_ui_nodes

    def derive(doc, path: Path, root: Path):
        derived.append(path)
        return parse_ui_nodes(doc, path, root)

    monkeypatch.setattr(real, "_parse_ui_nodes", derive)
    with index.session(ui_book, directory=directory):
        nodes = real.load(ui_book).ui_nodes

    assert not derived, f"re-derived the nodes of {[p.name for p in derived]} on a warm index"
    assert {(n.id, n.type, n.line, n.parent, n.path) for n in nodes} == expected


def test_a_warm_doctor_scans_no_file_for_its_links(
        ui_book: Path, tmp_path: Path, index_home: Path, monkeypatch: pytest.MonkeyPatch):
    """Link validation is document-wide: every file in the book, every run."""
    real = importlib.import_module("ostler.model")
    directory = tmp_path / "index"
    dash = ui_book / "docs" / "features" / "ui" / "dash.md"
    expected = tuple(markdown.iter_links(dash.read_text(encoding="utf-8")))
    assert expected, "the fixture file has no links to serve"
    warm_index(ui_book, directory)

    real._DOC_CACHE.clear()
    scanned: list[str] = []
    iter_links = markdown.iter_links

    def scan(text: str):
        scanned.append(text)
        return iter_links(text)

    monkeypatch.setattr(markdown, "iter_links", scan)
    with index.session(ui_book, directory=directory):
        links = real.read_links(dash)

    assert not scanned, "re-scanned a file's links on a warm index"
    assert links == expected


def test_the_read_only_accessor_hands_back_one_document_per_file(ui_book: Path, index_home: Path):
    path = ui_book / "docs" / "features" / "area" / "rec.md"

    with index.session(ui_book):
        first = model.read_doc(path)
        second = model.read_doc(path)

    assert second is first
    assert (first.frontmatter or {})["slug"] == "rec"
    assert first.sections, "the shared document carries its parsed sections, not just frontmatter"


def test_a_writer_never_receives_a_shared_cached_document(ui_book: Path, index_home: Path):
    """`replace_body` mutates in place and drops the parsed sections."""
    path = ui_book / "docs" / "features" / "area" / "rec.md"

    with index.session(ui_book):
        shared = model.read_doc(path)
        titles = [s.title for s in shared.sections]

        writer_doc = markdown.split(path.read_text(encoding="utf-8"))
        assert writer_doc is not shared

        writer_doc.replace_body(["# Replaced", ""])

        assert model.read_doc(path) is shared
        assert [s.title for s in model.read_doc(path).sections] == titles


def test_a_command_that_writes_is_never_served_a_stale_document(
        ui_book: Path, tmp_path: Path, index_home: Path, capsys):
    """A file edited between two runs is read fresh, and its new content is indexed in turn."""
    directory = tmp_path / "index"
    warm_index(ui_book, directory)
    before = len(entry_files(directory))

    write(ui_book / "docs" / "features" / "ui" / "detail.md",
          screen_md("detail", "Renamed Detail"))

    assert main(["-C", str(ui_book), "list", "--type", "screen", "--json",
                 "--index-dir", str(directory)]) == 0
    rows = json.loads(capsys.readouterr().out)

    assert "Renamed Detail" in {row.get("title") for row in rows}
    assert len(entry_files(directory)) > before, "the new content was never indexed"


@COMMANDS
def test_every_graph_loading_command_populates_the_index(
        ui_book: Path, tmp_path: Path, index_home: Path, argv: list[str], capsys):
    """Including the read-only query and listing commands."""
    directory = tmp_path / "index"

    main(["-C", str(ui_book), *argv, "--index-dir", str(directory)])
    capsys.readouterr()

    assert entry_files(directory), f"`{' '.join(argv)}` loaded a graph and indexed nothing"


def test_the_graph_global_checks_run_again_against_a_warm_index(
        ui_book: Path, tmp_path: Path, index_home: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    directory = tmp_path / "index"
    warm_index(ui_book, directory)
    seen: set[str] = set()
    for name in GLOBAL_CHECKS:
        monkeypatch.setattr(doctor, name, recording(name, getattr(doctor, name), seen))

    assert main(["-C", str(ui_book), "doctor", "--json", "--index-dir", str(directory)]) == 0
    report = report_of(capsys)

    assert report["index"]["hits"] > 0, "the run has to be a warm one for this to mean anything"
    assert seen == set(GLOBAL_CHECKS), f"not recomputed on a warm run: {set(GLOBAL_CHECKS) - seen}"


def test_a_global_finding_appears_from_a_change_to_a_different_file(
        ui_book: Path, tmp_path: Path, index_home: Path, capsys):
    """Reachability is transitive, which is exactly what a per-file cache cannot hold."""
    directory = tmp_path / "index"
    warm_index(ui_book, directory)
    write(ui_book / "docs" / "features" / "ui" / "dash.md",
          screen_md("dash", "Dash", entry=True, body=UI_DASH_UNLINKED))

    assert main(["-C", str(ui_book), "doctor", "--json", "--index-dir", str(directory)]) == 1
    report = report_of(capsys)

    unreachable = [f for f in report["findings"] if f["code"] == "unreachable-screen"]
    assert [f["ref"] for f in unreachable] == ["docs/features/ui/detail.md"]
    assert report["index"]["hits"] > 0, "detail.md was unchanged and should have been served warm"
