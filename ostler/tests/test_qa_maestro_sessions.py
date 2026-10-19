"""A Maestro session record whose CLI died is retired, and one that still beats is kept."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from ostler.qa.drivers import LocalLauncher, PythonDriver
from ostler.qa.maestro_sessions import retire_dead_sessions
from ostler.qa.session import QaSession

from conftest import write


def _put(store: Path, text: str) -> None:
    scratch = store.with_name("sessions.beat")
    scratch.write_text(text, encoding="utf-8")
    os.replace(scratch, store)


def _beat(store: Path, prefix: str, stop: threading.Event) -> None:
    stamp = 1_000
    while not stop.is_set():
        stamp += 1
        _put(store, f"{prefix}ANDROID_live={stamp}")
        time.sleep(0.1)


def test_a_missing_store_retires_nothing_and_stays_missing(tmp_path: Path) -> None:
    store = tmp_path / "sessions"
    assert retire_dead_sessions(store, wait=0.5) == []
    assert not store.exists()


def test_a_record_that_stops_beating_is_dropped_and_the_live_one_kept(tmp_path: Path) -> None:
    store = tmp_path / "sessions"
    store.write_text("ANDROID_dead=1792414344023\n\nbroken line\nANDROID_live=1000", encoding="utf-8")
    stop = threading.Event()
    beater = threading.Thread(target=_beat, args=(store, "ANDROID_dead=1792414344023\n", stop), daemon=True)
    beater.start()
    try:
        assert retire_dead_sessions(store, wait=1.0) == ["ANDROID_dead"]
    finally:
        stop.set()
        beater.join()
    lines = store.read_text(encoding="utf-8").split("\n")
    assert len(lines) == 1
    assert lines[0].startswith("ANDROID_live=")
    assert not store.read_text(encoding="utf-8").endswith("\n")


def test_a_record_that_keeps_beating_is_left_alone_before_the_wait_ends(tmp_path: Path) -> None:
    store = tmp_path / "sessions"
    store.write_text("ANDROID_live=1000", encoding="utf-8")
    stop = threading.Event()
    beater = threading.Thread(target=_beat, args=(store, "", stop), daemon=True)
    beater.start()
    try:
        started = time.monotonic()
        assert retire_dead_sessions(store, wait=10.0) == []
        assert time.monotonic() - started < 5.0
    finally:
        stop.set()
        beater.join()
    assert store.read_text(encoding="utf-8").startswith("ANDROID_live=")


PLAN = '''\
from ostler_qa import Qa, plan, scenario, target
import os, time

plan(run_id="qa-sessions", story="sessions")

api = target("api")


@scenario(target=api, mechanism="live", covers=["ac:1"])
def leaves_a_session_record(qa: Qa) -> None:
    """Writes a Maestro-style session record, then outlives its timeout without touching it again."""
    with open(os.environ["SESSION_STORE"], "w") as handle:
        handle.write("ANDROID_orphan=1792414344023")
    time.sleep(60)
'''


def test_the_launcher_retires_the_record_a_killed_scenario_left(repo: Path) -> None:
    module = repo / "qa_plan.py"
    write(module, PLAN)
    spec = repo / "docs/specs/story-1"
    spec.mkdir(parents=True, exist_ok=True)
    store = repo / "sessions"
    session = QaSession.create(spec, "qa-sessions-1", "story-1", {})
    launcher = LocalLauncher(kill_grace=1.0, session_store=store)
    driver = PythonDriver(session, "api", {"driver": "python", "module": str(module)}, root=repo, variables={}, launcher=launcher)
    context = {"root": str(repo), "spec_dir": str(spec), "qa_dir": str(session.qa_dir)}
    os.environ["SESSION_STORE"] = str(store)
    try:
        _records, _output, _code, timed_out = launcher.execute(driver, "leaves-a-session-record", 1.0, context)
    finally:
        del os.environ["SESSION_STORE"]
    assert timed_out
    assert store.read_text(encoding="utf-8") == ""
