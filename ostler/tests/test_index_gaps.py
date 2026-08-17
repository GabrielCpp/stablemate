"""The gap classes — every way a warm index can be wrong, and the report that must not change.

A cache is only worth having if a stale answer is impossible, so each way the world moves between
two runs gets a test of its own, and each asks the same question: *does the run against the warm
index produce exactly the report the cold run produces?*

The five gap classes, one test each:

* a **deleted** file — its entry is still on disk, and the links into it must still dangle;
* a **renamed** file — the content is unchanged, so a content-only key would serve the old answer
  under the new path (and keep the old path alive);
* an edited **waiver** file — a global input: every entry in the index is now suspect;
* an edited **config** file — the same, by a different door;
* a **tool version** bump — the global input with no on-disk home, moved at
  `index.epoch_inputs`, which is the seam the store documents for exactly this.

For the first two the index must still be *used* (a file that did not change is still served warm);
for the last three it must be wholly abandoned — hits zero, misses non-zero — because what moved
was an input to every entry.

`doctor --verify-index` is the same contract as one command CI can run, and it is asserted here
against a populated, an empty and a partially stale index. It passes trivially today; what these
add is that it passes *while the index is actually being used*.

Cached and uncached reports are collected in separate processes, so nothing in-process can carry
an answer between them and make a disagreement invisible.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from ostler import index, markdown, model
from ostler.cli import main

from conftest import (UI_DASH_UNLINKED, entry_files, ostler_process, report_of, screen_md,
                      warm_index, write)

WAIVED = {"code": "unreachable-screen", "ref": "docs/features/ui/detail.md",
          "reason": "known: the detail screen is entered from an emailed link",
          "backlog": "fix-detail-entry"}


def doctor_report(book: Path, *argv: str) -> dict:
    """One `doctor --json`, in a process of its own."""
    done = ostler_process(book, "doctor", "--json", *argv)
    assert done.returncode in (0, 1), done.stderr or done.stdout
    return json.loads(done.stdout)


def findings_of(report: dict) -> list[tuple]:
    """The report's findings, comparable — severity, code, ref, path and waived state."""
    return sorted((f["severity"], f["code"], f.get("ref", ""), f.get("path", ""),
                   bool(f.get("waived"))) for f in report["findings"])


def assert_agree(cached: dict, uncached: dict) -> None:
    assert findings_of(cached) == findings_of(uncached)
    assert (cached["errors"], cached["warnings"]) == (uncached["errors"], uncached["warnings"])


@pytest.fixture
def warm(ui_book: Path, tmp_path: Path, index_home: Path) -> Path:
    """A populated index directory for `ui_book`, written by a process that has since exited.

    Deliberately does not assert that anything was written: every test here goes on to assert
    what the index was used *for*, and a red belongs in the test rather than in a fixture.
    """
    directory = tmp_path / "index"
    done = ostler_process(ui_book, "doctor", "--json", "--index-dir", str(directory))
    assert done.returncode in (0, 1), done.stderr or done.stdout
    return directory


# ---------------------------------------------------------------------------
# (5) the gap classes
# ---------------------------------------------------------------------------
def test_a_deleted_file_still_dangles_every_link_into_it(ui_book: Path, warm: Path):
    (ui_book / "docs" / "features" / "area" / "rec.md").unlink()

    cached = doctor_report(ui_book, "--index-dir", str(warm))
    uncached = doctor_report(ui_book, "--no-index")

    dangling = [f for f in cached["findings"] if f["code"] == "dangling-link"]
    assert {f["ref"] for f in dangling} == {"../area/rec.md", "../area/rec.md#rec"}
    assert_agree(cached, uncached)
    assert cached["index"]["hits"] > 0, "the files that did not change are still served warm"


def test_a_renamed_file_is_not_served_under_its_old_path(ui_book: Path, warm: Path):
    """Same bytes, new path: a key on content alone would answer for both."""
    area = ui_book / "docs" / "features" / "area"
    shutil.move(area / "rec.md", area / "moved.md")

    cached = doctor_report(ui_book, "--index-dir", str(warm))
    uncached = doctor_report(ui_book, "--no-index")

    assert {f["ref"] for f in cached["findings"] if f["code"] == "dangling-link"} == {
        "../area/rec.md", "../area/rec.md#rec"}
    assert_agree(cached, uncached)
    assert cached["index"]["hits"] > 0


def test_an_edited_waiver_file_abandons_every_entry(ui_book: Path, tmp_path: Path,
                                                    index_home: Path):
    """A waiver changes the severity of a finding about a file whose bytes never moved."""
    directory = tmp_path / "index"
    write(ui_book / "docs" / "features" / "ui" / "dash.md",
          screen_md("dash", "Dash", entry=True, body=UI_DASH_UNLINKED))
    warm_index(ui_book, directory)

    write(ui_book / "docs" / "doctor-waivers.json",
          json.dumps({"waivers": [WAIVED]}, indent=2) + "\n")

    cached = doctor_report(ui_book, "--index-dir", str(directory))
    uncached = doctor_report(ui_book, "--no-index")

    waived = [f for f in cached["findings"] if f["code"] == "unreachable-screen"]
    assert waived and all(f["severity"] == "warn" and f["waived"] for f in waived)
    assert_agree(cached, uncached)
    assert cached["index"]["hits"] == 0 and cached["index"]["misses"] > 0


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
    """The one global input with no file behind it — moved at the seam the store documents.

    In-process, because a monkeypatch does not reach a subprocess; the uncached side stays in a
    process of its own, so the comparison is still against a genuinely cold run.
    """
    real = index.epoch_inputs
    monkeypatch.setattr(index, "epoch_inputs",
                        lambda root: {**real(root), "version": "99.0.0"})

    main(["-C", str(ui_book), "doctor", "--json", "--index-dir", str(warm)])
    cached = report_of(capsys)
    uncached = doctor_report(ui_book, "--no-index")

    assert_agree(cached, uncached)
    assert cached["index"]["hits"] == 0 and cached["index"]["misses"] > 0


# ---------------------------------------------------------------------------
# (4) verify mode, over the three states an index can be in
# ---------------------------------------------------------------------------
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
    """The mode's whole purpose, and for the document products it was inert until it wasn't.

    `--verify-index` runs the indexed and the uncached path in one process, so the two halves
    only disagree if the uncached one recomputes what the indexed one read. The document memo
    used to serve a parsed document across both stores — on the argument that these products
    are a pure function of the bytes and no store can disagree about them, which is precisely
    the assumption this mode exists to test. A corrupt entry was therefore never read by the
    half meant to catch it, and the gate reported "agree" and exited 0.

    Corrupting the read side of the round trip is the smallest faithful stand-in for a store
    that damages an entry: only a *hit* goes through `_doc_from_products`, so the uncached half
    is untouched and the disagreement is exactly the one a real corruption would produce.
    """
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
