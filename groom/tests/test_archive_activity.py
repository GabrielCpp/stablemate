"""The Activity of an archived run, read from its frozen file on the archive pool."""
from __future__ import annotations

import shutil
import sqlite3
import threading
import time
from pathlib import Path
from unittest.mock import patch

from litestar.testing import TestClient
from test_activity_tab_dynamic import FIRST, SECOND, SESSION, _record, _turn_attrs
from test_history import seed
from test_run_clock import _DB, span

from groom import activity, archive, pools, state, store, turns
from groom import app as groom_app

DAY = 86400.0
RUN = "run-act"


def _archived_turns(run: str = RUN, now: float | None = None, metrics: int = 0) -> Path:
    now = now or time.time()
    base = now - 60 * DAY
    pre = f"{run}-"
    given = [
        span(pre + "a1", pre + "t", pre + "n", "dev", "agent_turn", base + 10, 120, _turn_attrs(FIRST, "Documented the flow.", 1.25, 3100), 1, run),
        span(pre + "a2", pre + "t", pre + "n", "dev", "agent_turn", base + 140, 120, _turn_attrs(SECOND, "Stack up.", 2.0, 2100), 1, run),
    ]
    seed(run, base, costs=(), extra=given)
    store.insert_metrics([
        {"run_id": run, "name": "workhorse.gas", "ts": base + 30 + number, "value": float(number), "attrs": {"node": "dev"}}
        for number in range(metrics)
    ])
    rows = []
    for slug, seq, start in ((FIRST, 1, base + 10), (SECOND, 2, base + 140)):
        session = f"{SESSION}-{slug[:9]}"
        root = turns.transcripts_root() / run / f"{slug}__{session}"
        root.mkdir(parents=True, exist_ok=True)
        (root / "transcript.jsonl").write_text(_record(start + 1, "assistant", f"Said {slug} about the reset email"))
        rows.append({"run_id": run, "node": slug.split("-", 2)[2], "session_id": session, "generation": 1, "seq": seq, "ts": start, "path": f"{run}/{slug}__{session}"})
    store.insert_turns(rows)
    destination, _ = archive.archive_run(store.run_bounds()[run], now)
    assert destination is not None
    state.RUNS.clear()
    return destination


def _client() -> TestClient:
    return TestClient(app=groom_app.create_app())


def test_the_archive_activity_routes_resolve_an_archive_by_its_exact_id_and_nothing_else() -> None:
    now = time.time()
    with _DB():
        _archived_turns(now=now)
        seed("run-live", now - 3600)
        with _client() as client:
            found = [client.get(f"/api/archive/{RUN}/{tail}").status_code for tail in ("activity", f"activity/{FIRST}", "records", "search?q=said", "entry/step:none")]
            refused = [
                client.get(f"/api/archive/{who}/{tail}").status_code
                for who in ("run-ac", "nope", "run-live", "..%2F")
                for tail in ("activity", f"activity/{FIRST}", "records", "search?q=said", "entry/step:none")
            ]
    assert found == [200, 200, 200, 200, 404]
    assert set(refused) == {404}


def test_an_archived_run_lists_its_turns_and_reads_one_from_the_records_the_archive_kept() -> None:
    with _DB():
        _archived_turns()
        with _client() as client:
            timeline = client.get(f"/api/archive/{RUN}/activity").json()
            turn = client.get(f"/api/archive/{RUN}/activity/{SECOND}").json()
    assert [row["slug"] for row in timeline["rows"]] == [FIRST, SECOND]
    assert turn["entries"][0]["text"] == f"Said {SECOND} about the reset email"


def test_an_archived_turn_whose_record_is_gone_reads_as_no_record_and_an_unreadable_one_answers_unavailable() -> None:
    def unreadable(*args, **kwargs):
        raise activity.TurnUnreadable(SECOND)

    with _DB():
        folder = _archived_turns()
        shutil.rmtree(next(folder.glob(f"{SECOND}__*")))
        with _client() as client:
            timeline = client.get(f"/api/archive/{RUN}/activity")
            gone = client.get(f"/api/archive/{RUN}/activity/{SECOND}")
            kept = client.get(f"/api/archive/{RUN}/activity/{FIRST}")
            with patch.object(activity, "turn", unreadable):
                broken = client.get(f"/api/archive/{RUN}/activity/{SECOND}")
    assert [row["slug"] for row in timeline.json()["rows"]] == [FIRST, SECOND]
    assert gone.status_code == 200 and gone.json()["head"]["matched"] is False
    assert kept.json()["head"]["matched"] is True
    assert broken.status_code == 503


