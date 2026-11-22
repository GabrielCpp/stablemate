"""A book of a system outside the repository: it declares the documentation it is written from, and no command asks it for code."""

from __future__ import annotations

import dataclasses
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterator

import pytest

from book_fakes import book_command, shelf_book
from book_todo import FIXTURE, module, run_book
from ostler.book import App, Documentation, Service
from ostler.book.errors import BookError

SITE = "https://vendor.example.com/docs"
NO_CODE = "vendor describes an outside system: no code to compare"


def _vendor() -> Service[Any]:
    book = shelf_book()
    book.name = "vendor"
    book.documentation = Documentation(sites=(SITE,))
    return book


@pytest.mark.parametrize("verb", ["stale", "affected", "missing"])
def test_a_command_that_compares_code_says_there_is_none_and_exits_0(monkeypatch, tmp_path, capsys, verb):
    code, out = book_command(monkeypatch, tmp_path, _vendor(), capsys, verb, "services.shelf", "--app", str(tmp_path))
    assert (code, out.strip()) == (0, NO_CODE)


def test_verified_stamps_nothing_and_exits_0(monkeypatch, tmp_path, capsys):
    code, out = book_command(monkeypatch, tmp_path, _vendor(), capsys, "verified", "services.shelf", "--app", str(tmp_path))
    assert (code, out.strip()) == (0, "not stamped: vendor describes an outside system")
    assert not (tmp_path / "VERIFIED").exists()


def test_a_service_with_an_app_and_a_documentation_is_refused():
    with pytest.raises(BookError, match="vendor.*both"):
        dataclasses.replace(_vendor(), app=App(roots=(".",), verified="VERIFIED"))


def test_a_service_given_both_after_it_is_built_is_refused_when_loaded(monkeypatch):
    from ostler.book import cli

    book = _vendor()
    book.app = App(roots=(".",), verified="VERIFIED")
    monkeypatch.setattr(cli.importlib, "import_module", lambda name: type("Module", (), {"service": book}))
    monkeypatch.setattr(cli, "book_root", lambda cwd: str(FIXTURE))
    monkeypatch.setattr(cli.os.path, "isdir", lambda path: True)
    with pytest.raises(BookError, match="vendor.*both"):
        cli.load("services.vendor")


@pytest.mark.parametrize("sites", [(), ("vendor.example.com/docs",), ("ftp://vendor.example.com",), ("https://ok.example.com", "")])
def test_a_documentation_with_no_site_or_a_site_that_is_no_web_address_is_refused(sites):
    with pytest.raises(BookError):
        Documentation(sites=sites)


@pytest.fixture
def outside_book(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    shutil.copytree(FIXTURE, root, ignore=shutil.ignore_patterns("__pycache__"))
    service = root / "services" / "digest" / "service.py"
    service.write_text(service.read_text().replace("import App, ", "import Documentation, ").replace(
        'app=App(roots=("digest",), verified="VERIFIED", ignore=()),', f'documentation=Documentation(sites=("{SITE}",)),'))
    endpoints = root / "services" / "digest" / "endpoints.py"
    endpoints.write_text(endpoints.read_text().replace('"digest/app.py::', f'"{SITE}/digest#'))
    return root


@pytest.fixture
def digest_app(todo_app) -> Iterator:
    server = module("digest.app").DigestServer(todo_app.url).start()
    yield server
    server.stop()


def _book(root: Path, *arguments: str, port: int = 1, digest: int | None = None) -> subprocess.CompletedProcess[str]:
    return run_book(list(arguments), port, cwd=root, digest=digest)


def test_index_search_explain_and_check_read_a_book_of_an_outside_system(outside_book):
    done = _book(outside_book, "index", "services.digest")
    assert done.returncode == 0, done.stdout + done.stderr
    done = _book(outside_book, "search", "digest", "--service", "services.digest")
    assert done.returncode == 0 and "ReadDigest" in done.stdout, done.stdout + done.stderr
    done = _book(outside_book, "explain", "services.digest", "ReadDigest")
    assert done.returncode == 0 and "GET /digest" in done.stdout, done.stdout + done.stderr
    done = _book(outside_book, "check", "services.digest")
    assert done.returncode == 0, done.stdout + done.stderr


def test_run_plays_a_book_of_an_outside_system(outside_book, tmp_path, todo_app, digest_app):
    done = _book(outside_book, "run", "services.digest", "--no-stack", "--out", str(tmp_path / "out"), port=todo_app.port, digest=digest_app.port)
    assert done.returncode == 0, done.stdout + done.stderr
