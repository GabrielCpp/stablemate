"""The owner writes the Python book a lap at a time, the book's own check and run judge each lap, and a green book is committed."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import cast

import pytest
from okf_book.support import Reply, ScriptedRunner, git, run_env
from workhorse.pyflow import Await, Continue, Done
from workhorse import templates
from workhorse.pyflow.engine import Engine

from workhorse_workflows import okf_book
from workhorse_workflows.okf_book.main import python_book_flow
from workhorse_workflows.okf_book.main.python_book_flow import PythonBookOutcome, WritePythonBook

WRITE = "write-python-book"


def _flow(tmp_path: Path, replies: dict[str, Reply] | None = None, kind: str = "cli") -> tuple[WritePythonBook, ScriptedRunner]:
    runner = ScriptedRunner(replies or {})
    env = run_env(tmp_path / "runs", runner)
    repo = tmp_path / "repo"
    repo.mkdir()
    flow = WritePythonBook(repo_dir=str(repo), service="ledger", kind=kind, source_folder="ledger")
    flow._bind(Engine(env))  # pyright: ignore[reportPrivateUsage]
    return flow, runner


def _book_exits(monkeypatch: pytest.MonkeyPatch, red_module: str = "", **codes: int) -> list[list[str]]:
    seen: list[list[str]] = []

    def _run(argv: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        seen.append(argv)
        verb, module = argv[3], argv[4]
        code = codes.get(verb, 0) if module == red_module or not red_module else 0
        return subprocess.CompletedProcess(argv, code, stdout=f"{verb} said cell 7 differs", stderr="")

    monkeypatch.setattr(python_book_flow, "run_tool", _run)
    return seen


def test_the_owner_turn_names_the_package_and_the_commands_that_judge_it(tmp_path: Path) -> None:
    flow, runner = _flow(tmp_path, {WRITE: lambda _args: {"done": "the ledger book", "blocked": ""}})

    step = flow.write(gate="", lap=1)

    assert isinstance(step, Continue) and step.state == "check"
    sent = runner.args_of(WRITE)[0]
    assert sent["package"] == "services/ledger"
    assert sent["modules"] == ["services.ledger"]
    assert runner.chains[0][1] == "pybook:ledger"


def test_a_service_reached_by_two_surfaces_gets_one_module_per_surface(tmp_path: Path) -> None:
    flow, runner = _flow(tmp_path, {WRITE: lambda _args: {"done": "the ledger book", "blocked": ""}}, kind="http, web")

    flow.write(gate="", lap=1)

    sent = runner.args_of(WRITE)[0]
    assert sent["kinds"] == ["http", "web"]
    assert sent["modules"] == ["services.ledger.http", "services.ledger.web"]


def test_the_second_surface_red_sends_the_owner_another_lap_naming_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _book_exits(monkeypatch, red_module="services.ledger.web", run=1)
    flow, _runner = _flow(tmp_path, kind="http,web")

    step = flow.play(lap=1)

    assert [argv[4] for argv in seen] == ["services.ledger.http", "services.ledger.web"]
    assert seen[0][5:] == ["--out", str(flow.run_dir / "book-run" / "services.ledger.http")]
    assert isinstance(step, Continue) and step.state == "write"
    assert "run services.ledger.web` exited 1" in cast("str", step.params["gate"])


def test_a_blocked_owner_waits_for_the_operator_and_hears_the_answer_next_lap(tmp_path: Path) -> None:
    flow, _runner = _flow(tmp_path, {WRITE: lambda _args: {"done": "", "blocked": "which clock does the ledger close on"}})

    step = flow.write(gate="", lap=2)

    assert isinstance(step, Await) and step.path == flow.run_dir / python_book_flow.BLOCKED_GATE
    assert "which clock does the ledger close on" in step.questions
    question = cast("str", step.params["question"])
    step.path.write_text(f"{question}\n\nThe business day, in UTC.\n", encoding="utf-8")
    heard = flow.heard(question=question, gate_name=python_book_flow.BLOCKED_GATE, lap=2)
    assert heard.state == "write"
    assert "The business day, in UTC." in cast("str", heard.params["gate"])
    assert heard.params["lap"] == 2


def test_a_red_check_sends_the_owner_another_lap_with_what_it_printed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _book_exits(monkeypatch, check=1)
    flow, _runner = _flow(tmp_path)

    step = flow.check(lap=1)

    assert isinstance(step, Continue) and step.state == "write"
    assert step.params["lap"] == 2
    assert "check said cell 7 differs" in cast("str", step.params["gate"])


def test_a_book_still_red_after_the_last_lap_waits_for_the_operator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _book_exits(monkeypatch, run=1)
    flow, _runner = _flow(tmp_path)

    step = flow.play(lap=python_book_flow.MAX_LAPS)

    assert isinstance(step, Await) and step.path == flow.run_dir / python_book_flow.RED_GATE
    assert step.state == "heard"
    assert "run said cell 7 differs" in step.questions


def test_a_run_that_could_not_judge_waits_and_runs_again_without_a_lap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _book_exits(monkeypatch, run=python_book_flow.COULD_NOT_JUDGE)
    flow, runner = _flow(tmp_path)

    step = flow.play(lap=1)

    assert isinstance(step, Await) and step.path == flow.run_dir / python_book_flow.ENVIRONMENT_GATE
    assert step.state == "play" and step.params == {"lap": 1}
    assert runner.total == 0


def test_a_green_check_plays_the_book_into_the_run_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _book_exits(monkeypatch)
    flow, _runner = _flow(tmp_path)

    checked = flow.check(lap=1)
    played = flow.play(lap=1)

    assert isinstance(checked, Continue) and checked.state == "play"
    assert isinstance(played, Continue) and played.state == "render"
    assert seen[1][3:] == ["run", "services.ledger", "--out", str(flow.run_dir / "book-run" / "services.ledger")]


def test_a_run_that_names_a_stack_copy_plays_the_book_on_it_and_tells_the_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _book_exits(monkeypatch)
    flow, _runner = _flow(tmp_path)
    flow.stack_copy = "evening"

    flow.check(lap=1)
    flow.play(lap=1)
    rendered = _rendered(flow, tmp_path, monkeypatch)

    assert seen[0][3:] == ["check", "services.ledger"]
    assert seen[1][-2:] == ["--copy", "evening"]
    assert "python -m ostler.book run services.ledger --copy evening\n" in rendered
    assert "as the stack copy `evening`" in rendered


def test_a_run_that_names_no_stack_copy_leaves_the_copy_to_the_book(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _runner = _flow(tmp_path)

    rendered = _rendered(flow, tmp_path, monkeypatch)

    assert "--copy" not in rendered
    assert "stack copy" not in rendered


def test_a_green_book_commits_only_its_package(tmp_path: Path) -> None:
    flow, _runner = _flow(tmp_path)
    repo = flow.root
    git(repo, "init", "-q", "-b", "main")
    (repo / "README.md").write_text("app\n", encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "commit", "-q", "-m", "chore: start")
    (repo / "services/ledger").mkdir(parents=True)
    (repo / "services/ledger/service.py").write_text("NAME = 'ledger'\n", encoding="utf-8")
    (repo / "scratch.txt").write_text("not the book\n", encoding="utf-8")

    step = flow.commit(lap=2)

    assert isinstance(step, Done)
    assert step.result == PythonBookOutcome(service="ledger", laps=2)
    assert git(repo, "show", "--name-only", "--format=", "HEAD").split() == ["services/ledger/service.py"]
    assert "scratch.txt" in git(repo, "status", "--porcelain")


def _rendered(flow: WritePythonBook, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    home = tmp_path / "home"
    skill = home / ".claude/skills/ostler-book/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: ostler-book\nmetadata:\n  name: ostler-book\n---\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENT_CLI", "claude")
    return templates.render(python_book_flow.WRITE_PROMPT, flow._prompt_args(""), Path(okf_book.__file__).parent)  # pyright: ignore[reportPrivateUsage]


def test_the_owner_is_pointed_at_the_other_books_of_the_repo_for_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _runner = _flow(tmp_path)
    for book in ("ledger/service.py", "billing/service.py", "desk/http/service.py", "desk/web/service.py", "notes/README.md"):
        path = flow.root / "services" / book
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

    rendered = _rendered(flow, tmp_path, monkeypatch)

    assert flow._prompt_args("")["references"] == ["services/billing", "services/desk"]  # pyright: ignore[reportPrivateUsage]
    assert "- `services/billing/`\n- `services/desk/`\n" in rendered
    assert "services/ledger/`\n" not in rendered
    assert "notes" not in rendered


def test_a_repo_with_no_other_book_names_no_reference(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _runner = _flow(tmp_path)

    rendered = _rendered(flow, tmp_path, monkeypatch)

    assert "finished books" not in rendered


def test_a_two_surface_prompt_asks_for_one_model_and_judges_each_surface(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _runner = _flow(tmp_path, kind="http,web")

    rendered = _rendered(flow, tmp_path, monkeypatch)

    assert "reached by: http, web" in rendered
    assert "`services/ledger/model/`" in rendered
    for module in ("services.ledger.http", "services.ledger.web"):
        for verb in ("check", "run", "index"):
            assert f"python -m ostler.book {verb} {module}\n" in rendered
