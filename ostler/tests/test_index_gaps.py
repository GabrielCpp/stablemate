"""The gap classes — every way a warm index can be wrong, and the report that must not change."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from ostler import index, markdown, model
from ostler.cli import main

from conftest import (entry_files, ostler_process, report_of, screen_md,
                      warm_index, write)

def doctor_report(book: Path, *argv: str) -> dict:
    """One `doctor --json`, in a process of its own."""
    done = ostler_process(book, "doctor", "--json", *argv)
    assert done.returncode in (0, 1), done.stderr or done.stdout
    return json.loads(done.stdout)


def findings_of(report: dict) -> list[tuple]:
    """The report's findings, comparable — severity, code, ref and path."""
    return sorted((f["severity"], f["code"], f.get("ref", ""), f.get("path", ""))
                  for f in report["findings"])


def assert_agree(cached: dict, uncached: dict) -> None:
    assert findings_of(cached) == findings_of(uncached)
    assert (cached["errors"], cached["warnings"]) == (uncached["errors"], uncached["warnings"])


@pytest.fixture
def warm(ui_book: Path, tmp_path: Path, index_home: Path) -> Path:
    """A populated index directory for `ui_book`, written by a process that has since exited."""
    directory = tmp_path / "index"
    done = ostler_process(ui_book, "doctor", "--json", "--index-dir", str(directory))
    assert done.returncode in (0, 1), done.stderr or done.stdout
    return directory


def test_a_deleted_file_still_dangles_every_link_into_it(ui_book: Path, warm: Path):
    (ui_book / "docs" / "features" / "area" / "rec.md").unlink()

    cached = doctor_report(ui_book, "--index-dir", str(warm))
    uncached = doctor_report(ui_book, "--no-index")

    dangling = [f for f in cached["findings"] if f["code"] == "dangling-link"]
    assert {f["ref"] for f in dangling} == {
        "docs/features/ui/dash.md:12:../area/rec.md",
        "docs/features/ui/dash.md:12:../area/rec.md#rec"}
    assert_agree(cached, uncached)
    assert cached["index"]["hits"] > 0, "the files that did not change are still served warm"


def test_a_renamed_file_is_not_served_under_its_old_path(ui_book: Path, warm: Path):
    """Same bytes, new path: a key on content alone would answer for both."""
    area = ui_book / "docs" / "features" / "area"
    shutil.move(area / "rec.md", area / "moved.md")

    cached = doctor_report(ui_book, "--index-dir", str(warm))
    uncached = doctor_report(ui_book, "--no-index")

    assert {f["ref"] for f in cached["findings"] if f["code"] == "dangling-link"} == {
        "docs/features/ui/dash.md:12:../area/rec.md",
        "docs/features/ui/dash.md:12:../area/rec.md#rec"}
    assert_agree(cached, uncached)
    assert cached["index"]["hits"] > 0


def test_an_edited_config_file_abandons_every_entry(ui_book: Path, tmp_path: Path,
                                                    index_home: Path):
    directory = tmp_path / "index"
    write(ui_book / "ostler.yml", "organization:\n  name: acme\n")
    warm_index(ui_book, directory)

    write(ui_book / "ostler.yml", "organization:\n  name: globex\n")

    cached = doctor_report(ui_book, "--index-dir", str(directory))
    uncached = doctor_report(ui_book, "--no-index")

    assert cached["org"] == "globex"
    assert_agree(cached, uncached)
    assert cached["index"]["hits"] == 0 and cached["index"]["misses"] > 0


def test_a_tool_version_bump_abandons_every_entry(ui_book: Path, warm: Path,
                                                  monkeypatch: pytest.MonkeyPatch, capsys):
    """The one global input with no file behind it — moved at the seam the store documents."""
    real = index.epoch_inputs
    monkeypatch.setattr(index, "epoch_inputs",
                        lambda root: {**real(root), "version": "99.0.0"})

    main(["-C", str(ui_book), "doctor", "--json", "--index-dir", str(warm)])
    cached = report_of(capsys)
    uncached = doctor_report(ui_book, "--no-index")

    assert_agree(cached, uncached)
    assert cached["index"]["hits"] == 0 and cached["index"]["misses"] > 0


def test_verify_index_agrees_against_a_populated_index(ui_book: Path, warm: Path, capsys):
    code = main(["-C", str(ui_book), "doctor", "--verify-index", "--index-dir", str(warm)])
    printed = capsys.readouterr().out

    assert code == 0 and "agree" in printed
    assert entry_files(warm), "verify ran against an index that has nothing in it"


def test_verify_index_agrees_against_an_empty_index(ui_book: Path, tmp_path: Path,
                                                    index_home: Path, capsys):
    """The cold state — and the indexed half has to leave the index populated behind it."""
    directory = tmp_path / "index"

    code = main(["-C", str(ui_book), "doctor", "--verify-index", "--index-dir", str(directory)])
    printed = capsys.readouterr().out

    assert code == 0 and "agree" in printed
    assert entry_files(directory), "the indexed half of verify never wrote an entry"


def test_verify_index_catches_a_store_that_round_trips_a_document_wrongly(
    ui_book: Path, warm: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    """The mode's whole purpose, and for the document products it was inert until it wasn't."""
    original = model._doc_from_products

    def truncating(payload):
        doc = original(payload)
        return markdown.MarkdownDoc(frontmatter=doc.frontmatter,
                                    raw_frontmatter=doc.raw_frontmatter,
                                    body="", _sections=[])

    monkeypatch.setattr(model, "_doc_from_products", truncating)

    code = main(["-C", str(ui_book), "doctor", "--verify-index", "--index-dir", str(warm)])
    printed = capsys.readouterr().out

    assert code == 1, "verify-index passed while the store was handing back damaged documents"
    assert "disagree" in printed


def test_verify_index_agrees_against_a_partially_stale_index(ui_book: Path, warm: Path, capsys):
    """One file edited, the rest warm — the state a working tree is in nearly all the time."""
    before = len(entry_files(warm))
    write(ui_book / "docs" / "features" / "ui" / "detail.md",
          screen_md("detail", "Detail", body="\nA line of prose the warm entry has never seen.\n"))

    code = main(["-C", str(ui_book), "doctor", "--verify-index", "--index-dir", str(warm)])
    printed = capsys.readouterr().out

    assert code == 0 and "agree" in printed
    assert len(entry_files(warm)) > before, "the edited file was never indexed under its new sha"
