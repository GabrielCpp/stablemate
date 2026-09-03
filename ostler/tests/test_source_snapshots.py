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
