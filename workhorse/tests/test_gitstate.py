"""Tests for workhorse/gitstate.py and the repo state it stamps onto spans and logs.

The engine drives arbitrary workflows over arbitrary trees, so what is asserted here is
deliberately narrow: that an observation is *recorded*, and that a HEAD which moves
inside a span produces unequal endpoints. Nothing asserts the two should be equal — a
node that commits is doing its job, and telling that apart from a rebase is the reader's
problem, not the engine's.

The git half runs against a real temporary repository, which is the only way to test a
module whose entire purpose is what `git` says. It skips itself where git is absent
rather than failing: a machine with no git is one where this module correctly reports
nothing.

Run: ./.venv/bin/python tests/test_gitstate.py   (or via pytest)
"""
from __future__ import annotations

import importlib
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

gitstate = importlib.import_module("workhorse.gitstate")
logsetup = importlib.import_module("workhorse.logsetup")
otel = importlib.import_module("workhorse.otel")

HAVE_GIT = shutil.which("git") is not None


def _repo(path: Path) -> None:
    """A real repository with one commit, configured so committing needs no global."""
    for args in (
        ("init", "-q", "-b", "main"),
        ("config", "user.email", "test@example.com"),
        ("config", "user.name", "Test"),
    ):
        subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)
    _commit(path, "one")


