"""The parse products, served from the index — parsed once per content, reused everywhere.

One `doctor` run reads the same feature document several times over: the graph load wants its
frontmatter and its UI nodes, the per-file UI check re-splits it, conformance re-splits it again,
and the link resolver splits every file a link points into so it can list that file's anchors.
Each of those is the *same* parse of the *same* bytes, and on a real book the splitting is most of
the wall clock.

What this file pins down is behaviour, not the shape of the accessor:

* a document with one content sha is parsed **once** per run, no matter how many readers want it;
* a *second* run, in a *second process*, parses it **zero** times — the products come off disk;
* the readers are read-only. A writer still parses for itself, because `replace_body` mutates the
  document in place and drops its parsed sections: hand a writer the shared instance and every
  later reader in that run sees a document that no longer matches the file;
* every command that loads a graph fills the index, not just `doctor`;
* the graph-global checks — reachability, locators, milestones, epics, frozen entities — are
  recomputed from the (cached) per-file products every run and never served whole. A cached answer
  to a global question goes stale the moment a *different* file changes.

The planned seam is a read-only document accessor on `ostler.model`, generalised from the
feature-book cache that is there now, plus the anchor computation in `ostler.links`. It is reached
through the CLI wherever a CLI can reach it, so these tests hold whatever the accessor ends up
being called.
"""

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
    """`ostler.model`, resolved at attribute access instead of at import.

    The accessor this increment adds does not exist yet, and a module-level
    `from ostler.model import read_doc` would make that a *collection* error — pytest reports an
    interrupted run rather than a red test, and `ty` fails `make lint` before any test runs at
    all. Going through the module keeps the failure one red per test, raised at the missing seam.
    """

    def __getattr__(self, name: str) -> Any:
        return getattr(importlib.import_module("ostler.model"), name)


model = _Seam()

#: Every leaf command that loads a graph. Mirrors `test_index_cli.GRAPH_COMMANDS`, against the
#: `ui_book` fixture (so `reach` has a real screen to start from).
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

#: The checks whose answer depends on the whole graph rather than on any one file.
GLOBAL_CHECKS = ("_check_reachability", "_check_locators", "_check_milestones",
                 "_check_epic", "_check_frozen")


def record_parses(monkeypatch: pytest.MonkeyPatch) -> tuple[list[str], list[str]]:
    """Every text handed to the splitter, and every body whose sections were built.

    Both halves, because both are the expensive part: `split` yields the frontmatter, and
    `_build_sections` — lazy, once per document — yields the sections, bullets and links every
    later reader walks.
    """
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


# ---------------------------------------------------------------------------
# (1) one parse per distinct content sha, per run
# ---------------------------------------------------------------------------
def test_a_document_is_parsed_once_per_run_however_many_readers_want_it(
        ui_book: Path, index_home: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    """Cold index, one run: the four in-run readers agree on one parse each.

    Scoped to the feature book because that is what this increment's five call sites read; the
    epic and story documents have readers of their own that it does not touch.
    """
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
    """Not only the document — the nodes derived from it.

    Deriving a file's UI nodes costs a further markdown pass *per node* (each node's region is
    re-parsed for its links), which on a real book was the larger half of a warm `model.load`.
    The one part of a node that is not a function of the file's bytes is its absolute `path`, so
    that is what the entry leaves out and the load puts back.
    """
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


# ---------------------------------------------------------------------------
# (2) read-only callers share; a writer never gets the shared document
# ---------------------------------------------------------------------------
def test_the_read_only_accessor_hands_back_one_document_per_file(ui_book: Path, index_home: Path):
    path = ui_book / "docs" / "features" / "area" / "rec.md"

    with index.session(ui_book):
        first = model.read_doc(path)
        second = model.read_doc(path)

    assert second is first
    assert (first.frontmatter or {})["slug"] == "rec"
    assert first.sections, "the shared document carries its parsed sections, not just frontmatter"


def test_a_writer_never_receives_a_shared_cached_document(ui_book: Path, index_home: Path):
    """`replace_body` mutates in place and drops the parsed sections.

    A writer served the shared instance would leave every later reader in the run holding a
    document that no longer matches the file on disk — so writers keep splitting for themselves.
    """
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


# ---------------------------------------------------------------------------
# (3) every command that loads a graph populates the index
# ---------------------------------------------------------------------------
@COMMANDS
def test_every_graph_loading_command_populates_the_index(
        ui_book: Path, tmp_path: Path, index_home: Path, argv: list[str], capsys):
    """Including the read-only query and listing commands.

    A book is walked far more often by `list`/`trace`/`find` than by `doctor`; if only `doctor`
    writes, every other command pays the cold cost forever and the index is never warm when it
    matters.
    """
    directory = tmp_path / "index"

    main(["-C", str(ui_book), *argv, "--index-dir", str(directory)])
    capsys.readouterr()

    assert entry_files(directory), f"`{' '.join(argv)}` loaded a graph and indexed nothing"


# ---------------------------------------------------------------------------
# (6) the graph-global checks are recomputed every run
# ---------------------------------------------------------------------------
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
    """Reachability is transitive, which is exactly what a per-file cache cannot hold.

    Cutting the `leads-to:` on `dash.md` makes `detail.md` unreachable — a fact about a file this
    run never re-read, and one a cached per-file answer would keep reporting as fine.
    """
    directory = tmp_path / "index"
    warm_index(ui_book, directory)
    write(ui_book / "docs" / "features" / "ui" / "dash.md",
          screen_md("dash", "Dash", entry=True, body=UI_DASH_UNLINKED))

    assert main(["-C", str(ui_book), "doctor", "--json", "--index-dir", str(directory)]) == 1
    report = report_of(capsys)

    unreachable = [f for f in report["findings"] if f["code"] == "unreachable-screen"]
    assert [f["ref"] for f in unreachable] == ["docs/features/ui/detail.md"]
    assert report["index"]["hits"] > 0, "detail.md was unchanged and should have been served warm"
