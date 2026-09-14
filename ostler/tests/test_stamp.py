"""`ostler.stamp` — writing per-citation content-hash digests onto `code:` bullets."""
from __future__ import annotations

import hashlib
from pathlib import Path

from ostler import stamp

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
