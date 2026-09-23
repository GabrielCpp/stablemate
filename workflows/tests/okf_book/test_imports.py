"""The import walk reaches every production file from an entry point, and no test file."""
from __future__ import annotations

from pathlib import Path

from okf_book.support import APPS

from workhorse_workflows.okf_book.imports import reached_files

TALLY = APPS / "tally-cli"
GLOBEX = APPS / "globex"


def test_the_python_walk_follows_from_imports_of_modules_and_their_packages() -> None:
    assert set(reached_files(TALLY, ["tally/__main__.py"])) == {
        "tally/__main__.py",
        "tally/__init__.py",
        "tally/cli.py",
        "tally/ledger.py",
        "tally/report.py",
    }


def test_a_go_file_reaches_its_whole_package_and_skips_its_tests() -> None:
    assert set(reached_files(GLOBEX, ["app/api-service/main.go"])) == {
        "app/api-service/main.go",
        "app/api-service/service.go",
        "app/api-service/store.go",
    }


def test_a_react_native_app_reaches_its_screens_and_its_api_client() -> None:
    found = set(reached_files(GLOBEX, ["app/mobile-app/App.tsx"]))
    assert "app/mobile-app/src/api/client.ts" in found
    assert any(path.startswith("app/mobile-app/src/screens/") for path in found)
    assert all(path.startswith("app/mobile-app/") for path in found)


def test_a_page_reaches_the_scripts_and_styles_it_loads() -> None:
    found = set(reached_files(GLOBEX, ["app/web-app/static/index.html"]))
    assert {"app/web-app/static/app.js", "app/web-app/static/styles.css"} <= found


def test_a_relative_import_resolves_against_the_importing_package(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    _ = (pkg / "__init__.py").write_text("", encoding="utf-8")
    _ = (pkg / "main.py").write_text("from . import helper\nfrom .deep import thing\n", encoding="utf-8")
    _ = (pkg / "helper.py").write_text("import json\n", encoding="utf-8")
    _ = (pkg / "deep.py").write_text("thing = 1\n", encoding="utf-8")
    _ = (pkg / "test_main.py").write_text("", encoding="utf-8")
    assert set(reached_files(tmp_path, ["pkg/main.py"])) == {"pkg/main.py", "pkg/helper.py", "pkg/deep.py"}


def test_a_start_that_is_a_test_file_or_outside_the_root_reaches_nothing(tmp_path: Path) -> None:
    _ = (tmp_path / "thing_test.go").write_text("package main\n", encoding="utf-8")
    assert reached_files(tmp_path, ["thing_test.go", "../elsewhere.py", "missing.py"]) == ()
