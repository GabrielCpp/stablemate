"""The owner writes the Python book a lap at a time, the book's own check and run judge each lap, and a green book is committed."""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import cast

import pytest
from _books import TODO_BOOK, write_todo_book
from _workspace import cut_run_worktrees, lay_out, name_members, run_git
from okf_book.main.flows import book_exits, build_flow, workspace_flow, written_book
from okf_book.support import ScriptedRunner, git, install_book_skill, run_env
from workhorse.pyflow import Await, Continue, Done
from workhorse import templates
from workhorse.pyflow.engine import Engine

from workhorse_workflows import okf_book
from workhorse_workflows.okf_book.main import python_book_flow
from workhorse_workflows.okf_book.shared import book_gates
from workhorse_workflows.okf_book.main.python_book_flow import PythonBookOutcome, WritePythonBook

WRITE = "write-python-book"


def test_the_owner_turn_names_the_package_and_the_commands_that_judge_it(tmp_path: Path) -> None:
    flow, runner = build_flow(tmp_path, {WRITE: lambda _args: {"done": "the ledger book", "blocked": ""}})

    step = flow.write(gate="", lap=1)

    assert isinstance(step, Continue) and step.state == "check"
    sent = runner.args_of(WRITE)[0]
    assert sent["package"] == "services/ledger"
    assert sent["modules"] == ["services.ledger"]
    assert runner.chains[0][1] == "pybook:ledger"


def test_a_service_reached_by_two_surfaces_gets_one_module_per_surface(tmp_path: Path) -> None:
    flow, runner = build_flow(tmp_path, {WRITE: lambda _args: {"done": "the ledger book", "blocked": ""}}, kind="http, web")

    flow.write(gate="", lap=1)

    sent = runner.args_of(WRITE)[0]
    assert sent["kinds"] == ["http", "web"]
    assert sent["modules"] == ["services.ledger.http", "services.ledger.web"]


def test_the_second_surface_red_sends_the_owner_another_lap_naming_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen = book_exits(monkeypatch, red_module="services.ledger.web", run=1)
    flow, _runner = build_flow(tmp_path, kind="http,web")

    step = flow.play(lap=1)

    assert [argv[4] for argv in seen] == ["services.ledger.http", "services.ledger.web"]
    assert seen[0][5:] == ["--out", str(flow.run_dir / "book-run" / "services.ledger.http"), "--fresh-data"]
    assert isinstance(step, Continue) and step.state == "write"
    assert "run services.ledger.web` exited 1" in cast("str", step.params["gate"])


def test_a_blocked_owner_waits_for_the_operator_and_hears_the_answer_next_lap(tmp_path: Path) -> None:
    flow, _runner = build_flow(tmp_path, {WRITE: lambda _args: {"done": "", "blocked": "which clock does the ledger close on"}})

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
    book_exits(monkeypatch, check=1)
    flow, _runner = build_flow(tmp_path)

    step = flow.check(lap=1)

    assert isinstance(step, Continue) and step.state == "write"
    assert step.params["lap"] == 2
    assert "check said cell 7 differs" in cast("str", step.params["gate"])


def test_a_book_still_red_after_the_last_lap_waits_for_the_operator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book_exits(monkeypatch, run=1)
    flow, _runner = build_flow(tmp_path)

    step = flow.play(lap=python_book_flow.MAX_LAPS)

    assert isinstance(step, Await) and step.path == flow.run_dir / python_book_flow.RED_GATE
    assert step.state == "heard"
    assert "run said cell 7 differs" in step.questions


def test_a_run_that_could_not_judge_waits_and_runs_again_without_a_lap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book_exits(monkeypatch, run=python_book_flow.COULD_NOT_JUDGE)
    flow, runner = build_flow(tmp_path)

    step = flow.play(lap=1)

    assert isinstance(step, Await) and step.path == flow.run_dir / python_book_flow.ENVIRONMENT_GATE
    assert step.state == "play" and step.params == {"lap": 1}
    assert runner.total == 0


def test_a_green_check_sends_the_book_to_the_commit_checks_and_play_runs_it_into_the_run_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen = book_exits(monkeypatch)
    flow, _runner = build_flow(tmp_path)

    checked = flow.check(lap=1)
    played = flow.play(lap=1)

    assert isinstance(checked, Continue) and checked.state == "checks"
    assert isinstance(played, Continue) and played.state == "account"
    assert seen[1][3:] == ["run", "services.ledger", "--out", str(flow.run_dir / "book-run" / "services.ledger"), "--fresh-data"]


def test_a_missing_list_that_is_not_empty_sends_the_owner_another_lap_with_the_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen = book_exits(monkeypatch, missing=1)
    flow, _runner = build_flow(tmp_path)

    step = flow.account(lap=1)

    assert isinstance(step, Continue) and step.state == "write"
    assert step.params["lap"] == 2
    assert "`python -m ostler.book missing services.ledger` exited 1" in cast("str", step.params["gate"])
    assert "missing said cell 7 differs" in cast("str", step.params["gate"])
    assert seen[0][3:] == ["missing", "services.ledger", "--app", str(flow.code_root), "--under", "ledger"]


