from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ostler import index, textindex
from ostler.cli import main
from ostler.model import load

from conftest import write


@pytest.fixture
def index_home(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("STABLEMATE_CONFIG", str(tmp_path / "config/config.toml"))
    monkeypatch.setenv("STABLEMATE_CACHE_DIR", str(tmp_path / "cache"))
    resolved = tmp_path / "resolved-index"
    monkeypatch.setenv(index.INDEX_DIR_ENV, str(resolved))
    return resolved


def _concept(slug: str, title: str, body: str) -> str:
    return f"---\ntype: concept\nslug: {slug}\ntitle: {title}\n---\n\n# {title}\n\n{body}\n"


def _search(repo: Path, q: str, **kw) -> list[dict]:
    with index.session(repo, enabled=False):
        return textindex.search(load(repo), q, **kw)


def _refresh(repo: Path, store: index.IndexStore | None) -> textindex.RefreshReport:
    graph = load(repo)
    ti = textindex.TextIndex.open(store, graph)
    try:
        return ti.refresh(graph)
    finally:
        ti.close()


def test_rows_for_gives_preamble_and_section_rows(repo: Path):
    page = repo / "docs/services/area/guide.md"
    write(page, "---\ntype: concept\nslug: guide\ntitle: Guide\n---\n\nLead words.\n\n"
                "# Guide\n\n## Setup\n\n### Install\n\nrun the installer\n\n- a bullet here\n")
    rows = textindex.rows_for("services", page, load(repo))
    assert [(r.anchor, r.heading) for r in rows] == [
        ("", ""), ("install", "Guide > Setup > Install")]
    assert rows[0].body == "Lead words."
    assert "run the installer" in rows[1].body
    assert "a bullet here" in rows[1].body
    assert rows[1].node == "docs/services/area/guide"
    assert rows[1].path == "docs/services/area/guide.md"
    assert rows[1].type == "concept"
    assert rows[1].slug == "guide"
    assert rows[1].title == "Guide"


def test_title_match_outranks_body_match(repo: Path):
    write(repo / "docs/services/area/a.md", _concept("a", "Zebra crossing", "nothing relevant"))
    write(repo / "docs/services/area/b.md", _concept("b", "Other", "a zebra appears here"))
    hits = _search(repo, "zebra")
    assert [h["path"] for h in hits][:2] == [
        "docs/services/area/a.md", "docs/services/area/b.md"]
    assert hits[0]["score"] > hits[1]["score"]


def test_porter_stemming_finds_parallel(repo: Path):
    write(repo / "docs/services/area/p.md", _concept("p", "Speed", "uses parallelism widely"))
    hits = _search(repo, "parallel")
    assert any(h["path"] == "docs/services/area/p.md" for h in hits)


def test_refresh_is_incremental(repo: Path, index_home: Path):
    store = index.IndexStore(repo, directory=index_home)
    first = _refresh(repo, store)
    assert first.indexed == first.files > 0
    assert _refresh(repo, store).indexed == 0
    write(repo / "docs/services/area/rec.md", _concept("rec", "Rec", "changed text"))
    assert _refresh(repo, store).indexed == 1
    (repo / "docs/services/area/rec2.md").unlink()
    report = _refresh(repo, store)
    assert (report.indexed, report.removed) == (0, 1)
    graph = load(repo)
    ti = textindex.TextIndex.open(store, graph)
    try:
        assert not [h for h in ti.search("rec2") if h["path"].endswith("rec2.md")]
    finally:
        ti.close()


def test_second_refresh_reads_no_file(repo: Path, index_home: Path, monkeypatch):
    store = index.IndexStore(repo, directory=index_home)
    _refresh(repo, store)
    reads: list[Path] = []
    original = Path.read_bytes

    def counting(self: Path) -> bytes:
        reads.append(self)
        return original(self)

    graph = load(repo)
    ti = textindex.TextIndex.open(store, graph)
    try:
        monkeypatch.setattr(Path, "read_bytes", counting)
        assert ti.refresh(graph).indexed == 0
    finally:
        ti.close()
    assert reads == []


def test_touch_without_change_reindexes_nothing(repo: Path, index_home: Path):
    store = index.IndexStore(repo, directory=index_home)
    _refresh(repo, store)
    page = repo / "docs/services/area/rec.md"
    page.write_bytes(page.read_bytes())
    os.utime(page, ns=(1, 1))
    assert _refresh(repo, store).indexed == 0


def test_epoch_change_drops_rows(repo: Path, index_home: Path):
    store = index.IndexStore(repo, directory=index_home)
    first = _refresh(repo, store)
    assert _refresh(repo, store).indexed == 0
    store._epoch = "another-epoch"
    assert _refresh(repo, store).indexed == first.files


def test_type_and_root_filters(repo: Path):
    write(repo / "docs/services/area/c.md", _concept("c", "Gizmo", "gizmo concept"))
    write(repo / "docs/services/area/f.md",
          "---\ntype: flow\nslug: f\ntitle: Gizmo flow\n---\n\n# Gizmo flow\n\ngizmo steps\n")
    both = {h["type"] for h in _search(repo, "gizmo")}
    assert {"concept", "flow"} <= both
    assert {h["type"] for h in _search(repo, "gizmo", etype="flow")} == {"flow"}
    assert _search(repo, "gizmo", root="epics") == []
    assert {h["root"] for h in _search(repo, "gizmo", root="services")} == {"services"}


def test_disabled_index_searches_without_a_file(repo: Path, index_home: Path):
    with index.session(repo, directory=index_home, enabled=False):
        hits = textindex.search(load(repo), "thing works")
    assert hits
    assert not (index_home / "textindex").exists()


def test_enabled_index_writes_one_file(repo: Path, index_home: Path):
    with index.session(repo, directory=index_home):
        textindex.search(load(repo), "thing works")
    assert len(list((index_home / "textindex").glob("*.sqlite"))) == 1


def test_cli_search_json(repo: Path, index_home: Path, capsys):
    assert main(["-C", str(repo), "search", "thing works", "--json"]) == 0
    hits = json.loads(capsys.readouterr().out)
    assert hits
    assert set(hits[0]) == {
        "root", "type", "node", "path", "anchor", "heading", "title", "score", "snippet"}


def test_cli_search_human(repo: Path, index_home: Path, capsys):
    assert main(["-C", str(repo), "search", "thing works"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].split()[1].startswith("epics/")
    assert out[1].startswith("        ")


def test_cli_index_build_json(repo: Path, index_home: Path, capsys):
    assert main(["-C", str(repo), "index", "build", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert set(report) == {"files", "sections", "indexed", "removed", "dir"}
    assert report["indexed"] == report["files"] > 0


def test_cli_match_rejects_bad_syntax(repo: Path, index_home: Path, capsys):
    assert main(["-C", str(repo), "search", '"unterminated', "--match"]) == 2
    assert capsys.readouterr().out.startswith("error:")
