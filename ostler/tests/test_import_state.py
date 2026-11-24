"""The import path and the loaded `services` package a test leaves do not reach the next test."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import book_todo
from book_todo import FIXTURE, module


def test_the_fixture_book_loads_with_another_services_root_ahead_of_it_on_the_path(own_book, tmp_path: Path, monkeypatch):
    module("app")
    (tmp_path / "services").mkdir()
    (tmp_path / "services" / "__init__.py").write_text("")
    monkeypatch.syspath_prepend(str(tmp_path))
    surface = module("services.api.surface")
    assert Path(str(surface.__file__)).is_relative_to(FIXTURE)


def test_a_kept_block_puts_back_the_path_and_the_services_it_found(tmp_path: Path):
    path = list(sys.path)
    held = {name for name in sys.modules if name == "services" or name.startswith("services.")}
    with book_todo.import_state_kept():
        sys.path.insert(0, str(tmp_path))
        sys.modules["services.left_behind"] = ModuleType("services.left_behind")
        module("services.api.surface")
    assert sys.path == path
    assert {name for name in sys.modules if name == "services" or name.startswith("services.")} == held
