"""A `visible` check tells a control the page never rendered apart from one it rendered hidden."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from ostler.qa.harness_host import load_harness_module

harness = load_harness_module("ostler_qa")


def _locator(*, matches: int, shown: bool) -> SimpleNamespace:
    return SimpleNamespace(count=lambda: matches, is_visible=lambda: shown,
                           page=SimpleNamespace(url="http://localhost:5173/fr/editor?draft=1"))


def test_a_control_no_element_matches_is_reported_absent_at_the_page_searched(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys.modules["ostler_qa_elements"], "ATTACH_WAIT_S", 0.0)
    verdict = harness.VERIFIERS["visible"](_locator(matches=0, shown=False), {"locator": "#create-document-slug"})
    assert verdict.passed is False
    assert verdict.actual == {"present": False, "at": "/fr/editor"}
    assert verdict.expected == {"visible": True}


def test_a_control_rendered_hidden_is_reported_not_visible() -> None:
    verdict = harness.VERIFIERS["visible"](_locator(matches=1, shown=False), {"locator": "#banner"})
    assert verdict.actual == {"visible": False}
