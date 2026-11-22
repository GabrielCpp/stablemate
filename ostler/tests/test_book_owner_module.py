"""A book's module name is the nearest package that holds a service.py, at any depth."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from conftest import write
from ostler.book.asked import Asked, book_module
from ostler.book.owners import book_of


@pytest.fixture
def loaded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    for folder in ("services", "services/acme", "services/acme/api", "services/acme/groom", "services/acme/groom/http"):
        write(tmp_path / folder / "__init__.py", "")
    for folder in ("services/acme/api", "services/acme/groom/http"):
        write(tmp_path / folder / "service.py", "")
        write(tmp_path / folder / "endpoints.py", "class Call:\n    pass\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    for name in [n for n in sys.modules if n == "services" or n.startswith("services.")]:
        monkeypatch.delitem(sys.modules, name)
    yield
    for name in [n for n in sys.modules if n == "services" or n.startswith("services.")]:
        del sys.modules[name]


def test_the_book_module_of_a_module_is_its_nearest_package_with_a_service(loaded):
    importlib.import_module("services.acme.api.endpoints")
    importlib.import_module("services.acme.groom.http.endpoints")
    assert book_module("services.acme.api.endpoints") == "services.acme.api"
    assert book_module("services.acme.groom.http.endpoints") == "services.acme.groom.http"


def test_the_owner_and_the_asker_name_the_same_book(loaded):
    for module, expected in (("services.acme.api.endpoints", "services.acme.api"), ("services.acme.groom.http.endpoints", "services.acme.groom.http")):
        call = importlib.import_module(module).Call
        assert book_of(call()) == expected
        assert Asked(call).book == expected


def test_a_module_with_no_loaded_package_falls_back_to_its_first_two_parts():
    assert book_module("services.other.thing.deep") == "services.other"
