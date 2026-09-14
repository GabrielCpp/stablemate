"""`ostler.stamp` — writing per-citation content-hash digests onto `code:` bullets."""
from __future__ import annotations

import hashlib
from pathlib import Path

from ostler import source_snapshots, stamp
from ostler.cli import main

SERVICE = "def charge(amount):\n    return amount\n"


def test_digest_file_matches_the_snapshot_recipe():
    """Decode-then-hash, truncated to 12 hex chars — must agree with the catalog's own recipe."""
    assert stamp.digest_file(SERVICE) == hashlib.sha256(SERVICE.encode()).hexdigest()[:12]


def test_restamp_stamps_a_single_target():
    out = stamp.restamp_leading_code_spans("`api/a.py`", lambda _: "3f9a1c07b2e4")
    assert out == "`api/a.py` @3f9a1c07b2e4"


def test_restamp_stamps_every_target_in_a_multi_target_bullet():
    digests = {"api/a.py": "3f9a1c07b2e4", "api/b.py": "abcdef012345"}
    out = stamp.restamp_leading_code_spans(
        "`api/a.py`, `api/b.py`", lambda target: digests[target],
    )
    assert out == "`api/a.py` @3f9a1c07b2e4, `api/b.py` @abcdef012345"


def test_restamp_leaves_a_target_unstamped_when_digest_for_returns_none():
    out = stamp.restamp_leading_code_spans("`api/a.py`", lambda _: None)
    assert out == "`api/a.py`"


def test_restamp_overwrites_an_existing_digest():
    out = stamp.restamp_leading_code_spans(
        "`api/a.py` @000000000000", lambda _: "3f9a1c07b2e4",
    )
    assert out == "`api/a.py` @3f9a1c07b2e4"


def test_restamp_leaves_a_trailing_gloss_untouched():
    out = stamp.restamp_leading_code_spans(
        "`api/a.py` (inline JSX, not a named export)", lambda _: "3f9a1c07b2e4",
    )
    assert out == "`api/a.py` @3f9a1c07b2e4 (inline JSX, not a named export)"


def test_restamp_leaves_a_value_with_no_leading_span_unchanged():
    assert stamp.restamp_leading_code_spans(
        "see `api/a.py` for the handler", lambda _: "3f9a1c07b2e4",
    ) == "see `api/a.py` for the handler"


def _book(root: Path, code: str) -> Path:
    feature = root / "docs/features/billing/charge.md"
    feature.parent.mkdir(parents=True, exist_ok=True)
    feature.write_text(
        "---\ntype: concept\nslug: charge\ntitle: Charge\n---\n"
        f"# Charge\n\n- code: {code}\n",
        encoding="utf-8",
    )
    return feature


def _service(root: Path, text: str = SERVICE) -> Path:
    target = root / "src/service.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def test_stamp_page_writes_a_digest_onto_the_cited_file(tmp_path: Path):
    feature = _book(tmp_path, "`src/service.py::charge`")
    _service(tmp_path)
    result = stamp.stamp_page(tmp_path, tmp_path, "docs/features/billing/charge.md")
    expected = stamp.digest_file(SERVICE)
    assert result.stamped == 1
    assert result.unresolved == []
    assert result.changed is True
    assert f"`src/service.py::charge` @{expected}" in feature.read_text(encoding="utf-8")


def test_stamp_page_reports_a_missing_file_as_unresolved(tmp_path: Path):
    _book(tmp_path, "`src/missing.py::charge`")
    result = stamp.stamp_page(tmp_path, tmp_path, "docs/features/billing/charge.md")
    assert result.stamped == 0
    assert result.unresolved == ["src/missing.py::charge"]
    assert result.changed is False


def test_stamp_page_leaves_a_ref_to_a_different_repository_unresolved(tmp_path: Path):
    (tmp_path / "repository.txt").write_text("acme\n", encoding="utf-8")
    _book(tmp_path, "`repo://globex/src/service.py::charge`")
    _service(tmp_path)
    result = stamp.stamp_page(tmp_path, tmp_path, "docs/features/billing/charge.md")
    assert result.stamped == 0
    assert result.unresolved == ["repo://globex/src/service.py::charge"]
    assert result.changed is False


def test_stamp_page_resolves_a_ref_qualified_with_the_books_own_repository(tmp_path: Path):
    (tmp_path / "repository.txt").write_text("acme\n", encoding="utf-8")
    feature = _book(tmp_path, "`repo://acme/src/service.py::charge`")
    _service(tmp_path)
    result = stamp.stamp_page(tmp_path, tmp_path, "docs/features/billing/charge.md")
    expected = stamp.digest_file(SERVICE)
    assert result.stamped == 1
    assert f"@{expected}" in feature.read_text(encoding="utf-8")


def test_restamping_an_unchanged_file_is_a_noop_write(tmp_path: Path):
    feature = _book(tmp_path, "`src/service.py::charge`")
    _service(tmp_path)
    stamp.stamp_page(tmp_path, tmp_path, "docs/features/billing/charge.md")
    before = feature.read_text(encoding="utf-8")
    result = stamp.stamp_page(tmp_path, tmp_path, "docs/features/billing/charge.md")
    assert result.changed is False
    assert feature.read_text(encoding="utf-8") == before


def _two_node_book(root: Path, code: str) -> Path:
    feature = root / "docs/features/billing/charge.md"
    feature.parent.mkdir(parents=True, exist_ok=True)
    feature.write_text(
        "---\ntype: concept\nslug: charge\ntitle: Charge\n---\n"
        "# Charge\n\n"
        "## Alpha\n\n"
        f"- code: {code}\n\n"
        "## Beta\n\n"
        f"- code: {code}\n",
        encoding="utf-8",
    )
    return feature


