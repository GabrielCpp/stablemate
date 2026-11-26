"""`ostler book check` on a decision: the elements it names must be elements of the book."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from ostler.book import Documentation, decisions
from ostler.book.check import decision_faults, question_faults
from ostler.book.search import cmd_explain
from ostler.book.service import Service


class Home: ...


class Checkout:
    carries = None


class Onboarding: ...


class Cart: ...


class Landing:
    first = False
    inside = None
    shown_in = None

    @classmethod
    def describe(cls, lang: str, arrived: tuple = ()) -> str:
        return "the landing page"


class Pay: ...


def _service() -> Service[Any]:
    return cast("Service[Any]", SimpleNamespace(
        name="shop", endpoints=(), records=(), screens=(Home,), interactions=(Checkout,), journeys=(Onboarding,), documentation=None))


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


def _asked(module: str, tmp_path: Path, line: str) -> list[str]:
    (tmp_path / "shop_book" / "QUESTIONS.md").write_text(f"Open questions\n\n{line}\n")
    return [f"{f.name}: {f.problem}" for f in question_faults(_service(), module)]


def test_a_question_naming_an_element_of_the_book_brings_no_finding(module, tmp_path):
    assert _asked(module, tmp_path, "- Home: why does it greet twice?") == []


def test_a_question_naming_no_element_of_the_book_brings_the_finding(module, tmp_path):
    assert _asked(module, tmp_path, "- Missing: why?") == ["question line 3: element Missing resolves to no element of the book"]


def test_a_question_written_without_its_dash_brings_the_finding(module, tmp_path):
    assert _asked(module, tmp_path, "Home: why does it greet twice?") == ["question line 3: is no entry, write it as `- <Element>: <question>`"]


def test_explain_shows_the_open_questions_of_an_element(module, tmp_path, capsys):
    (tmp_path / "shop_book" / "QUESTIONS.md").write_text("- Landing: why does it greet twice?\n- Cart: other\n")
    service = cast("Service[Any]", SimpleNamespace(
        name="shop", endpoints=(), records=(), screens=(Landing,), interactions=(), journeys=(), language="en"))
    assert cmd_explain(service, SimpleNamespace(service=module, name="Landing")) == 0
    assert capsys.readouterr().out.endswith("\nOpen questions\n- why does it greet twice?\n")


def _vendor_findings(module: str, tmp_path: Path, pointer: str, app: Path) -> list[str]:
    _write(tmp_path, f"sources: {pointer}\n")
    service = cast("Service[Any]", SimpleNamespace(name="vendor", endpoints=(), records=(), screens=(Home,), interactions=(), journeys=(),
                                                   documentation=Documentation(sites=("https://vendor.example.com/docs",))))
    return [f.problem for f in decision_faults(service, module, str(app))]


def test_a_decision_source_under_a_declared_site_brings_no_finding(module, tmp_path):
    assert _vendor_findings(module, tmp_path, "https://vendor.example.com/docs/api#users", tmp_path) == []


def test_a_decision_source_under_another_site_is_not_there(module, tmp_path):
    assert _vendor_findings(module, tmp_path, "https://other.example.com/docs", tmp_path) == ["source https://other.example.com/docs is not there"]


SIBLING = """from types import SimpleNamespace


class Pay:
    carries = None


service = SimpleNamespace(name="shop-api", endpoints=(Pay,), records=(), screens=(), interactions=(), journeys=(), documentation=None)
"""


@pytest.fixture
def surface(module: str, tmp_path: Path) -> Iterator[str]:
    """The web surface of a book split by surface: `shop_book` holds the model and the shared decisions, and an api
    surface beside the web one declares the endpoint `Pay`."""
    book = tmp_path / "shop_book"
    for part in ("model", "web", "api"):
        (book / part).mkdir()
        (book / part / "__init__.py").write_text("")
    (book / "web" / "service.py").write_text("")
    (book / "api" / "service.py").write_text(SIBLING)
    yield f"{module}.web"
    for name in [n for n in sys.modules if n.startswith(f"{module}.")]:
        sys.modules.pop(name)


def _shared(tmp_path: Path, element: str) -> None:
    (tmp_path / "shop_book" / "decisions" / "why.md").write_text(f"story: none\ndate: 2026-11-25\nelements: {element}\n\nWhy.\n")


def test_a_surface_reads_the_decisions_of_the_book_shared_root(surface, tmp_path):
    _shared(tmp_path, "Home")
    assert [d.slug for d in decisions.load(surface)] == ["why"]


def test_a_shared_decision_naming_a_screen_leaves_it_out_of_unexplained(surface, tmp_path):
    _shared(tmp_path, "Home")
    assert decisions.unexplained(_service(), surface, "screen") == []


def test_a_shared_decision_naming_an_element_of_another_surface_brings_no_finding(surface, tmp_path):
    _shared(tmp_path, "Home, Pay")
    assert [f.problem for f in decision_faults(_service(), surface)] == []


def test_a_surface_decision_naming_an_element_of_another_surface_still_brings_the_finding(surface, tmp_path):
    (tmp_path / "shop_book" / "web" / "decisions").mkdir()
    (tmp_path / "shop_book" / "web" / "decisions" / "why.md").write_text("story: none\ndate: 2026-11-25\nelements: Pay\n\nWhy.\n")
    assert [f.problem for f in decision_faults(_service(), surface)] == ["element Pay resolves to no element of the book"]


def test_a_question_in_the_shared_root_is_read_by_each_surface(surface, tmp_path):
    (tmp_path / "shop_book" / "QUESTIONS.md").write_text("- Pay: why?\n- Missing: why?\n")
    assert [f.problem for f in question_faults(_service(), surface)] == ["element Missing resolves to no element of the book"]
