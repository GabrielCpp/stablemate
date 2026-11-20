"""A catch-up flow bound to a scripted agent, a git repo that is both the app and the book root, and a stand-in for the book's own commands."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import cast

import pytest
from _books import write_book
from okf_book.support import Reply, ScriptedRunner, git, run_env
from workhorse.pyflow.engine import Engine, RunEnv

from workhorse.pyflow import Await, Continue, Transition
from workhorse_workflows.okf_book.catch_up.flow import CatchUpBooks
from workhorse_workflows.okf_book.catch_up.models import CatchUpOutcome
from workhorse_workflows.okf_book.shared import book_gates

UPDATE = "update-book"


def stale_printed(verified: str, elements: dict[str, str], unnamed: list[str]) -> str:
    lines = [f"verified at {verified}, app at 9f8e7d6", "", "## Stale elements"]
    lines += [f"- {name}: {path} (2 commits: a1b2c3d, e4f5a6b)" for name, path in elements.items()]
    lines += ["", "## Changed files no element names"]
    lines += [f"- {path} (1 commits: a1b2c3d)" for path in unnamed]
    lines += ["", "## Changed functions no element names", "", "## Changed beside the named symbols, functions not told apart"]
    lines += ["", "## Pointers to files that no longer exist", "", "## Decisions touching stale elements"]
    return "\n".join(lines) + "\n"


def make_app(repo: Path) -> str:
    """The repo as an app with one file at two commits, and the first commit's id."""
    git(repo, "init", "-q", "-b", "main")
    (repo / "ledger").mkdir()
    (repo / "ledger/ping.py").write_text("print('v1')\n", encoding="utf-8")
    (repo / "ledger/new.py").write_text("print('new')\n", encoding="utf-8")
    git(repo, "add", "ledger")
    git(repo, "commit", "-q", "-m", "chore: start")
    first = git(repo, "rev-parse", "--short", "HEAD").strip()
    (repo / "ledger/ping.py").write_text("print('v2')\n", encoding="utf-8")
    (repo / "ledger/new.py").write_text("print('newer')\n", encoding="utf-8")
    git(repo, "commit", "-q", "-am", "feat: change")
    return first


def build_flow(tmp_path: Path, replies: dict[str, Reply] | None = None, services: list[str] | None = None, books: tuple[str, ...] = ("ledger",), history: str = "") -> tuple[CatchUpBooks, ScriptedRunner, RunEnv]:
    runner = ScriptedRunner(replies or {})
    env = run_env(tmp_path / "runs", runner)
    repo = tmp_path / "repo"
    repo.mkdir()
    for book in books:
        write_book(repo, book)
    flow = CatchUpBooks(repo_dir=str(repo), stack_copy="evening", services=services or [], format_history=history)
    flow._bind(Engine(env))  # pyright: ignore[reportPrivateUsage]
    return flow, runner, env


def book_exits(
    monkeypatch: pytest.MonkeyPatch,
    stale: dict[str, tuple[int, str] | tuple[int, str, str]] | None = None,
    calls: dict[str, list[str]] | None = None,
    checks: dict[str, list[tuple[int, str]]] | None = None,
    plans: dict[str, tuple[int, dict[str, object]]] | None = None,
    **codes: int,
) -> list[list[str]]:
    """Stand in for the book's commands. `checks` lists what each module's check says in turn, the last repeating, and `plans` what its affected writes."""
    seen: list[list[str]] = []
    stale = stale or {}
    calls = calls or {}
    asked: dict[str, int] = {}
    checks = checks or {}
    plans = plans or {}

    def _run(argv: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        seen.append(argv)
        if argv[1] == "-c":
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(calls.get(argv[3], [])), stderr="")
        verb, module = argv[3], argv[4]
        if verb == "stale":
            code, said, *error = stale.get(module, (0, "nothing stale\n"))
            return subprocess.CompletedProcess(argv, code, stdout=said, stderr="".join(error))
        if verb == "check" and module in checks:
            said = checks[module]
            code, text = said[min(asked.get(module, 0), len(said) - 1)]
            asked[module] = asked.get(module, 0) + 1
            return subprocess.CompletedProcess(argv, code, stdout=text, stderr="")
        if verb == "affected":
            code, plan = plans.get(module, (0, {"plan": "none"}))
            out = Path(argv[argv.index("--out") + 1])
            out.mkdir(parents=True, exist_ok=True)
            (out / "ledger-affected.json").write_text(json.dumps(plan), encoding="utf-8")
            return subprocess.CompletedProcess(argv, code, stdout="written", stderr="")
        return subprocess.CompletedProcess(argv, codes.get(verb, 0), stdout=f"{verb} said cell 7 differs", stderr="")

    monkeypatch.setattr(book_gates, "run_tool", _run)
    return seen


def advance(flow: CatchUpBooks, step: Transition) -> Continue[...] | Await[...]:
    """Run the state the transition names, with the parameters it hands it."""
    current = cast("Continue[...] | Await[...]", step)
    return getattr(flow, current.state)(**current.params)  # pyright: ignore[reportAny]


def walk(flow: CatchUpBooks, step: Transition, until: str = "books") -> Continue[...] | Await[...]:
    """Follow the states the flow names until it reaches `until`."""
    current = cast("Continue[...] | Await[...]", step)
    while current.state != until:
        current = advance(flow, current)
    return current


def summarized(flow: CatchUpBooks) -> CatchUpOutcome:
    done = flow.summarize()
    assert isinstance(done.result, CatchUpOutcome)
    return done.result


def stale_book(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, replies: dict[str, Reply] | None = None, **codes: int) -> tuple[CatchUpBooks, ScriptedRunner, list[list[str]]]:
    """A flow with the ledger book stale in `ledger/ping.py` and `ledger/new.py`, filed and ready for its first lap."""
    flow, runner, _env = build_flow(tmp_path, replies)
    first = make_app(flow.root)
    said = stale_printed(first, {"Ping": "ledger/ping.py", "Entry": "ledger/ping.py"}, ["ledger/new.py"])
    seen = book_exits(monkeypatch, stale={"services.ledger": (1, said)}, calls={"services.ledger": ["Ping", "Pong", "Other"]}, checks=None, plans=None, **codes)
    flow.fill()
    return flow, runner, seen
