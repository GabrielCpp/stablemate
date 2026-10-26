"""The compose files, Dockerfiles and runbook make targets join the production set."""
from __future__ import annotations

from pathlib import Path

from workhorse_workflows.okf_book.shared.source_repo import SourceRepo
from workhorse_workflows.okf_book.shared.stack import stack_files

RUNBOOK = "---\ntype: runbook\nslug: run\ntitle: Run\n---\n# Run\n\n- run: `make up`\n"

def _repo(tmp_path: Path, makefile: str, runbook: str = RUNBOOK) -> Path:
    book = tmp_path / "docs" / "services" / "svc" / "ops"
    book.mkdir(parents=True)
    _ = (book / "run.md").write_text(runbook, encoding="utf-8")
    _ = (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
    (tmp_path / "src").mkdir()
    _ = (tmp_path / "src" / "main.py").write_text("", encoding="utf-8")
    return tmp_path


def test_a_makefile_joins_when_a_runbook_calls_a_target_it_defines(tmp_path: Path) -> None:
    root = _repo(tmp_path, "up:\n\tdocker compose up\n")
    assert stack_files(root, "svc", ["src/main.py"], SourceRepo(path=root)) == {"Makefile"}


def test_a_makefile_stays_out_when_no_runbook_target_is_defined_in_it(tmp_path: Path) -> None:
    root = _repo(tmp_path, "UP := 1\nlint:\n\truff check .\n")
    assert stack_files(root, "svc", ["src/main.py"], SourceRepo(path=root)) == frozenset()


def test_a_make_call_outside_a_runbook_does_not_pull_the_makefile_in(tmp_path: Path) -> None:
    root = _repo(tmp_path, "up:\n\ttrue\n", RUNBOOK.replace("type: runbook", "type: concept"))
    assert stack_files(root, "svc", ["src/main.py"], SourceRepo(path=root)) == frozenset()
