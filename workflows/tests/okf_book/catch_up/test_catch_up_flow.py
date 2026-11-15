"""The catch-up reads each book's stale report, has an owner update a stale book from its changed elements and their diff, judges it with the book's own gates, and stamps and commits a green one."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest
from okf_book.catch_up.flows import UPDATE, advance, book_exits, build_flow, make_app, stale_book, stale_printed, summarized, walk
from okf_book.support import Reply, git, install_book_skill
from workhorse import templates
from workhorse.pyflow import Await, Continue
from workhorse.pyflow.graph import state_graph
from workhorse.worklist import WorkItem

from workhorse_workflows import okf_book
from workhorse_workflows.okf_book.catch_up.flow import CatchUpBooks
from workhorse_workflows.okf_book.catch_up.models import BookOutcome
from workhorse_workflows.okf_book.main.python_book_flow import MAX_LAPS

DONE: dict[str, Reply] = {UPDATE: lambda _args: {"done": "the ledger book", "blocked": "", "added": []}}


def test_a_book_whose_stale_report_is_empty_is_skipped_and_named_current(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, runner, _env = build_flow(tmp_path)
    seen = book_exits(monkeypatch)

    flow.fill()
    step = flow.books()
    done = summarized(flow)

    assert isinstance(step, Continue) and step.state == "summarize"
    assert [argv[3] for argv in seen] == ["stale"]
    assert runner.total == 0
    assert done.books == [BookOutcome(service="ledger", verdict="current")]
    assert done.summary == "ledger: current"


def test_a_book_with_no_verified_commit_is_named_a_first_book_and_not_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, runner, _env = build_flow(tmp_path)
    book_exits(monkeypatch, stale={"services.ledger": (2, "not verified: write the commit with 'verified'\n")})

    flow.fill()
    step = flow.books()
    done = summarized(flow)

    assert isinstance(step, Continue) and step.state == "summarize"
    assert runner.total == 0
    assert done.books == [BookOutcome(service="ledger", verdict="first-book")]
    assert done.summary == "ledger: first book, write it with python_book"
    assert not (flow.root / "services/ledger/VERIFIED").exists()


def test_a_named_service_with_no_book_is_a_first_book(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, runner, _env = build_flow(tmp_path, services=["billing"])
    seen = book_exits(monkeypatch)

    flow.fill()
    done = summarized(flow)

    assert seen == []
    assert runner.total == 0
    assert done.books == [BookOutcome(service="billing", verdict="first-book")]


def test_a_stale_book_gets_an_owner_turn_with_its_changed_elements_their_files_and_their_diff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, runner, _seen = stale_book(tmp_path, monkeypatch, DONE)

    step = walk(flow, flow.books(), "write")
    advance(flow, step)

    sent = runner.args_of(UPDATE)[0]
    sections = cast("list[dict[str, object]]", sent["sections"])
    assert sections[0]["module"] == "services.ledger"
    assert sections[0]["elements"] == [{"name": "Entry", "files": ["ledger/ping.py"]}, {"name": "Ping", "files": ["ledger/ping.py"]}]
    assert sections[0]["new_files"] == ["ledger/new.py"]
    diff = cast("str", sections[0]["diff"])
    assert "-print('v1')" in diff and "+print('v2')" in diff
    assert "-print('new')" in diff and "+print('newer')" in diff
    assert runner.chains[0][1] == "catchup:ledger"


def test_the_owner_prompt_names_each_changed_element_each_new_file_and_the_diff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, runner, _seen = stale_book(tmp_path, monkeypatch, DONE)
    install_book_skill(tmp_path / "home", monkeypatch)

    walk(flow, flow.books(), "write")
    flow.write(service="ledger", gate="", lap=1, added=[])
    rendered = templates.render("catch_up/prompts/update-book.md", runner.args_of(UPDATE)[0], Path(okf_book.__file__).parent)

    assert "- `Ping`: ledger/ping.py" in rendered
    assert "- `ledger/new.py`" in rendered
    assert "+print('v2')" in rendered
    assert "services.ledger" in rendered
    assert "as the stack copy `evening`" in rendered


def test_the_owner_plays_its_own_change_on_the_stack_copy_before_it_replies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, runner, _seen = stale_book(tmp_path, monkeypatch, DONE)
    install_book_skill(tmp_path / "home", monkeypatch)
    walk(flow, flow.books(), "write")
    flow.write(service="ledger", gate="", lap=1, added=[])
    args = runner.args_of(UPDATE)[0]
    root = Path(okf_book.__file__).parent

    told = templates.render("catch_up/prompts/update-book.md", args, root)
    bare = templates.render("catch_up/prompts/update-book.md", {**args, "stack_copy": ""}, root)

    assert "python -m ostler.book run <module> --only <names> --copy evening --out <a scratch folder>" in told
    assert "reads 0 fail" in told
    assert "exits 3 could not judge the environment" in told
    assert "--only" not in bare


def test_the_targeted_run_names_the_elements_of_the_report_and_those_the_turn_added(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    replies: dict[str, Reply] = {UPDATE: lambda _args: {"done": "added", "blocked": "", "added": ["Pong", "Stray"]}}
    flow, _runner, seen = stale_book(tmp_path, monkeypatch, replies)

    step = walk(flow, flow.books(), "write")
    step = advance(flow, step)
    walk(flow, step, "stamp")

    run = next(argv for argv in seen if argv[3:5] == ["run", "services.ledger"])
    assert run[5:] == ["--out", str(flow.run_dir / "book-run/services.ledger"), "--only", "Ping,Pong", "--copy", "evening"]


def test_a_book_whose_gates_pass_is_stamped_verified_and_committed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _runner, seen = stale_book(tmp_path, monkeypatch, DONE)
    head = git(flow.root, "rev-parse", "HEAD")
    (flow.root / "services/ledger/VERIFIED").write_text("9f8e7d6\n", encoding="utf-8")
    (flow.root / "scratch.txt").write_text("not the book\n", encoding="utf-8")

    step = walk(flow, flow.books(), "write")
    step = walk(flow, advance(flow, step), "books")

    verbs = [argv[3] if argv[1] != "-c" else "calls" for argv in seen]
    assert verbs == ["stale", "check", "calls", "run", "verified"]
    assert seen[-1][3:] == ["verified", "services.ledger", "--app", str(flow.code_root)]
    assert git(flow.root, "rev-parse", "HEAD") != head
    assert git(flow.root, "log", "-1", "--format=%s") == "docs(ledger): catch the ledger book up with the app\n"
    assert sorted(git(flow.root, "show", "--name-only", "--format=", "HEAD").split()) == ["services/ledger/VERIFIED", "services/ledger/service.py"]
    assert "scratch.txt" in git(flow.root, "status", "--porcelain")
    done = walk(flow, step, "summarize")
    assert summarized(flow).books == [BookOutcome(service="ledger", verdict="caught-up", laps=1, elements=["Entry", "Ping"], added=[])]
    assert isinstance(done, Continue)


def test_a_book_whose_whole_missing_list_is_not_empty_is_caught_up_when_its_changed_files_are_named(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _runner, seen = stale_book(tmp_path, monkeypatch, DONE, missing=1)

    step = walk(flow, flow.books(), "write")
    walk(flow, advance(flow, step), "books")

    assert "missing" not in [argv[3] for argv in seen if argv[1] != "-c"]
    assert git(flow.root, "log", "-1", "--format=%s") == "docs(ledger): catch the ledger book up with the app\n"
    assert summarized(flow).books[0].verdict == "caught-up"


def test_a_red_gate_starts_another_lap_with_the_gates_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _runner, _seen = stale_book(tmp_path, monkeypatch, DONE, run=1)

    step = walk(flow, flow.books(), "write")
    step = walk(flow, advance(flow, step), "write")

    assert isinstance(step, Continue)
    assert step.params["lap"] == 2
    assert "`python -m ostler.book run services.ledger` exited 1" in cast("str", step.params["gate"])
    assert "run said cell 7 differs" in cast("str", step.params["gate"])


def test_a_red_gate_after_the_lap_cap_fails_the_book_and_goes_on_without_committing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _runner, _seen = stale_book(tmp_path, monkeypatch, DONE, verified=1)
    head = git(flow.root, "rev-parse", "HEAD")

    walk(flow, flow.books(), "write")
    step = flow.stamp(service="ledger", lap=MAX_LAPS, added=[])

    assert isinstance(step, Continue) and step.state == "books"
    assert git(flow.root, "rev-parse", "HEAD") == head
    outcome = summarized(flow).books[0]
    assert outcome.verdict == "failed" and outcome.laps == MAX_LAPS
    assert "`python -m ostler.book verified services.ledger` exited 1" in outcome.gate
    assert [item.status for item in flow.work_list.items("book")] == ["blocked"]


def test_a_gate_that_could_not_judge_waits_and_judges_again_without_a_lap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, runner, _seen = stale_book(tmp_path, monkeypatch, DONE, check=3)

    step = flow.check(service="ledger", lap=1, added=[])

    assert isinstance(step, Await) and step.state == "check"
    assert step.params == {"service": "ledger", "lap": 1, "added": []}
    assert runner.total == 0


def test_a_blocked_owner_fails_the_book_with_what_it_said(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    replies: dict[str, Reply] = {UPDATE: lambda _args: {"done": "", "blocked": "which clock does the ledger close on", "added": []}}
    flow, _runner, _seen = stale_book(tmp_path, monkeypatch, replies)

    step = walk(flow, flow.books(), "write")
    step = advance(flow, step)

    assert isinstance(step, Continue) and step.state == "books"
    outcome = summarized(flow).books[0]
    assert outcome.verdict == "failed"
    assert "which clock does the ledger close on" in outcome.gate


def test_a_resumed_run_continues_at_the_book_it_stopped_on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _runner, env = build_flow(tmp_path, books=("api", "web"))
    first = make_app(flow.root)
    said = stale_printed(first, {"Ping": "ledger/ping.py"}, [])
    seen = book_exits(monkeypatch, stale={"services.api": (1, said), "services.web": (1, said)})
    flow.fill()
    taken = flow.books()
    assert isinstance(taken, Continue) and cast("list[WorkItem]", taken.params["items"])[0].id == "api"
    asked = len(seen)

    env.resume_pending = True
    flow.fill()
    resumed = flow.books()

    assert len(seen) == asked
    assert isinstance(resumed, Continue) and resumed.state == "take"
    assert [item.id for item in cast("list[WorkItem]", resumed.params["items"])] == ["api"]
    assert [item.status for item in flow.work_list.items("book")] == ["active", ""]


def test_a_dry_run_walks_the_catch_up_to_a_green_end(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "kept.txt").write_text("kept\n", encoding="utf-8")
    git(repo, "add", "kept.txt")
    git(repo, "commit", "-q", "-m", "chore: start")
    home = tmp_path / "home"
    install_book_skill(home)
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin"}

    done = subprocess.run(
        [sys.executable, "-c", "from workhorse_workflows.okf_book.workflow import main; main()", "run", "catch_up", "--dry-run", "--runs-dir", str(tmp_path / "runs")],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert done.returncode == 0, done.stdout + done.stderr
    said = done.stdout + done.stderr
    assert "dry-run ok" in said
    assert "call   → commit_book_paths (dry-run)" in said
    assert "done   ← summarize" in said


def test_every_edge_of_the_catch_up_graph_has_a_reason() -> None:
    graph = state_graph(CatchUpBooks, workflow_dir=Path(okf_book.__file__).parent)

    bare = [(node.name, edge.target) for node in graph.states for edge in node.edges if not edge.reason]

    assert bare == []
    assert {"fill", "books", "take", "write", "check", "play", "stamp", "render", "commit", "summarize"} <= {node.name for node in graph.states}
