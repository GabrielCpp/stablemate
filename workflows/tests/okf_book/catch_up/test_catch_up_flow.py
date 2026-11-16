"""The catch-up reads each book's stale report, has an owner update a stale book from its changed elements and their diff, judges it with the book's own gates, and stamps and commits a green one."""
from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from okf_book.catch_up.flows import UPDATE, advance, book_exits, build_flow, make_app, stale_book, stale_printed, summarized, walk
from okf_book.support import Reply, dry_run_said, git, install_book_skill
from workhorse import templates
from workhorse.pyflow import Await, Continue
from workhorse.pyflow.graph import state_graph
from workhorse.worklist import WorkItem

from workhorse_workflows import okf_book
from workhorse_workflows.okf_book.catch_up.flow import CatchUpBooks
from workhorse_workflows.okf_book.catch_up.models import BookOutcome
from workhorse_workflows.okf_book.catch_up.flow import STALE_GATE
from workhorse_workflows.okf_book.shared.book_flow import BLOCKED_GATE, MAX_LAPS, RED_GATE

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


def test_a_book_whose_service_declares_no_app_is_a_first_book_and_asks_no_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, runner, _env = build_flow(tmp_path)
    book_exits(monkeypatch, stale={"services.ledger": (2, "ledger declares no app\n")})

    filled = flow.fill()
    step = flow.books()
    done = summarized(flow)

    assert isinstance(filled, Continue)
    assert isinstance(step, Continue) and step.state == "summarize"
    assert runner.total == 0
    assert done.books == [BookOutcome(service="ledger", verdict="first-book")]
    assert not (flow.run_dir / STALE_GATE).exists()


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
    flow.write(service="ledger", gate="", lap=1, added=[], ignored=[])
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
    flow.write(service="ledger", gate="", lap=1, added=[], ignored=[])
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
    assert summarized(flow).books == [BookOutcome(service="ledger", verdict="caught-up", laps=1, elements=["Entry", "Ping"], added=[], ignored=[])]
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


def test_a_book_that_reaches_the_lap_cap_parks_on_the_operator_gate_with_the_red_gates_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _runner, _seen = stale_book(tmp_path, monkeypatch, DONE, verified=1)
    head = git(flow.root, "rev-parse", "HEAD")

    walk(flow, flow.books(), "write")
    step = flow.stamp(service="ledger", lap=MAX_LAPS, added=[], ignored=[])

    assert isinstance(step, Await) and step.state == "heard"
    assert step.path == flow.run_dir / RED_GATE
    assert "`python -m ostler.book verified services.ledger` exited 1" in step.questions
    assert "verified said cell 7 differs" in step.questions
    assert git(flow.root, "rev-parse", "HEAD") == head
    assert [item.status for item in flow.work_list.items("book")] == ["active"]


def test_the_operators_answer_resumes_that_same_book_and_reaches_the_owners_next_prompt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, runner, _seen = stale_book(tmp_path, monkeypatch, DONE, verified=1)
    install_book_skill(tmp_path / "home", monkeypatch)
    walk(flow, flow.books(), "write")
    parked = flow.stamp(service="ledger", lap=MAX_LAPS, added=["Pong"], ignored=[])
    assert isinstance(parked, Await)
    question = cast("str", parked.params["question"])
    parked.path.write_text(f"{question}\n\nThe ledger closes on the business day, in UTC.\n", encoding="utf-8")

    heard = advance(flow, parked)
    advance(flow, heard)

    assert heard.state == "write"
    assert (heard.params["service"], heard.params["lap"], heard.params["added"]) == ("ledger", MAX_LAPS, ["Pong"])
    sent = runner.args_of(UPDATE)[-1]
    rendered = templates.render("catch_up/prompts/update-book.md", sent, Path(okf_book.__file__).parent)
    assert "The operator answered" in rendered
    assert "The ledger closes on the business day, in UTC." in rendered
    assert runner.chains[-1][1] == "catchup:ledger"
    again = flow.stamp(service="ledger", lap=MAX_LAPS, added=["Pong"], ignored=[])
    assert isinstance(again, Await) and again.path == flow.run_dir / RED_GATE


def test_a_gate_that_could_not_judge_waits_and_judges_again_without_a_lap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, runner, _seen = stale_book(tmp_path, monkeypatch, DONE, check=3)

    step = flow.check(service="ledger", lap=1, added=[], ignored=[])

    assert isinstance(step, Await) and step.state == "check"
    assert step.params == {"service": "ledger", "lap": 1, "added": [], "ignored": []}
    assert runner.total == 0


