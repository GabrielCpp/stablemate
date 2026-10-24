"""The import walk reaches every production file from an entry point, and no test file."""
from __future__ import annotations

from pathlib import Path

from workhorse_workflows.okf_book.shared.imports import reached_files

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
