"""A book whose app is current but whose check is red is filed for the format, sent the check's findings and the format's commits when they can be read, played by what its edits select, marked and committed."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest
from okf_book.catch_up.flows import UPDATE, advance, book_exits, build_flow, make_app, stale_printed, summarized, walk
from okf_book.support import Reply, ScriptedRunner, commit_at, git, install_book_skill, skill_history
from workhorse import templates
from workhorse.pyflow import Await, Continue

from workhorse_workflows import okf_book
from workhorse_workflows.okf_book.catch_up.flow import CatchUpBooks
from workhorse_workflows.okf_book.catch_up.models import BookOutcome
from workhorse_workflows.okf_book.shared.book_commits import format_book_commit_subject
from workhorse_workflows.okf_book.shared import book_format
from workhorse_workflows.okf_book.shared.book_format import MARK_FILE

APPLIED = "{short} applied: the credential renews itself"
NOT_APPLICABLE = "{short} not applicable: the book has no credentials"
RED = "CHECK  sources: Ping names no source\nCHECK  decisions: the Entry screen names no decision\nNOTE  index: differs\ncheck: 2 findings, 3 notes\n"
GREEN = "check: 0 findings, 1 note\n"
PARTIAL: dict[str, object] = {"plan": "partial", "whole": False, "reason": "", "only": ["Ping", "Pong"], "by_journey": ["Open an account"]}


def lines_for(shas: list[str]) -> list[str]:
    return [APPLIED.format(short=shas[1][:7]), NOT_APPLICABLE.format(short=shas[2][:7])]


def behind_book(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replies: dict[str, Reply] | None = None,
    history: str = "",
    plan: dict[str, object] | None = None,
) -> tuple[CatchUpBooks, ScriptedRunner, list[str], list[list[str]]]:
    """A flow whose ledger book was committed between the first and the second of three instructions commits, with the app current and the check red until the owner's first lap."""
    shas = skill_history(tmp_path / "history", monkeypatch)
    flow, runner, _env = build_flow(tmp_path, replies, history=history or str(tmp_path / "history"))
    make_app(flow.root)
    git(flow.root, "add", "services")
    commit_at(flow.root, "docs(ledger): write the ledger book", "2026-11-02T12:00:00+00:00", monkeypatch)
    seen = book_exits(monkeypatch, checks={"services.ledger": [(1, RED), (0, GREEN)]}, plans={"services.ledger": (0, plan or PARTIAL)})
    return flow, runner, shas, seen


def played(seen: list[list[str]]) -> list[list[str]]:
    return [argv for argv in seen if argv[3] == "run"]


def test_a_book_with_nothing_stale_and_a_red_check_is_filed_and_sent_the_findings_and_the_formats_commits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    replies: dict[str, Reply] = {}
    flow, runner, shas, _seen = behind_book(tmp_path, monkeypatch, replies)
    install_book_skill(tmp_path / "home", monkeypatch)

    step = flow.fill()
    taken = walk(flow, step, "write")
    runner.replies[UPDATE] = lambda _args: {"done": "moved", "blocked": "", "format": lines_for(shas)}
    advance(flow, taken)

    sent = runner.args_of(UPDATE)[0]
    rendered = templates.render("catch_up/prompts/update-book.md", sent, Path(okf_book.__file__).parent)
    assert [item.id for item in flow.work_list.items("book")] == ["ledger"]
    assert f"- `{shas[1][:7]}` docs(base-library): teach two" in rendered
    assert f"- `{shas[2][:7]}` docs(base-library): teach three" in rendered
    assert "+three" in rendered
    assert "The book format changed since this book was last judged against it." in rendered
    assert "The book was last verified against the commit below" not in rendered
    assert "--only" not in rendered
    assert "The check of this book reports these findings." in rendered
    assert "never invent a statement to silence a finding" in rendered
    assert "- sources: Ping names no source" in rendered
    assert "- decisions: the Entry screen names no decision" in rendered
    assert "`services.ledger`, 2 findings:" in rendered


def test_with_no_checkout_the_run_does_not_gate_logs_the_line_and_sends_the_findings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    flow, runner, _shas, _seen = behind_book(tmp_path, monkeypatch, {UPDATE: lambda _args: {"done": "moved", "blocked": ""}})
    monkeypatch.setattr(book_format, "history_repo", lambda: None)
    flow.format_history = ""
    install_book_skill(tmp_path / "home", monkeypatch)
    caplog.set_level(logging.INFO)

    step = flow.fill()
    walk(flow, step, "write")
    flow.write(service="ledger", gate="", lap=1, added=[], ignored=[])

    rendered = templates.render("catch_up/prompts/update-book.md", runner.args_of(UPDATE)[0], Path(okf_book.__file__).parent)
    assert isinstance(step, Continue) and step.state == "books"
    assert any("the format history was not available" in line and "the check's findings are the work list" in line for line in caplog.messages)
    assert "- sources: Ping names no source" in rendered
    assert "The book format changed since this book was last judged against it." not in rendered