def test_a_blocked_owner_parks_on_the_operator_gate_and_its_answer_reaches_the_next_turn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    blocked: dict[str, Reply] = {UPDATE: lambda _args: {"done": "", "blocked": "which clock does the ledger close on", "added": []}}
    flow, runner, _seen = stale_book(tmp_path, monkeypatch, blocked)

    step = walk(flow, flow.books(), "write")
    parked = advance(flow, step)

    assert isinstance(parked, Await) and parked.state == "heard"
    assert parked.path == flow.run_dir / BLOCKED_GATE
    assert "which clock does the ledger close on" in parked.questions
    question = cast("str", parked.params["question"])
    parked.path.write_text(f"{question}\n\nThe business day, in UTC.\n", encoding="utf-8")
    heard = advance(flow, parked)
    advance(flow, heard)
    assert heard.state == "write" and heard.params["service"] == "ledger"
    assert "The business day, in UTC." in cast("str", runner.args_of(UPDATE)[-1]["gate"])


def test_a_stale_report_that_cannot_be_read_asks_the_operator_and_the_answer_reads_it_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, runner, _env = build_flow(tmp_path)
    first = make_app(flow.root)
    seen = book_exits(monkeypatch, stale={"services.ledger": (4, "the app is not a git checkout\n")})

    step = flow.fill()

    assert isinstance(step, Await) and step.state == "fill"
    assert step.path == flow.run_dir / STALE_GATE
    assert "the app is not a git checkout" in step.questions
    assert flow.work_list.items("book") == []
    said = stale_printed(first, {"Ping": "ledger/ping.py"}, [])
    book_exits(monkeypatch, stale={"services.ledger": (1, said)})
    again = flow.fill()
    assert isinstance(again, Continue) and again.state == "books"
    assert [item.id for item in flow.work_list.items("book")] == ["ledger"]
    assert runner.total == 0
    assert len(seen) == 1


def test_the_question_of_an_unreadable_stale_report_carries_the_exit_code_and_stderr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _runner, _env = build_flow(tmp_path)
    make_app(flow.root)
    book_exits(monkeypatch, stale={"services.ledger": (4, "", "fatal: not a git repository")})

    step = flow.fill()

    assert isinstance(step, Await)
    assert "exited 4" in step.questions
    assert "fatal: not a git repository" in step.questions
    assert "stale services.ledger" in step.questions


def test_the_summary_never_names_a_failed_book(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _runner, _seen = stale_book(tmp_path, monkeypatch, DONE, verified=1)
    walk(flow, flow.books(), "write")
    flow.stamp(service="ledger", lap=MAX_LAPS, added=[], ignored=[])

    done = summarized(flow)

    assert "failed" not in done.summary
    assert done.books == []
    assert "failed" not in BookOutcome.model_json_schema()["properties"]["verdict"]["enum"]


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
    done = dry_run_said(tmp_path, "catch_up")

    assert done.returncode == 0, done.stdout + done.stderr
    said = done.stdout + done.stderr
    assert "dry-run ok" in said
    assert "call   → commit_book_paths (dry-run)" in said
    assert "done   ← summarize" in said

def test_every_edge_of_the_catch_up_graph_has_a_reason() -> None:
    graph = state_graph(CatchUpBooks, workflow_dir=Path(okf_book.__file__).parent)

    bare = [(node.name, edge.target) for node in graph.states for edge in node.edges if not edge.reason]

    assert bare == []
    assert {"fill", "books", "take", "write", "check", "play", "stamp", "render", "commit", "summarize", "heard"} <= {node.name for node in graph.states}


def test_the_owner_prompt_names_code_a_served_request_runs_in_a_source_and_does_not_ignore_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, runner, _seen = stale_book(tmp_path, monkeypatch, DONE)
    install_book_skill(tmp_path / "home", monkeypatch)
    walk(flow, flow.books(), "write")
    flow.write(service="ledger", gate="", lap=1, added=[], ignored=[])
    rendered = templates.render("catch_up/prompts/update-book.md", runner.args_of(UPDATE)[0], Path(okf_book.__file__).parent)

    assert "runs when a route, screen or heard event of the book is served" in rendered
    assert "however pure" in rendered
    assert "holds no behaviour a user reaches" not in rendered
    assert "`ignored`" in rendered


def test_the_summary_of_a_caught_up_book_names_the_patterns_its_turns_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    replies: dict[str, Reply] = {UPDATE: lambda _args: {"done": "ok", "blocked": "", "added": [], "ignored": ["ledger/build.py", "ledger/tools/*"]}}
    flow, _runner, _seen = stale_book(tmp_path, monkeypatch, replies)

    step = walk(flow, flow.books(), "write")
    step = walk(flow, advance(flow, step), "books")
    walk(flow, step, "summarize")

    assert summarized(flow).summary == "ledger: caught up in 1 laps, 2 elements changed, 0 endpoints added, 2 files ignored: ledger/build.py, ledger/tools/*"


def test_the_summary_of_a_book_with_nothing_ignored_reads_as_before(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _runner, _seen = stale_book(tmp_path, monkeypatch, DONE)

    step = walk(flow, flow.books(), "write")
    step = walk(flow, advance(flow, step), "books")
    walk(flow, step, "summarize")

    assert summarized(flow).summary == "ledger: caught up in 1 laps, 2 elements changed, 0 endpoints added"