def test_stamp_page_scoped_to_a_line_range_leaves_the_other_nodes_bullet_stale(tmp_path: Path):
    # Two nodes on one page cite the same changed file. Stamping only "Alpha"'s line range
    # must not touch "Beta"'s bullet — the whole point of node-scoped stamping.
    feature = _two_node_book(tmp_path, "`src/service.py::charge`")
    _service(tmp_path)
    lines = feature.read_text(encoding="utf-8").splitlines()
    alpha_line = next(i for i, line in enumerate(lines, start=1) if line == "## Alpha")
    beta_line = next(i for i, line in enumerate(lines, start=1) if line == "## Beta")

    result = stamp.stamp_page(
        tmp_path, tmp_path, "docs/features/billing/charge.md",
        line_ranges=[(alpha_line, beta_line)],
    )

    expected = stamp.digest_file(SERVICE)
    assert result.stamped == 1
    assert result.changed is True
    after = feature.read_text(encoding="utf-8").splitlines()
    assert f"- code: `src/service.py::charge` @{expected}" == after[alpha_line + 1]
    assert "- code: `src/service.py::charge`" == after[beta_line + 1]


def test_stamp_page_reports_a_bullet_whose_line_count_changed_as_unresolved(
    tmp_path: Path, monkeypatch,
):
    feature = _book(tmp_path, "`src/service.py::charge`")
    _service(tmp_path)
    # `restamp_leading_code_spans` never adds or removes a line on its own; force the
    # mismatch branch by handing it a `digest_for` that turns one line into two.
    original = stamp.restamp_leading_code_spans
    monkeypatch.setattr(
        stamp, "restamp_leading_code_spans",
        lambda value, digest_for: original(value, digest_for) + "\nextra",
    )
    result = stamp.stamp_page(tmp_path, tmp_path, "docs/features/billing/charge.md")
    assert result.unresolved == ["- code: `src/service.py::charge`"]
    assert result.changed is False
    assert "@" not in feature.read_text(encoding="utf-8")


def test_stamp_page_from_catalog_uses_the_catalogs_digest_not_the_live_files(tmp_path: Path):
    # The file on disk has drifted since the catalog was last built. Migration must stamp
    # the *catalog's* stale digest, not re-read the file — so `stale-citation` fires right
    # after migration, instead of the drift silently looking fresh.
    root = tmp_path
    _book(root, "`src/service.py::charge`")
    _service(root, "def charge(amount):\n    return amount * 2\n")
    stale_digest = hashlib.sha256(SERVICE.encode()).hexdigest()
    catalog = source_snapshots.SourceCatalog(
        repositories=(
            source_snapshots.RepositorySnapshot(
                id=source_snapshots.SELF_REPOSITORY, base="", head="WORKTREE",
                files=(
                    source_snapshots.SourceFile(path="src/service.py", content_sha256=stale_digest),
                ),
            ),
        ),
    )
    result = stamp.stamp_page_from_catalog(root, "docs/features/billing/charge.md", catalog)
    assert result.stamped == 1
    assert result.unresolved == []
    text = (root / "docs/features/billing/charge.md").read_text(encoding="utf-8")
    assert f"`src/service.py::charge` @{stale_digest[:12]}" in text
    assert stale_digest[:12] != stamp.digest_file(
        (root / "src/service.py").read_text(encoding="utf-8")
    )


def test_stamp_page_from_catalog_leaves_a_file_with_no_catalog_row_unstamped(tmp_path: Path):
    _book(tmp_path, "`src/missing_from_catalog.py::charge`")
    catalog = source_snapshots.SourceCatalog(
        repositories=(
            source_snapshots.RepositorySnapshot(
                id=source_snapshots.SELF_REPOSITORY, base="", head="WORKTREE", files=(),
            ),
        ),
    )
    result = stamp.stamp_page_from_catalog(tmp_path, "docs/features/billing/charge.md", catalog)
    assert result.stamped == 0
    assert result.unresolved == ["src/missing_from_catalog.py::charge"]
    assert result.changed is False


def test_cli_stamp_from_catalog_migrates_the_whole_book_and_deletes_the_catalog(
    tmp_path: Path,
):
    feature = tmp_path / "docs/features/billing/charge.md"
    feature.parent.mkdir(parents=True, exist_ok=True)
    feature.write_text(
        "---\ntype: concept\nslug: charge\ntitle: Charge\n---\n"
        "# Charge\n\n"
        "- code: `src/service.py::charge`\n"
        "- code: `src/uncatalogued.py::other`\n",
        encoding="utf-8",
    )
    _service(tmp_path)
    (tmp_path / "src/uncatalogued.py").write_text("def other():\n    pass\n", encoding="utf-8")

    stale_digest = hashlib.sha256(SERVICE.encode()).hexdigest()
    catalog = source_snapshots.SourceCatalog(
        repositories=(
            source_snapshots.RepositorySnapshot(
                id=source_snapshots.SELF_REPOSITORY, base="", head="WORKTREE",
                files=(
                    source_snapshots.SourceFile(path="src/service.py",
                                                 content_sha256=stale_digest),
                ),
            ),
        ),
    )
    catalog_path = source_snapshots.catalog_path(tmp_path)
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(catalog.model_dump_json(), encoding="utf-8")

    assert main(["-C", str(tmp_path), "stamp", "--from-catalog"]) == 0

    text = feature.read_text(encoding="utf-8")
    assert f"`src/service.py::charge` @{stale_digest[:12]}" in text
    assert "`src/uncatalogued.py::other`\n" in text
    assert not catalog_path.exists()