def _commit(path: Path, text: str) -> str:
    (path / "file.txt").write_text(text)
    subprocess.run(["git", "-C", str(path), "add", "file.txt"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-q", "-m", text], check=True, capture_output=True
    )
    return gitstate.observe(path, dirty=False).head


# --------------------------------------------------------------------------- #
# Observing
# --------------------------------------------------------------------------- #
def test_observe_reports_head_branch_and_clean():
    if not HAVE_GIT:
        return
    with tempfile.TemporaryDirectory() as tmp:
        _repo(Path(tmp))
        state = gitstate.observe(tmp)
        assert len(state.head) == 40
        assert state.branch == "main"
        assert state.dirty is False
        assert state.observed is True


def test_observe_reports_a_dirty_tree_and_can_snapshot_it():
    if not HAVE_GIT:
        return
    with tempfile.TemporaryDirectory() as tmp:
        _repo(Path(tmp))
        (Path(tmp) / "file.txt").write_text("edited")
        state = gitstate.observe(tmp, stash=True)
        assert state.dirty is True
        # `stash create` writes a commit object without touching the worktree, the
        # index, or the stash ref — so the edit is still there afterwards.
        assert len(state.stash) == 40
        assert (Path(tmp) / "file.txt").read_text() == "edited"


def test_a_non_repo_is_observed_as_nothing_rather_than_as_clean():
    """The distinction the whole record rests on: empty means *not observed*."""
    with tempfile.TemporaryDirectory() as tmp:
        state = gitstate.observe(tmp)
        assert state.observed is False
        assert state.head == "" and state.branch == ""
        # Not False. "This directory is not a repository" and "this repository has no
        # uncommitted work" are different facts, and only one of them was learned.
        assert state.dirty is None
        assert state.attributes("git") == {}


def test_attributes_omit_what_was_not_observed():
    state = gitstate.RepoState(path="/x", head="abc", dirty=True)
    assert state.attributes("git.head.start") == {
        "git.head.start.head": "abc",
        "git.head.start.dirty": True,
    }


def test_nothing_bound_answers_empty_rather_than_raising():
    gitstate.unbind()
    try:
        assert gitstate.current_head() == ""
        assert gitstate.current_head(refresh=True) == ""
        assert gitstate.current_state().observed is False
        assert gitstate.bound() is None
    finally:
        gitstate.unbind()


def test_head_is_cached_until_refreshed():
    """What makes stamping every log record affordable — and its one cost."""
    if not HAVE_GIT:
        return
    with tempfile.TemporaryDirectory() as tmp:
        _repo(Path(tmp))
        gitstate.bind(tmp, ttl_s=3600)
        try:
            first = gitstate.current_head()
            moved = _commit(Path(tmp), "two")
            assert moved != first
            # The stale answer is the deliberate trade: a `rev-parse` per log line is
            # not affordable, and the span endpoints bracket the move regardless.
            assert gitstate.current_head() == first
            assert gitstate.current_head(refresh=True) == moved
            assert gitstate.current_head() == moved
        finally:
            gitstate.unbind()


def test_a_git_that_cannot_answer_costs_a_field_not_an_exception():
    original = gitstate.TIMEOUT_S
    try:
        # A command that would take far longer than it is given. The point is the
        # exception path, not the timeout value: every way git can fail to answer has
        # to leave an empty field behind.
        gitstate.TIMEOUT_S = 0.001
        assert gitstate._git(".", "log", "--all") == ""
    finally:
        gitstate.TIMEOUT_S = original


# --------------------------------------------------------------------------- #
# Spans
# --------------------------------------------------------------------------- #
class _Head:
    """A stand-in for the observer, so span tests need no repository.

    It records how it was asked, which is half of what is under test: an open reads the
    cache, a close re-reads, and a `git` per span open is the cost that was avoided.
    """

    def __init__(self, head: str = "aaa") -> None:
        self.head = head
        self.refreshes = 0

    def __call__(self, refresh: bool) -> str:
        if refresh:
            self.refreshes += 1
        return self.head


class _FakeSpan:
    def __init__(self, name, attributes) -> None:
        self.name = name
        self.attrs = dict(attributes or {})
        self.ended = False

    def set_attribute(self, key, value):
        self.attrs[key] = value

    def add_event(self, name, attributes=None):
        pass

    def set_status(self, status):
        pass

    def end(self):
        self.ended = True


class _FakeTracer:
    def __init__(self) -> None:
        self.spans: list[_FakeSpan] = []

    def start_span(self, name, context=None, attributes=None):
        span = _FakeSpan(name, attributes)
        self.spans.append(span)
        return span

    def by_name(self, name: str) -> _FakeSpan:
        return next(s for s in self.spans if s.name == name)


class _FakeTraceApi:
    class Status:
        def __init__(self, code, description=None) -> None:
            self.code, self.description = code, description

    class StatusCode:
        ERROR = "ERROR"

    @staticmethod
    def set_span_in_context(span):
        return span


class _FakeMeter:
    def create_gauge(self, name, **_):
        return None

    def create_counter(self, name, **_):
        return None


def _spans() -> tuple:
    """A `_Telemetry` over fake SDK objects — the same shape tests/test_otel.py uses,
    kept local so this file stays standalone-runnable."""
    tracer = _FakeTracer()
    t = otel._Telemetry(
        _FakeTraceApi, tracer, _FakeMeter(), lambda: None,
        otel.OtelSettings().heartbeat_every_s,
    )
    return t, tracer


def test_a_head_that_moves_inside_a_node_leaves_unequal_endpoints():
    probe = _Head("aaa")
    otel.set_head_probe(probe)
    try:
        t, tracer = _spans()
        records = importlib.import_module("workhorse.records")
        event = lambda node, seq, phase, **kw: records.NodeEvent(  # noqa: E731
            ts="2026-01-01T00:00:00+00:00", seq=seq, node=node, phase=phase, **kw
        )
        t.record_event(event("plan", 1, "enter"))
        probe.head = "bbb"  # the agent, or the node, committed
        t.record_event(event("plan", 1, "done", next="build"))
        span = tracer.by_name("plan")
        assert span.attrs["git.head.start"] == "aaa"
        assert span.attrs["git.head.end"] == "bbb"
    finally:
        otel.set_head_probe(None)


def test_a_turn_records_the_tree_it_ran_against():
    probe = _Head("aaa")
    otel.set_head_probe(probe)
    try:
        t, tracer = _spans()
        t.turn_start("plan", "sonnet", "high", 60.0, backend="claude")
        probe.head = "bbb"
        t.turn_end()
        span = tracer.by_name("agent_turn")
        assert span.attrs["git.head.start"] == "aaa"
        assert span.attrs["git.head.end"] == "bbb"
        # A turn opens with a refreshed read as well as closing with one: the agent is
        # the thing most likely to have moved HEAD since the last boundary.
        assert probe.refreshes == 2
    finally:
        otel.set_head_probe(None)


def test_the_root_span_brackets_the_whole_run():
    probe = _Head("aaa")
    otel.set_head_probe(probe)
    try:
        t, tracer = _spans()
        t.start_root("wf")
        probe.head = "zzz"
        t.end_run("terminal", None)
        root = tracer.by_name("run:wf")
        assert root.attrs["git.head.start"] == "aaa"
        assert root.attrs["git.head.end"] == "zzz"
    finally:
        otel.set_head_probe(None)


def test_no_observation_stamps_no_attribute():
    """Absent, not blank: a `git.head.start` of "" is a claim nobody made."""
    otel.set_head_probe(None)
    t, tracer = _spans()
    t.start_root("wf")
    t.end_run("terminal", None)
    root = tracer.by_name("run:wf")
    assert "git.head.start" not in root.attrs
    assert "git.head.end" not in root.attrs


def test_a_probe_that_raises_costs_an_attribute_not_the_span():
    def boom(refresh: bool) -> str:
        raise RuntimeError("git exploded")

    otel.set_head_probe(boom)
    try:
        t, tracer = _spans()
        t.start_root("wf")
        t.end_run("terminal", None)
        assert "git.head.start" not in tracer.by_name("run:wf").attrs
    finally:
        otel.set_head_probe(None)


# --------------------------------------------------------------------------- #
# run.json
# --------------------------------------------------------------------------- #
def test_run_json_records_what_the_run_started_from_and_ended_on():
    if not HAVE_GIT:
        return
    artifacts = importlib.import_module("workhorse.artifacts")
    records = importlib.import_module("workhorse.records")
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        _repo(repo)
        gitstate.bind(repo, ttl_s=0.0)
        try:
            writer = artifacts.ArtifactWriter("wf", Path(tmp) / "runs", run_id="x")
            started = records.parse_run_record((writer.run_dir / "run.json").read_text())
            assert started.repo_start is not None
            assert started.repo_start.branch == "main"
            # No end yet — the run is still going, and an "ended on" written here would
            # be a guess at a commit the run has not reached.
            assert started.repo_end is None

            moved = _commit(repo, "two")
            writer.finish("terminal")
            ended = records.parse_run_record((writer.run_dir / "run.json").read_text())
            # Preserved, not re-observed: "what the run started from" must not drift to
            # mean "what the last write happened to see".
            assert ended.repo_start is not None
            assert ended.repo_start.head == started.repo_start.head
            assert ended.repo_end is not None
            assert ended.repo_end.head == moved
        finally:
            gitstate.unbind()


def test_run_json_outside_a_repo_records_no_observation_at_all():
    artifacts = importlib.import_module("workhorse.artifacts")
    records = importlib.import_module("workhorse.records")
    gitstate.unbind()
    with tempfile.TemporaryDirectory() as tmp:
        writer = artifacts.ArtifactWriter("wf", Path(tmp) / "runs", run_id="x")
        record = records.parse_run_record((writer.run_dir / "run.json").read_text())
        assert record.repo_start is None


def test_an_older_run_json_without_the_fields_still_parses():
    """The resume path reads whatever the previous process left, including a file
    written before any of this existed."""
    records = importlib.import_module("workhorse.records")
    record = records.parse_run_record('{"workflow": "wf", "run_id": "x"}')
    assert record.repo_start is None and record.repo_end is None


# --------------------------------------------------------------------------- #
# Logs
# --------------------------------------------------------------------------- #
def _record() -> logging.LogRecord:
    return logging.LogRecord("t", logging.INFO, __file__, 1, "hello", None, None)


def test_log_records_carry_the_head_current_when_they_were_emitted():
    if not HAVE_GIT:
        return
    with tempfile.TemporaryDirectory() as tmp:
        _repo(Path(tmp))
        gitstate.bind(tmp, ttl_s=0.0)  # every read re-reads; the cache is tested above
        try:
            filt = logsetup._HeadFilter()
            before, after = _record(), _record()
            filt.filter(before)
            moved = _commit(Path(tmp), "two")
            filt.filter(after)
            # `getattr`, because "no head at all" is a state this attribute has and a
            # `LogRecord` does not declare it.
            assert getattr(before, "head", "") != getattr(after, "head", "")
            assert getattr(after, "head", "") == moved
        finally:
            gitstate.unbind()


def test_a_log_record_from_a_non_repo_carries_no_head_at_all():
    gitstate.unbind()
    record = _record()
    assert logsetup._HeadFilter().filter(record) is True
    assert not hasattr(record, "head")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
