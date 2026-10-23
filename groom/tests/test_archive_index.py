"""An archived run answers cost, loops and profile through a derived SQLite index."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

import pytest

from groom import archive, store

RUN = "run-9"
START = 1_000_000.0


class _DB:
    def __enter__(self) -> _DB:
        self._dir = tempfile.TemporaryDirectory()
        self._prev = os.environ.get("GROOM_DB")
        os.environ["GROOM_DB"] = str(Path(self._dir.name) / "groom.db")
        store.reset()
        return self

    def __exit__(self, *exc: object) -> None:
        store.reset()
        if self._prev is None:
            os.environ.pop("GROOM_DB", None)
        else:
            os.environ["GROOM_DB"] = self._prev
        self._dir.cleanup()


def _span(
    span_id: str,
    name: str,
    start: float,
    end: float,
    node: str,
    attrs: dict[str, Any],
    parent: str = "",
    run: str = RUN,
) -> dict[str, Any]:
    return {
        "span_id": span_id,
        "trace_id": "aa" * 16,
        "parent_id": parent,
        "run_id": run,
        "workflow": "coder",
        "repo": "example-org/api-service",
        "branch": "main",
        "node": node,
        "name": name,
        "run_dir": "/home/me/repo/.agents/runs/run-9",
        "start_ts": start,
        "end_ts": end,
        "status": "ok",
        "attrs": attrs,
        "resume_generation": 1,
    }


def _seed(run: str = RUN) -> None:
    spans = []
    for index, work in enumerate(("s1", "s1", "s1", "s2")):
        begin = START + index * 100
        spans.append(
            _span(
                f"visit-{index}", "node:plan-qa", begin, begin + 90, "plan-qa",
                {"work_id": work, "workhorse.out.status": "revise" if index % 2 else "ok"},
                run=run,
            )
        )
        spans.append(
            _span(
                f"turn-{index}", "agent_turn", begin + 5, begin + 80, "plan-qa",
                {
                    "work_id": work,
                    "backend": "claude",
                    "total_cost_usd": 1.5 + index,
                    "usage.output_tokens": 100 + index,
                    "model": "claude-sonnet-4",
                },
                parent=f"visit-{index}",
                run=run,
            )
        )
    store.insert_spans(spans)
    store.insert_logs([
        {
            "run_id": run, "ts": START + 3, "severity": "INFO", "body": "hello",
            "node": "plan-qa", "workflow": "coder",
            "run_dir": "/home/me/repo/.agents/runs/run-9",
        }
    ])
    store.insert_metrics([
        {"run_id": run, "name": "workhorse.gas", "ts": START + 4, "value": 7.0,
         "attrs": {"workhorse.node": "plan-qa"}},
        {"run_id": run, "name": "workhorse.gas.capacity", "ts": START + 4, "value": 10.0,
         "attrs": {}},
    ])


def _archive(run: str = RUN) -> Path:
    bounds = store.run_bounds()[run]
    destination, _ = archive.archive_run(bounds, now=START + 10_000)
    assert destination is not None
    return destination


def _answers(run: str = RUN) -> tuple[Any, Any, Any]:
    return (
        store.node_costs(run=run),
        store.loop_convergence(run=run, min_work_items=1),
        store.run_profile(run),
    )


def test_an_archived_run_answers_cost_loops_and_profile_from_its_index() -> None:
    with _DB():
        _seed()
        captured = _answers()
        assert captured[0] and captured[1] and captured[2]
        _archive()
        assert store.node_costs(run=RUN) == []
        assert store.loop_convergence(run=RUN, min_work_items=1) == []
        assert store.run_profile(RUN) is None
        with archive.run_source(RUN):
            assert _answers() == captured
        assert store.node_costs(run=RUN) == []


def test_the_index_is_reused_until_the_jsonl_is_newer() -> None:
    with _DB():
        _seed()
        folder = _archive()
        index = archive.build_index(folder)
        assert index == folder / archive.INDEX_FILE
        source = folder / archive.TELEMETRY_FILE
        os.utime(source, (START, START))
        os.utime(index, (START + 50, START + 50))
        marker = sqlite3.connect(index)
        marker.execute("DELETE FROM logs")
        marker.commit()
        marker.close()
        os.utime(index, (START + 50, START + 50))
        archive.build_index(folder)
        check = sqlite3.connect(index)
        assert check.execute("SELECT COUNT(*) FROM logs").fetchone()[0] == 0
        check.close()
        os.utime(source, (START + 100, START + 100))
        archive.build_index(folder)
        check = sqlite3.connect(index)
        assert check.execute("SELECT COUNT(*) FROM logs").fetchone()[0] == 1
        check.close()
        assert not (folder / (archive.INDEX_FILE + ".tmp")).exists()


def test_run_source_leaves_reads_on_the_store_while_the_run_has_rows() -> None:
    with _DB():
        _seed()
        folder = _archive()
        _seed()
        with archive.run_source(RUN):
            assert store.node_costs(run=RUN)
        assert not (folder / archive.INDEX_FILE).exists()


def test_run_source_without_an_archive_changes_nothing() -> None:
    with _DB():
        _seed("other")
        with archive.run_source("missing"), archive.run_source(""):
            assert store.node_costs(run="missing") == []
            assert store.node_costs(run="other")
        assert not (archive.archives_root() / "missing").exists()


def test_archive_dir_prefers_the_exact_name_then_a_derived_one(tmp_path: Path) -> None:
    with _DB():
        root = archive.archives_root()
        (root / "r1-deadbeef").mkdir(parents=True)
        (root / "r1-deadbeef" / archive.TELEMETRY_FILE).write_text("{}\n")
        assert archive.archive_dir("r1") == root / "r1-deadbeef"
        (root / "r1").mkdir()
        (root / "r1" / archive.TELEMETRY_FILE).write_text("{}\n")
        assert archive.archive_dir("r1") == root / "r1"
        assert archive.archive_dir("nope") is None


def test_reading_from_restores_the_previous_source_even_when_the_body_raises(
    tmp_path: Path,
) -> None:
    with _DB():
        _seed("live")
        other = tmp_path / "other.db"
        conn = sqlite3.connect(other)
        conn.row_factory = sqlite3.Row
        store.prepare(conn)
        conn.close()
        assert store.node_costs(run="live")
        with store.reading_from(other):
            assert store.node_costs(run="live") == []
        assert store.node_costs(run="live")
        with pytest.raises(RuntimeError), store.reading_from(other):
            raise RuntimeError("boom")
        assert store.node_costs(run="live")
