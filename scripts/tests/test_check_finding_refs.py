"""What `check_finding_refs.py` reports, over fabricated findings rather than the real book.

The guard's own logic — group by `(code, ref)`, exempt a linked group — is what these cases
pin. They deliberately do *not* run doctor over
`docs/features/`: that pass is the `make check-finding-refs` target's job, and a unit test
that depended on the repo's current findings would go red every time somebody wrote a bullet.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from ostler.doctor import Finding

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "check_finding_refs.py"


@pytest.fixture(scope="module")
def guard() -> Any:
    spec = importlib.util.spec_from_file_location("check_finding_refs", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _finding(code: str, ref: str, *, related: list[str] | None = None) -> Finding:
    return Finding("error", code, f"{ref}: something", path="book.md", line=1, ref=ref,
                   related=related or [])


def _report(guard: Any, findings: list[Finding], monkeypatch) -> Any:
    class _Report:
        def __init__(self) -> None:
            self.findings = findings

    monkeypatch.setattr(guard.doctor, "run", lambda graph: _Report())
    return guard.ambiguous_refs(object())


def test_two_findings_under_one_ref_are_the_failure(guard, monkeypatch) -> None:
    problems = _report(guard, [
        _finding("relation-without-subject", "book.md#node#does"),
        _finding("relation-without-subject", "book.md#node#does"),
    ], monkeypatch)
    assert len(problems) == 1
    assert "relation-without-subject" in problems[0]
    assert "book.md#node#does" in problems[0]


def test_the_index_is_what_makes_siblings_addressable(guard, monkeypatch) -> None:
    """The fix the guard exists to enforce: one address per bullet occurrence."""
    problems = _report(guard, [
        _finding("relation-without-subject", "book.md#node#does:1"),
        _finding("relation-without-subject", "book.md#node#does:2"),
    ], monkeypatch)
    assert problems == []


def test_a_different_code_under_one_ref_is_not_ambiguous(guard, monkeypatch) -> None:
    """Two codes on one bullet are two remedies with two names; the drain keys on both."""
    problems = _report(guard, [
        _finding("relation-without-subject", "book.md#node#does:1"),
        _finding("compound-normative-bullet", "book.md#node#does:1"),
    ], monkeypatch)
    assert problems == []


def test_a_group_finding_keeps_its_shared_ref(guard, monkeypatch) -> None:
    """`competing-implementations` is deliberately one finding about several nodes."""
    problems = _report(guard, [
        _finding("competing-implementations", "book.md#a", related=["book.md#b"]),
        _finding("competing-implementations", "book.md#a", related=["book.md#b"]),
    ], monkeypatch)
    assert problems == []


def test_a_duplicated_node_id_is_now_a_failure_not_an_excuse(guard, monkeypatch) -> None:
    """The exemption that used to pardon this is gone, because the case is.

    Two nodes shared an id when `model.anchor_of` minted it from the heading title alone, so no
    ref into either could name one of them and 16 findings were excused. `document_anchors`
    issues the anchor GitHub renders, so a shared ref is a defect again — including this one.
    """
    problems = _report(guard, [
        _finding("relation-without-subject", "book.md#effects#consistency:1"),
        _finding("relation-without-subject", "book.md#effects#consistency:1"),
    ], monkeypatch)
    assert len(problems) == 1
