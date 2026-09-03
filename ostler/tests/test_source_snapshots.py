"""The catalog: what the book cites, and the watermark that says whether it has moved.

The central case is `test_the_graphs_own_repository_is_snapshotted`. The catalog used to skip
every unqualified `code:` ref — the majority of any book — so the one freshness question a run
could ask was `source_fingerprint`'s, which changes when *anything* under a scope changes and
can never name a node. A same-repo snapshot is what turns "something moved" into "these nodes
went stale".
"""
from __future__ import annotations

from pathlib import Path

from ostler import source_snapshots
from ostler.model import load

SERVICE = "def charge(amount):\n    return amount\n\n\ndef refund(amount):\n    return -amount\n"


def _book(root: Path, code: str) -> None:
    """A one-node book citing *code*, plus the source file that citation names."""
    feature = root / "docs/features/billing/charge.md"
    feature.parent.mkdir(parents=True, exist_ok=True)
    feature.write_text(
        "---\ntype: concept\nslug: charge\ntitle: Charge\n---\n"
        f"# Charge\n\n- code: `{code}`\n",
        encoding="utf-8",
    )


def _service(root: Path, text: str = SERVICE) -> None:
    target = root / "src/service.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def test_the_graphs_own_repository_is_snapshotted(tmp_path: Path) -> None:
    _book(tmp_path, "src/service.py::charge")
    _service(tmp_path)
    catalog = source_snapshots.build_catalog(load(tmp_path), ())
    snapshot = catalog.repository(source_snapshots.SELF_REPOSITORY)
    assert snapshot is not None
    assert [item.path for item in snapshot.files] == ["src/service.py"]
    assert snapshot.files[0].symbols == ("charge", "refund")


def test_each_cited_file_carries_a_digest_per_declaration(tmp_path: Path) -> None:
    _book(tmp_path, "src/service.py::charge")
    _service(tmp_path)
    catalog = source_snapshots.build_catalog(load(tmp_path), ())
    snapshot = catalog.repository(source_snapshots.SELF_REPOSITORY)
    assert snapshot is not None
    declared = snapshot.files[0]
    assert [item.name for item in declared.declarations] == ["charge", "refund"]
    assert declared.digest_of("charge")
    assert declared.digest_of("charge") != declared.digest_of("refund")


def test_editing_one_symbol_moves_only_that_symbols_digest(tmp_path: Path) -> None:
    """The property the whole backfill rests on: a per-file sha cannot say this."""
    _book(tmp_path, "src/service.py::charge")
    _service(tmp_path)
    before = source_snapshots.build_catalog(load(tmp_path), ())
    _service(tmp_path, SERVICE.replace("return amount", "return amount * 2"))
    after = source_snapshots.build_catalog(load(tmp_path), ())

    old = before.repository(source_snapshots.SELF_REPOSITORY)
    new = after.repository(source_snapshots.SELF_REPOSITORY)
    assert old is not None and new is not None
    assert old.files[0].content_sha256 != new.files[0].content_sha256
    assert old.files[0].digest_of("charge") != new.files[0].digest_of("charge")
    assert old.files[0].digest_of("refund") == new.files[0].digest_of("refund")


def test_a_snapshot_with_no_watermark_answers_empty_rather_than_guessing() -> None:
    """A catalog written before `declarations` existed must read as "unknown", not "gone"."""
    stored = source_snapshots.SourceFile(
        path="src/service.py", content_sha256="deadbeef", symbols=("charge",)
    )
    assert stored.digest_of("charge") == ""
    assert stored.symbols == ("charge",)


def test_a_citation_naming_a_file_that_is_gone_is_left_to_doctor(tmp_path: Path) -> None:
    """The catalog is a snapshot, not a check: a missing file is simply absent from it."""
    _book(tmp_path, "src/service.py::charge")
    catalog = source_snapshots.build_catalog(load(tmp_path), ())
    snapshot = catalog.repository(source_snapshots.SELF_REPOSITORY)
    assert snapshot is None or snapshot.files == ()


def test_the_catalog_round_trips_through_disk(tmp_path: Path) -> None:
    _book(tmp_path, "src/service.py::charge")
    _service(tmp_path)
    graph = load(tmp_path)
    written = source_snapshots.write_catalog(graph, ())
    assert written == source_snapshots.catalog_path(tmp_path)
    loaded = source_snapshots.load_catalog(tmp_path)
    assert loaded == source_snapshots.build_catalog(graph, ())


def test_advancing_one_path_leaves_every_other_row_alone(tmp_path: Path) -> None:
    """The write a run makes mid-drain, when one node has just been reconciled.

    A whole-catalog write is only honest at convergence. Here exactly one file was re-read, so
    exactly one row may move — anything wider would stamp symbols nobody looked at as current
    and erase the drift the next join exists to report.
    """
    _book(tmp_path, "src/service.py::charge")
    _service(tmp_path)
    other = tmp_path / "src/other.py"
    other.write_text("def ship():\n    return 1\n", encoding="utf-8")
    (tmp_path / "docs/features/billing/ship.md").write_text(
        "---\ntype: concept\nslug: ship\ntitle: Ship\n---\n"
        "# Ship\n\n- code: `src/other.py::ship`\n",
        encoding="utf-8",
    )
    source_snapshots.write_catalog(load(tmp_path), ())
    before = source_snapshots.load_catalog(tmp_path)
    assert before is not None
    stale = {f.path: f.digest_of(n) for f in before.repositories[0].files
             for n in ("charge", "ship")}

    _service(tmp_path, SERVICE.replace("return amount", "return amount * 2"))
    other.write_text("def ship():\n    return 2\n", encoding="utf-8")
    source_snapshots.advance_catalog(load(tmp_path), ["src/service.py"])

    after = source_snapshots.load_catalog(tmp_path)
    assert after is not None
    files = {item.path: item for item in after.repositories[0].files}
    assert files["src/service.py"].digest_of("charge") != stale["src/service.py"]
    assert files["src/other.py"].digest_of("ship") == stale["src/other.py"]


def test_advancing_against_no_catalog_writes_one(tmp_path: Path) -> None:
    """A run that closes a regrounding item before any convergence still records what it read.

    The first advance on a book with no `sources.json` must produce a catalog holding that one
    file, not fail and not silently do nothing — otherwise the very first fix in a fresh clone
    is the one whose row can never retire.
    """
    _book(tmp_path, "src/service.py::charge")
    _service(tmp_path)
    source_snapshots.advance_catalog(load(tmp_path), ["src/service.py"])

    catalog = source_snapshots.load_catalog(tmp_path)
    assert catalog is not None
    snapshot = catalog.repository(source_snapshots.SELF_REPOSITORY)
    assert snapshot is not None
    assert [item.path for item in snapshot.files] == ["src/service.py"]
    assert snapshot.files[0].digest_of("charge")
