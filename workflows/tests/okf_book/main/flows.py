"""A python book flow bound to a scripted agent, and a stand-in for the book's own commands."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from workhorse.pyflow.engine import Engine
from workhorse_workflows.okf_book.main import python_book_flow
from workhorse_workflows.okf_book.main.python_book_flow import WritePythonBook

from okf_book.support import Reply, ScriptedRunner, run_env


def build_flow(tmp_path: Path, replies: dict[str, Reply] | None = None, kind: str = "cli") -> tuple[WritePythonBook, ScriptedRunner]:
    runner = ScriptedRunner(replies or {})
    env = run_env(tmp_path / "runs", runner)
    repo = tmp_path / "repo"
    repo.mkdir()
    flow = WritePythonBook(repo_dir=str(repo), service="ledger", kind=kind, source_folder="ledger")
    flow._bind(Engine(env))  # pyright: ignore[reportPrivateUsage]
    return flow, runner


def missing_printed(unnamed: list[str]) -> str:
    named = "## What the book names\n- ledger/home.py: Home (screen)\n"
    left = "\n## Left out by the book\n- *.css: 2 files\n"
    return f"{named}\n## Files no element names\n" + "".join(f"- {path}\n" for path in unnamed) + left + f"\n{len(unnamed)} of 9 files are in no element and under no ignore pattern\n"


def book_exits(monkeypatch: pytest.MonkeyPatch, red_module: str = "", unnamed: list[str] | None = None, **codes: int) -> list[list[str]]:
    seen: list[list[str]] = []

    def _run(argv: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        seen.append(argv)
        verb, module = argv[3], argv[4]
        code = codes.get(verb, 0) if module == red_module or not red_module else 0
        said = missing_printed(unnamed) if verb == "missing" and unnamed is not None else f"{verb} said cell 7 differs"
        return subprocess.CompletedProcess(argv, code, stdout=said, stderr="")

    monkeypatch.setattr(python_book_flow, "run_tool", _run)
    return seen
