"""The Activity tab's search: the turns whose transcript says a query, and the endpoint that answers it."""

from __future__ import annotations

from pathlib import Path

from litestar.testing import TestClient
from test_activity import BASE, SESSION, SLUG, _claude, _seed_run, _write
from test_run_clock import RUN, _DB

from groom import activity_search, store, turns
from groom import app as groom_app


def test_a_search_finds_the_turn_whose_transcript_says_the_query_with_its_line(
    tmp_path: Path,
) -> None:
    with _DB():
        _seed_run(tmp_path)
        found = activity_search.search(RUN, "BRINGING")
        none = activity_search.search(RUN, "pgbouncer")
        tool = activity_search.search(RUN, "make up")
    assert found["matches"] == [{"key": SLUG, "line": "Bringing the stack up."}]
    assert none["matches"] == []
    assert [one["key"] for one in tool["matches"]] == [SLUG]


def test_a_search_never_reads_a_turn_outside_its_run_and_an_empty_query_reads_nothing(
    tmp_path: Path,
) -> None:
    with _DB():
        _seed_run(tmp_path)
        other = activity_search.search("some-other-run", "Bringing")
        blank = activity_search.search(RUN, "   ")
    assert other["matches"] == []
    assert blank == {"run_id": RUN, "query": "", "matches": []}


def test_a_search_cuts_a_long_query_to_its_bound_and_lowercases_it(
    tmp_path: Path,
) -> None:
    with _DB():
        _seed_run(tmp_path)
        path = (
            turns.transcripts_root() / RUN / f"{SLUG}__{SESSION}" / "transcript.jsonl"
        )
        _write(path, [_claude(110, "assistant", "ab" * 120)])
        found = activity_search.search(RUN, "AB" * 250)
    assert found["query"] == "ab" * (activity_search.SEARCH_QUERY_CHARS // 2)
    assert [one["key"] for one in found["matches"]] == [SLUG]


def test_a_search_does_not_read_another_runs_transcripts_that_hold_the_word(
    tmp_path: Path,
) -> None:
    with _DB():
        _seed_run(tmp_path)
        other = turns.transcripts_root() / "other-run" / f"{SLUG}__{SESSION}"
        _write(
            other / "transcript.jsonl", [_claude(110, "assistant", "pgbouncer is down")]
        )
        store.insert_turns(
            [
                {
                    "run_id": "other-run",
                    "node": "qa-story",
                    "session_id": SESSION,
                    "generation": 1,
                    "seq": 2,
                    "ts": BASE + 100,
                    "path": f"other-run/{SLUG}__{SESSION}",
                }
            ]
        )
        mine = activity_search.search(RUN, "pgbouncer")
        theirs = activity_search.search("other-run", "pgbouncer")
    assert mine["matches"] == []
    assert theirs["matches"] == []


def test_a_search_line_is_cut_and_keeps_markup_as_plain_text(tmp_path: Path) -> None:
    with _DB():
        _seed_run(tmp_path)
        path = (
            turns.transcripts_root() / RUN / f"{SLUG}__{SESSION}" / "transcript.jsonl"
        )
        _write(
            path,
            [_claude(110, "assistant", "<img src=x onerror=alert(1)> " + "z" * 900)],
        )
        found = activity_search.search(RUN, "onerror")
    line = found["matches"][0]["line"]
    assert (
        "<img src=x onerror=alert(1)>" in line
        and len(line) <= activity_search.SEARCH_LINE_CHARS
    )


def test_an_unreadable_transcript_fails_the_search_and_the_endpoint_answers_503(
    tmp_path: Path, monkeypatch
) -> None:
    import pytest

    with _DB():
        _seed_run(tmp_path)
        (
            turns.transcripts_root() / RUN / f"{SLUG}__{SESSION}" / "transcript.jsonl"
        ).unlink()
        with pytest.raises(activity_search.SearchFailed):
            activity_search.search(RUN, "x", pending=True)
        real = activity_search.search

        def failing(run_id, query, live=None, pending=False):
            return real(run_id, query, live, True)

        monkeypatch.setattr(activity_search, "search", failing)
        with TestClient(app=groom_app.create_app()) as client:
            answered = client.get(f"/api/run/{RUN}/search", params={"q": "Bringing"})
    assert answered.status_code == 503