def test_a_history_that_cannot_be_read_does_not_gate_and_writes_no_mark(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    (tmp_path / "nowhere").mkdir()
    flow, _runner, _shas, _seen = behind_book(tmp_path, monkeypatch, {UPDATE: lambda _args: {"done": "moved", "blocked": ""}}, history=str(tmp_path / "nowhere"))
    install_book_skill(tmp_path / "home", monkeypatch)
    caplog.set_level(logging.INFO)

    step = walk(flow, flow.fill(), "write")
    walk(flow, advance(flow, step), "books")

    assert any("the format history was not available" in line for line in caplog.messages)
    assert not (flow.root / "services/ledger" / MARK_FILE).exists()
    assert git(flow.root, "log", "-1", "--format=%s") == "docs(ledger): write the ledger book\n"
    assert not any(path.name.startswith("catch-up-format") for path in flow.run_dir.iterdir())


def test_a_format_book_plays_the_calls_and_journeys_its_edits_select_and_never_a_whole_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    replies: dict[str, Reply] = {UPDATE: lambda _args: {"done": "moved", "blocked": ""}}
    flow, _runner, shas, seen = behind_book(tmp_path, monkeypatch, replies)
    install_book_skill(tmp_path / "home", monkeypatch)
    head = git(flow.root, "rev-parse", "HEAD").strip()

    step = walk(flow, flow.fill(), "write")
    step = walk(flow, advance(flow, step), "books")

    affected = next(argv for argv in seen if argv[3] == "affected")
    assert affected[4:] == ["services.ledger", "--app", str(flow.code_root), "--since", head, "--out", str(flow.run_dir / "book-plan/services.ledger")]
    runs = played(seen)
    assert len(runs) == 2
    assert runs[0][5:] == ["--out", str(flow.run_dir / "book-run/services.ledger"), "--only", "Ping,Pong", "--copy", "evening", "--fresh-data"]
    assert runs[1][5:] == ["--out", str(flow.run_dir / "book-run/services.ledger.journeys"), "--partial", "--journey", "Open an account", "--copy", "evening"]
    assert all("--only" in argv or "--journey" in argv for argv in runs)
    assert "verified" not in [argv[3] for argv in seen if argv[1] != "-c"]
    assert (flow.root / "services/ledger" / MARK_FILE).read_text(encoding="utf-8") == f"{shas[2]}\n"
    assert git(flow.root, "log", "-1", "--format=%s") == "docs(ledger): move the ledger book onto the current book format\n"
    assert git(flow.root, "show", "--name-only", "--format=", "HEAD").split() == ["services/ledger/FORMAT"]
    assert isinstance(step, Continue)


def test_a_whole_plan_plays_only_what_it_names_and_records_the_reason_as_owed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan: dict[str, object] = {"plan": "whole", "whole": True, "reason": "a shared book file changed: services/shared/names.py", "only": [], "by_journey": ["Open an account"]}
    flow, _runner, _shas, seen = behind_book(tmp_path, monkeypatch, {UPDATE: lambda _args: {"done": "moved", "blocked": ""}}, plan=plan)
    install_book_skill(tmp_path / "home", monkeypatch)

    flow.fill()
    step = walk(flow, flow.books(), "write")
    walk(flow, advance(flow, step), "books")
    walk(flow, flow.books(), "summarize")

    runs = played(seen)
    assert len(runs) == 1
    assert runs[0][5:] == ["--out", str(flow.run_dir / "book-run/services.ledger"), "--partial", "--journey", "Open an account", "--copy", "evening", "--fresh-data"]
    done = summarized(flow)
    assert done.books[0].move is not None
    assert done.books[0].move.owed == "a shared book file changed: services/shared/names.py"
    assert done.summary.endswith("owed to a whole play: a shared book file changed: services/shared/names.py")


def test_a_plan_that_selects_nothing_plays_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan: dict[str, object] = {"plan": "empty", "whole": False, "reason": "", "only": [], "by_journey": []}
    flow, _runner, _shas, seen = behind_book(tmp_path, monkeypatch, {UPDATE: lambda _args: {"done": "moved", "blocked": ""}}, plan=plan)
    install_book_skill(tmp_path / "home", monkeypatch)

    step = walk(flow, flow.fill(), "write")
    walk(flow, advance(flow, step), "books")
    walk(flow, flow.books(), "summarize")

    assert played(seen) == []
    assert summarized(flow).summary == "ledger: moved onto the format in 1 laps, check 2 findings to 0, notes 3 to 1, played nothing"


def test_a_plan_that_cannot_be_read_waits_on_the_environment_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _runner, _shas, seen = behind_book(tmp_path, monkeypatch, {UPDATE: lambda _args: {"done": "moved", "blocked": ""}})
    seen.clear()
    book_exits(monkeypatch, checks={"services.ledger": [(1, RED), (0, GREEN)]}, plans={"services.ledger": (2, {})})
    install_book_skill(tmp_path / "home", monkeypatch)

    step = walk(flow, flow.fill(), "write")
    waiting = walk(flow, advance(flow, step), "play")
    waiting = advance(flow, waiting)

    assert isinstance(waiting, Await) and waiting.state == "play"
    assert "affected" in waiting.questions


def test_the_outcome_line_carries_the_check_before_and_after_the_play_and_what_the_owner_applied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, runner, shas, _seen = behind_book(tmp_path, monkeypatch)
    flow.fill()
    runner.replies[UPDATE] = lambda _args: {"done": "moved", "blocked": "", "format": lines_for(shas)}

    step = walk(flow, flow.books(), "write")
    walk(flow, advance(flow, step), "books")
    walk(flow, flow.books(), "summarize")

    done = summarized(flow)
    assert done.summary == "ledger: moved onto the format in 1 laps, check 2 findings to 0, notes 3 to 1, played 2 calls and 1 journeys green, 1 changes applied, 1 not applicable"
    assert done.books[0].format == lines_for(shas)
    assert done.books[0].moved


def test_a_book_stale_in_the_app_and_behind_on_the_format_keeps_the_app_subject_and_plays_its_changed_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    replies: dict[str, Reply] = {UPDATE: lambda _args: {"done": "moved", "blocked": "", "format": []}}
    flow, _runner, shas, _seen = behind_book(tmp_path, monkeypatch, replies)
    first = git(flow.root, "rev-list", "--max-parents=0", "HEAD").strip()
    said = stale_printed(first, {"Ping": "ledger/ping.py"}, [])
    seen = book_exits(monkeypatch, stale={"services.ledger": (1, said)}, calls={"services.ledger": ["Ping"]})
    flow.fill()
    assert "check" not in [argv[3] for argv in seen]

    step = walk(flow, flow.books(), "write")
    walk(flow, advance(flow, step), "books")
    walk(flow, flow.books(), "summarize")

    run = next(argv for argv in seen if argv[3:5] == ["run", "services.ledger"])
    assert run[5:] == ["--out", str(flow.run_dir / "book-run/services.ledger"), "--only", "Ping", "--copy", "evening"]
    assert [argv[3] for argv in seen if argv[3] == "verified"] == ["verified"]
    assert git(flow.root, "log", "-1", "--format=%s") == "docs(ledger): catch the ledger book up with the app\n"
    assert (flow.root / "services/ledger" / MARK_FILE).read_text(encoding="utf-8") == f"{shas[2]}\n"
    assert summarized(flow).summary == "ledger: caught up in 1 laps, 1 elements changed, 0 endpoints added, moved onto the format, 0 changes applied, 0 not applicable"


def test_a_book_current_on_both_axes_is_recorded_current_and_gets_no_turn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, runner, shas, _seen = behind_book(tmp_path, monkeypatch)
    seen = book_exits(monkeypatch, checks={"services.ledger": [(0, "")]})
    (flow.root / "services/ledger" / MARK_FILE).write_text(f"{shas[2]}\n", encoding="utf-8")

    flow.fill()
    step = flow.books()
    done = summarized(flow)

    assert isinstance(step, Continue) and step.state == "summarize"
    assert runner.total == 0
    assert [argv[3] for argv in seen] == ["stale", "check"]
    assert done.books == [BookOutcome(service="ledger", verdict="current")]


def test_a_book_with_no_verified_commit_stays_a_first_book_whatever_its_format(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, _runner, _shas, _seen = behind_book(tmp_path, monkeypatch)
    book_exits(monkeypatch, stale={"services.ledger": (2, "not verified: write the commit with 'verified'\n")})

    flow.fill()
    done = summarized(flow)

    assert done.books == [BookOutcome(service="ledger", verdict="first-book")]


def test_the_format_subject_names_the_book_once_where_its_name_is_long() -> None:
    assert format_book_commit_subject("ledger") == "docs(ledger): move the ledger book onto the current book format"
    long = format_book_commit_subject("a-long-service-name-x")
    assert long == "docs(a-long-service-name-x): move the book onto the current book format"
    longer = format_book_commit_subject("a-service-with-a-very-long-name")
    assert longer == "docs(a-service-with-a-very-long-name): adopt the current book format"
    assert len(long) <= 72 and len(longer) <= 72


def test_the_reply_schema_the_prompt_renders_names_the_format_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, runner, _shas, _seen = behind_book(tmp_path, monkeypatch, {UPDATE: lambda _args: {"done": "", "blocked": ""}})
    install_book_skill(tmp_path / "home", monkeypatch)
    walk(flow, flow.fill(), "write")
    flow.write(service="ledger", gate="", lap=1, added=[], ignored=[])

    rendered = templates.render("catch_up/prompts/update-book.md", runner.args_of(UPDATE)[0], Path(okf_book.__file__).parent)

    assert '"format"' in rendered and "not applicable" in rendered
