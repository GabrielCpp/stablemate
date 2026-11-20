"""A book whose app is current but whose format moved is filed, sent the format's commits, played whole, marked and committed."""
from __future__ import annotations

from pathlib import Path

import pytest
from okf_book.catch_up.flows import UPDATE, advance, book_exits, build_flow, make_app, stale_printed, summarized, walk
from okf_book.support import Reply, ScriptedRunner, commit_at, git, install_book_skill, skill_history
from workhorse import templates
from workhorse.pyflow import Await, Continue

from workhorse_workflows import okf_book
from workhorse_workflows.okf_book.catch_up.flow import FORMAT_GATE, CatchUpBooks
from workhorse_workflows.okf_book.catch_up.models import BookOutcome
from workhorse_workflows.okf_book.shared.book_commits import format_book_commit_subject
from workhorse_workflows.okf_book.shared.book_format import MARK_FILE

APPLIED = "{short} applied: the credential renews itself"
NOT_APPLICABLE = "{short} not applicable: the book has no credentials"


def lines_for(shas: list[str]) -> list[str]:
    return [APPLIED.format(short=shas[1][:7]), NOT_APPLICABLE.format(short=shas[2][:7])]


def behind_book(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, replies: dict[str, Reply] | None = None, history: str = "") -> tuple[CatchUpBooks, ScriptedRunner, list[str], list[list[str]]]:
    """A flow whose ledger book was committed between the first and the second of three instructions commits, with the app current."""
    shas = skill_history(tmp_path / "history", monkeypatch)
    flow, runner, _env = build_flow(tmp_path, replies, history=history or str(tmp_path / "history"))
    make_app(flow.root)
    git(flow.root, "add", "services")
    commit_at(flow.root, "docs(ledger): write the ledger book", "2026-11-02T12:00:00+00:00", monkeypatch)
    seen = book_exits(monkeypatch)
    return flow, runner, shas, seen


def test_a_book_with_a_current_app_and_a_format_behind_is_filed_and_sent_the_formats_commits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_the_whole_book_is_played_marked_at_the_head_and_committed_with_the_format_subject(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    replies: dict[str, Reply] = {UPDATE: lambda _args: {"done": "moved", "blocked": ""}}
    flow, _runner, shas, seen = behind_book(tmp_path, monkeypatch, replies)
    install_book_skill(tmp_path / "home", monkeypatch)

    step = walk(flow, flow.fill(), "write")
    step = walk(flow, advance(flow, step), "books")

    run = next(argv for argv in seen if argv[3:5] == ["run", "services.ledger"])
    assert run[5:] == ["--out", str(flow.run_dir / "book-run/services.ledger"), "--copy", "evening", "--fresh-data"]
    assert "verified" not in [argv[3] for argv in seen if argv[1] != "-c"]
    assert (flow.root / "services/ledger" / MARK_FILE).read_text(encoding="utf-8") == f"{shas[2]}\n"
    assert git(flow.root, "log", "-1", "--format=%s") == "docs(ledger): move the ledger book onto the current book format\n"
    assert git(flow.root, "show", "--name-only", "--format=", "HEAD").split() == ["services/ledger/FORMAT"]
    assert isinstance(step, Continue)


def test_the_summary_counts_the_changes_the_owner_applied_and_those_that_did_not_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, runner, shas, _seen = behind_book(tmp_path, monkeypatch)
    flow.fill()
    runner.replies[UPDATE] = lambda _args: {"done": "moved", "blocked": "", "format": lines_for(shas)}

    step = walk(flow, flow.books(), "write")
    walk(flow, advance(flow, step), "books")
    walk(flow, flow.books(), "summarize")

    done = summarized(flow)
    assert done.summary == "ledger: moved onto the format, 1 changes applied, 1 not applicable"
    assert done.books[0].format == lines_for(shas)
    assert done.books[0].moved


def test_a_book_stale_in_the_app_and_behind_on_the_format_keeps_the_app_subject_and_plays_whole(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    replies: dict[str, Reply] = {UPDATE: lambda _args: {"done": "moved", "blocked": "", "format": []}}
    flow, _runner, shas, _seen = behind_book(tmp_path, monkeypatch, replies)
    first = git(flow.root, "rev-list", "--max-parents=0", "HEAD").strip()
    said = stale_printed(first, {"Ping": "ledger/ping.py"}, [])
    seen = book_exits(monkeypatch, stale={"services.ledger": (1, said)}, calls={"services.ledger": ["Ping"]})
    flow.fill()

    step = walk(flow, flow.books(), "write")
    walk(flow, advance(flow, step), "books")
    walk(flow, flow.books(), "summarize")

    run = next(argv for argv in seen if argv[3:5] == ["run", "services.ledger"])
    assert "--only" not in run
    assert [argv[3] for argv in seen if argv[3] == "verified"] == ["verified"]
    assert git(flow.root, "log", "-1", "--format=%s") == "docs(ledger): catch the ledger book up with the app\n"
    assert (flow.root / "services/ledger" / MARK_FILE).read_text(encoding="utf-8") == f"{shas[2]}\n"
    assert summarized(flow).summary == "ledger: caught up in 1 laps, 1 elements changed, 0 endpoints added, moved onto the format, 0 changes applied, 0 not applicable"


def test_a_book_current_on_both_axes_is_recorded_current_and_gets_no_turn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    flow, runner, shas, seen = behind_book(tmp_path, monkeypatch)
    (flow.root / "services/ledger" / MARK_FILE).write_text(f"{shas[2]}\n", encoding="utf-8")

    flow.fill()
    step = flow.books()
    done = summarized(flow)

    assert isinstance(step, Continue) and step.state == "summarize"
    assert runner.total == 0
    assert [argv[3] for argv in seen] == ["stale"]
    assert done.books == [BookOutcome(service="ledger", verdict="current")]


def test_a_history_that_cannot_be_read_waits_on_the_operator_and_the_answer_reads_it_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "nowhere").mkdir()
    flow, _runner, shas, _seen = behind_book(tmp_path, monkeypatch, history=str(tmp_path / "nowhere"))

    step = flow.fill()

    assert isinstance(step, Await) and step.state == "fill"
    assert step.path == flow.run_dir / FORMAT_GATE
    assert "rev-list" in step.questions and "ledger" in step.questions
    assert flow.work_list.items("book") == []
    flow.format_history = str(tmp_path / "history")
    again = flow.fill()
    assert isinstance(again, Continue) and again.state == "books"
    assert [item.id for item in flow.work_list.items("book")] == ["ledger"]
    assert shas


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
