"""`ostler book check` on a decision: the elements it names must be elements of the book."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator, cast

import pytest

from ostler.book import decisions
from ostler.book.check import decision_faults
from ostler.book.service import Service


class Home: ...


class Checkout:
    carries = None


class Onboarding: ...


class Cart: ...


class Pay: ...


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


def _write(tmp_path: Path, header: str = "") -> None:
    (tmp_path / "shop_book" / "decisions" / "why.md").write_text(f"story: S-1\ndate: 2026-11-14\nelements: Home\n{header}\nWhy.\n")


def _sourced(module: str, tmp_path: Path, pointer: str, app: Path | None) -> list[str]:
    _write(tmp_path, f"sources: {pointer}\n")
    return [f.problem for f in decision_faults(_service(), module, str(app) if app else None)]


@pytest.fixture
def app(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "app"
    root.mkdir()

    def run(*a: str) -> str:
        return subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True, text=True).stdout.strip()

    run("init", "-q")
    (root / "shop.py").write_text("x = 1\n")
    run("add", "shop.py")
    run("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "first")
    return root, run("rev-parse", "HEAD")


def test_a_decision_with_a_sources_line_parses_its_pointers(module, tmp_path):
    _write(tmp_path, "sources: abc1234, shop.py::Cart\n")
    assert decisions.load(module)[0].sources == ("abc1234", "shop.py::Cart")


def test_a_decision_without_a_sources_line_parses_no_pointer(module, tmp_path):
    _write(tmp_path)
    assert decisions.load(module)[0].sources == ()


def test_a_source_that_names_a_commit_of_the_app_passes_the_check(module, tmp_path, app):
    assert _sourced(module, tmp_path, app[1][:10], app[0]) == []


def test_a_source_that_names_a_file_in_a_commit_passes_the_check(module, tmp_path, app):
    assert _sourced(module, tmp_path, f"{app[1][:10]}:shop.py", app[0]) == []


def test_a_source_that_names_a_path_the_commit_does_not_hold_is_a_finding(module, tmp_path, app):
    pointer = f"{app[1][:10]}:other.py"
    assert _sourced(module, tmp_path, pointer, app[0]) == [f"source {pointer} is not there"]


def test_a_source_that_names_a_file_of_the_app_passes_the_check(module, tmp_path, app):
    assert _sourced(module, tmp_path, "shop.py::Cart", app[0]) == []


def test_a_source_that_names_a_file_the_app_lacks_is_a_finding(module, tmp_path, app):
    assert _sourced(module, tmp_path, "gone.py", app[0]) == ["source gone.py is not there"]


def test_a_source_that_names_a_sha_no_commit_has_is_a_finding(module, tmp_path, app):
    assert _sourced(module, tmp_path, "deadbee", app[0]) == ["source deadbee is not there"]


def test_without_an_app_no_source_is_opened(module, tmp_path):
    assert _sourced(module, tmp_path, "deadbee, gone.py", None) == []


def _listed(module: str, tmp_path: Path, capsys: pytest.CaptureFixture[str], kind: str | None = None) -> list[str]:
    _write(tmp_path)
    service = cast("Service[Any]", SimpleNamespace(
        name="shop", endpoints=(Pay,), records=(), screens=(Home, Cart), interactions=()))
    args = SimpleNamespace(service=module, story=None, element=None, unexplained=True, kind=kind)
    assert decisions.cmd_decisions(service, args) == 0
    return capsys.readouterr().out.splitlines()


def test_unexplained_lists_the_screens_no_decision_names_and_leaves_out_the_named_one(module, tmp_path, capsys):
    assert _listed(module, tmp_path, capsys, "screen") == ["Cart"]


def test_unexplained_kind_screen_leaves_out_an_unexplained_endpoint(module, tmp_path, capsys):
    listed = _listed(module, tmp_path, capsys, "screen")
    assert "Cart" in listed and "Pay" not in listed


def test_unexplained_without_a_kind_lists_every_kind_in_the_order_the_service_lists_them(module, tmp_path, capsys):
    assert _listed(module, tmp_path, capsys) == ["Pay", "Cart"]


def test_unexplained_with_a_story_is_refused_by_the_parser():
    from ostler.book.cli import main

    with pytest.raises(SystemExit) as stop:
        main(["decisions", "services.shop", "--unexplained", "--story", "S-1"])
    assert stop.value.code == 2