def test_an_empty_missing_list_stamps_the_book(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book_exits(monkeypatch)
    flow, _runner = build_flow(tmp_path)

    step = flow.account(lap=1)

    assert isinstance(step, Continue) and step.state == "stamp"


def test_a_missing_list_still_full_after_the_last_lap_waits_for_the_operator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book_exits(monkeypatch, missing=1)
    flow, _runner = build_flow(tmp_path)

    step = flow.account(lap=python_book_flow.MAX_LAPS)

    assert isinstance(step, Await) and step.path == flow.run_dir / python_book_flow.RED_GATE
    assert "missing said cell 7 differs" in step.questions


def test_a_run_with_no_source_folder_asks_missing_for_the_roots_of_the_book(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen = book_exits(monkeypatch)
    flow, _runner = build_flow(tmp_path)
    flow.source_folder = ""

    flow.account(lap=1)
    rendered = _rendered(flow, tmp_path, monkeypatch)

    assert "--under" not in seen[0]
    assert f"python -m ostler.book missing services.ledger --app {flow.code_root}\n" in rendered
    assert "--under" not in rendered


def test_the_prompt_makes_the_owner_answer_for_every_file_of_the_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _runner = build_flow(tmp_path)

    rendered = _rendered(flow, tmp_path, monkeypatch)

    assert f"answers for every file under `{flow.source_root}/`" in rendered
    assert f"python -m ostler.book missing services.ledger --app {flow.code_root} --under ledger\n" in rendered
    assert "never ignored" in rendered


def test_a_run_that_names_a_stack_copy_plays_the_book_on_it_and_tells_the_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen = book_exits(monkeypatch)
    flow, _runner = build_flow(tmp_path)
    flow.stack_copy = "evening"

    flow.check(lap=1)
    flow.play(lap=1)
    rendered = _rendered(flow, tmp_path, monkeypatch)

    assert seen[0][3:] == ["check", "services.ledger", "--app", str(flow.code_root)]
    assert seen[1][-3:] == ["--copy", "evening", "--fresh-data"]
    assert "python -m ostler.book run services.ledger --only <each endpoint or interaction this turn touched> --copy evening\n" in rendered
    assert "as the stack copy `evening`" in rendered


def test_a_run_that_names_no_stack_copy_leaves_the_copy_to_the_book(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _runner = build_flow(tmp_path)

    rendered = _rendered(flow, tmp_path, monkeypatch)

    assert "--copy" not in rendered
    assert "stack copy" not in rendered


def test_a_service_named_with_a_hyphen_is_told_to_import_its_own_modules_relatively(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plain, _runner = build_flow(tmp_path)
    hyphened = plain.model_copy(update={"service": "ledger-api"})

    assert "imports its siblings relatively" not in _rendered(plain, tmp_path, monkeypatch)
    told = templates.render(python_book_flow.WRITE_PROMPT, hyphened._prompt_args(""), Path(okf_book.__file__).parent)  # pyright: ignore[reportPrivateUsage]
    assert "imports its siblings relatively" in told
    assert "python -m ostler.book check services.ledger-api\n" in told


def test_a_green_book_commits_only_its_package(tmp_path: Path) -> None:
    flow, _runner = build_flow(tmp_path)
    repo = written_book(flow)

    step = flow.commit(lap=2)

    assert isinstance(step, Done)
    assert step.result == PythonBookOutcome(service="ledger", laps=2)
    assert git(repo, "show", "--name-only", "--format=", "HEAD").split() == ["services/ledger/service.py"]
    assert "scratch.txt" in git(repo, "status", "--porcelain")


def _rendered(flow: WritePythonBook, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    install_book_skill(tmp_path / "home", monkeypatch)
    return templates.render(python_book_flow.WRITE_PROMPT, flow._prompt_args(""), Path(okf_book.__file__).parent)  # pyright: ignore[reportPrivateUsage]


def test_the_owner_is_pointed_at_the_other_books_of_the_repo_for_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _runner = build_flow(tmp_path)
    for book in ("ledger/service.py", "billing/service.py", "desk/http/service.py", "desk/web/service.py", "notes/README.md"):
        path = flow.root / "services" / book
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

    rendered = _rendered(flow, tmp_path, monkeypatch)

    assert flow._prompt_args("")["references"] == ["services/billing", "services/desk"]  # pyright: ignore[reportPrivateUsage]
    assert "- `services/billing/`\n- `services/desk/`\n" in rendered
    assert "services/ledger/`\n" not in rendered
    assert "notes" not in rendered
    assert "Read one that is reached the way this service is, for the shape of each file.\n\nA finished book is also the only place" in rendered
    assert f"Read no\nsource outside `{flow.source_root}/`." in rendered
    assert "the reference names the\nrecord by a word." in rendered
    assert "Take nothing of" not in rendered


def test_a_repo_with_no_other_book_names_no_reference(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _runner = build_flow(tmp_path)

    rendered = _rendered(flow, tmp_path, monkeypatch)

    assert "finished books" not in rendered


def test_a_two_surface_prompt_asks_for_one_model_and_judges_each_surface(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _runner = build_flow(tmp_path, kind="http,web")

    rendered = _rendered(flow, tmp_path, monkeypatch)

    assert "reached by: http, web" in rendered
    assert "`services/ledger/model/`" in rendered
    for module in ("services.ledger.http", "services.ledger.web"):
        for verb in ("check", "index"):
            assert f"python -m ostler.book {verb} {module}\n" in rendered
        assert f"python -m ostler.book run {module} --only " in rendered


def test_in_a_workspace_the_book_is_written_and_committed_in_the_artifacts_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _runner, laid = workspace_flow(tmp_path, monkeypatch)
    api_head = git(laid.api, "rev-parse", "HEAD")
    (laid.artifacts / "services/api/ledger").mkdir(parents=True)
    (laid.artifacts / "services/api/ledger/service.py").write_text("NAME = 'ledger'\n", encoding="utf-8")

    step = flow.commit(lap=1)

    assert flow.root == laid.artifacts.resolve()
    assert isinstance(step, Done)
    assert git(laid.artifacts, "show", "--name-only", "--format=", "HEAD").split() == ["services/api/ledger/service.py"]
    assert git(laid.api, "rev-parse", "HEAD") == api_head


def test_in_a_worktree_run_the_book_is_written_and_committed_in_the_artifacts_worktree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    laid = lay_out(tmp_path, run_git)
    name_members(tmp_path, monkeypatch, laid)
    trees = cut_run_worktrees(laid, tmp_path / "trees", "run/book-t", run_git)
    flow = WritePythonBook(repo_dir=str(trees.api), service="ledger", kind="cli", source_folder="ledger")
    flow._bind(Engine(run_env(tmp_path / "runs", ScriptedRunner({}))))  # pyright: ignore[reportPrivateUsage]
    main_head = git(laid.artifacts, "rev-parse", "HEAD")
    (trees.artifacts / "services/api/ledger").mkdir(parents=True)
    (trees.artifacts / "services/api/ledger/service.py").write_text("NAME = 'ledger'\n", encoding="utf-8")

    step = flow.commit(lap=1)

    assert flow.root == trees.artifacts.resolve()
    assert isinstance(step, Done)
    assert git(trees.artifacts, "show", "--name-only", "--format=", "HEAD").split() == ["services/api/ledger/service.py"]
    assert git(laid.artifacts, "rev-parse", "HEAD") == main_head


def test_in_a_workspace_the_owner_is_told_both_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _runner, laid = workspace_flow(tmp_path, monkeypatch)

    rendered = _rendered(flow, tmp_path, monkeypatch)

    assert f"under the book root, `{laid.artifacts.resolve()}`" in rendered
    assert f"{laid.api.resolve()}/ledger/" in rendered


def test_in_a_workspace_the_owner_may_read_the_code_repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, runner, laid = workspace_flow(tmp_path, monkeypatch, {WRITE: lambda _args: {"done": "the ledger book", "blocked": ""}})

    flow.write(gate="", lap=1)

    sent = runner.nodes[0]
    assert sent.cwd == str(laid.artifacts.resolve())
    assert sent.add_dirs == [str(laid.api.resolve())]


def test_a_book_whose_pointer_names_a_missing_file_fails_the_check(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    write_todo_book(root)
    (root / "agents.yml").write_text("book:\n  home: repo\n", encoding="utf-8")
    app = tmp_path / "app-without-its-file"
    app.mkdir()

    gate = python_book_flow.python_book_check(logging.getLogger("test"), root, "services.api", app)

    assert gate.exit_code != 0
    assert "does not exist under" in gate.output


def test_a_book_whose_pointers_all_exist_passes_the_check(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    write_todo_book(root)
    (root / "agents.yml").write_text("book:\n  home: repo\n", encoding="utf-8")
    shutil.copy(TODO_BOOK / "app.py", root / "app.py")

    gate = python_book_flow.python_book_check(logging.getLogger("test"), root, "services.api", root)

    assert gate.exit_code == 0, gate.output



def test_the_owner_plays_only_what_it_touched_and_leaves_the_whole_book_to_the_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _runner = build_flow(tmp_path)

    rendered = _rendered(flow, tmp_path, monkeypatch)

    assert "python -m ostler.book run services.ledger --only " in rendered
    assert "python -m ostler.book run services.ledger\n" not in rendered
    assert "After the turn the flow plays the whole book once" in rendered
    assert "The app takes one play at a time" in rendered
    assert "start it in the background and wait\non its exit" in rendered


def test_the_run_play_starts_in_the_code_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _runner = build_flow(tmp_path)
    cwds: list[object] = []

    def _run(argv: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
        cwds.append(kw["cwd"])
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(book_gates, "run_tool", _run)

    _ = flow.play(lap=1)

    assert cwds == [flow.code_root]
