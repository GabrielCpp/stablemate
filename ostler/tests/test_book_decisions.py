"""`ostler book check` on a decision: the elements it names must be elements of the book."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator, cast

import pytest

from ostler.book.check import decision_faults
from ostler.book.service import Service


class Home: ...


class Checkout:
    carries = None


class Onboarding: ...


@pytest.fixture
def module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    package = tmp_path / "shop_book"
    (package / "decisions").mkdir(parents=True)
    (package / "__init__.py").write_text("")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield "shop_book"
    sys.modules.pop("shop_book", None)


def _service() -> Service[Any]:
    return cast("Service[Any]", SimpleNamespace(
        name="shop", endpoints=(), records=(), screens=(Home,), interactions=(Checkout,), journeys=(Onboarding,)))


def _findings(module: str, tmp_path: Path, element: str) -> list[str]:
    (tmp_path / "shop_book" / "decisions" / "why.md").write_text(f"story: S-1\ndate: 2026-11-14\nelements: {element}\n\nWhy.\n")
    return [f.problem for f in decision_faults(_service(), module)]


def test_a_decision_naming_a_screen_of_the_book_brings_no_finding(module, tmp_path):
    assert _findings(module, tmp_path, "Home") == []


def test_a_decision_naming_an_interaction_of_the_book_brings_no_finding(module, tmp_path):
    assert _findings(module, tmp_path, "Checkout") == []


def test_a_decision_naming_a_journey_of_the_book_brings_no_finding(module, tmp_path):
    assert _findings(module, tmp_path, "Onboarding") == []


def test_a_decision_naming_a_class_the_book_does_not_hold_brings_the_finding(module, tmp_path):
    assert _findings(module, tmp_path, "Missing") == ["element Missing resolves to no element of the book"]