def test_archive_records_list_newest_first_hide_metric_samples_until_asked_and_page_older_ones() -> None:
    with _DB():
        _archived_turns(metrics=4)
        with _client() as client:
            hidden = client.get(f"/api/archive/{RUN}/records").json()
            shown = client.get(f"/api/archive/{RUN}/records?metrics=1").json()
            first = client.get(f"/api/archive/{RUN}/records?limit=2").json()
            older = client.get(f"/api/archive/{RUN}/records?limit=2&before={first['next']}").json()
            bad = client.get(f"/api/archive/{RUN}/records?before=nonsense")
    stamps = [one["ts"] for one in hidden["records"]]
    assert stamps == sorted(stamps, reverse=True)
    assert hidden["metric_samples"] == shown["metric_samples"] == 4
    assert {one["kind"] for one in hidden["records"]} == {"SPAN"}
    assert shown["total"] == hidden["total"] + 4
    assert [one["key"] for one in first["records"] + older["records"]] == [one["key"] for one in hidden["records"]][:4]
    assert bad.status_code == 400


def test_archive_search_matches_the_transcripts_of_an_archived_run() -> None:
    with _DB():
        _archived_turns()
        with _client() as client:
            found = client.get(f"/api/archive/{RUN}/search?q=reset+email").json()
            none = client.get(f"/api/archive/{RUN}/search?q=zebra").json()
    assert [one["key"] for one in found["matches"]] == [FIRST, SECOND]
    assert none["matches"] == []


def test_an_archive_whose_files_are_gone_answers_gone_on_every_activity_route() -> None:
    with _DB():
        folder = _archived_turns()
        (folder / archive.TELEMETRY_FILE).unlink()
        with _client() as client:
            answers = [client.get(f"/api/archive/{RUN}/{tail}").status_code for tail in ("activity", f"activity/{FIRST}", "records", "search?q=said", "entry/step:none")]
    assert set(answers) == {410}


def test_every_archive_activity_route_reads_on_the_archive_pool_and_never_on_the_query_pool() -> None:
    tails = ("activity", f"activity/{FIRST}", "records", "search?q=said", "entry/step:none")
    with _DB():
        _archived_turns()
        with (
            patch.object(pools.ARCHIVE, "run", wraps=pools.ARCHIVE.run) as archive_run,
            patch.object(pools.QUERY, "run", wraps=pools.QUERY.run) as query_run,
            _client() as client,
        ):
            answers = [client.get(f"/api/archive/{RUN}/{tail}").status_code for tail in tails]
    assert answers == [200, 200, 200, 200, 404]
    assert [call.args[0] for call in archive_run.call_args_list] == [groom_app._archive_read] * len(tails)
    assert groom_app._archive_read not in [call.args[0] for call in query_run.call_args_list]


def test_an_archive_read_enters_the_archive_inside_the_pooled_thread_and_drops_an_unreadable_index() -> None:
    seen: list[tuple[str, bool]] = []

    def reads(*args, **kwargs):
        entered = store.read_connection() is not store.STORE.read_connection()
        seen.append((threading.current_thread().name, entered))
        raise sqlite3.DatabaseError("file is not a database")

    with _DB():
        folder = _archived_turns()
        with _client() as client:
            client.get(f"/api/archive/{RUN}/activity")
            built = (folder / archive.INDEX_FILE).exists()
            with patch.object(activity, "timeline", reads):
                failed = client.get(f"/api/archive/{RUN}/activity").status_code
        after = (folder / archive.INDEX_FILE).exists()
    assert built and not after
    assert failed == 500
    assert seen
    name, entered = seen[0]
    assert name.startswith(f"groom-{pools.ARCHIVE.name}")
    assert entered
