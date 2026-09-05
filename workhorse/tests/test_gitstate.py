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
import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from workhorse import gitstate, logsetup, otel

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


def test_observe_preserves_the_exact_origin_url():
    if not HAVE_GIT:
        return
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        _repo(repo)
        origin = "git@github.com:example-org/api-service.git"
        subprocess.run(
            ["git", "-C", str(repo), "remote", "add", "origin", origin],
            check=True,
            capture_output=True,
        )

        state = gitstate.observe(repo)

        assert state.origin == origin
        assert state.root == str(repo.resolve())
        assert len(state.head) == 40


def test_scope_keeps_multiple_git_roots_and_an_unversioned_primary():
    if not HAVE_GIT:
        return
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        docs = root / "docs"
        api = root / "api-service"
        web = root / "web-app"
        docs.mkdir()
        api.mkdir()
        web.mkdir()
        _repo(api)
        _repo(web)
        (api / "src").mkdir()
        subprocess.run(
            ["git", "-C", str(api), "remote", "add", "origin", "https://example.com/api.git"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(web), "remote", "add", "origin", "git@example.com:web.git"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(web), "switch", "-q", "-c", "ostler-stories"],
            check=True,
            capture_output=True,
        )

        snapshot = gitstate.observe_scope(docs, [api / "src", api, web])

        assert [(item.role, item.vcs) for item in snapshot.directories] == [
            ("cwd", "unversioned"),
            ("add_dir", "git"),
            ("add_dir", "git"),
        ]
        api_state, web_state = snapshot.directories[1:]
        assert api_state.root == str(api.resolve())
        assert api_state.origin == "https://example.com/api.git"
        assert api_state.branch == "main"
        assert len(api_state.head) == 40
        assert web_state.origin == "git@example.com:web.git"
        assert web_state.branch == "ostler-stories"
        attrs = snapshot.attributes()
        assert attrs["workspace.path"] == str(docs.resolve())
        assert attrs["workspace.vcs"] == "unversioned"
        assert "git.head" not in attrs
        repositories = json.loads(attrs["workhorse.repositories"])
        assert [entry["root"] for entry in repositories[1:]] == [
            str(api.resolve()),
            str(web.resolve()),
        ]


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
        # The containing agent-node span already captured this scope. Its turn reuses
        # that immutable start snapshot; only the end re-observes what the agent moved.
        assert probe.refreshes == 1
    finally:
        otel.set_head_probe(None)


def test_agent_node_and_turn_spans_use_their_own_multi_repo_scope():
    calls: list[tuple[str | None, tuple[str, ...]]] = []

    def observe(cwd: str | None, add_dirs: tuple[str, ...], _refresh: bool) -> dict[str, str]:
        calls.append((cwd, add_dirs))
        primary = cwd or "/workspace/docs"
        return {
            "workspace.path": primary,
            "workspace.vcs": "unversioned" if primary.endswith("docs") else "git",
            "git.origin": "git@example.com:web-app.git" if primary.endswith("web-app") else "",
            "git.branch": "ostler-stories" if primary.endswith("web-app") else "",
            "git.head": "c" * 40 if primary.endswith("web-app") else "",
            "workhorse.repositories": json.dumps([primary, *add_dirs]),
        }

    otel.set_repository_probe(observe)
    try:
        telemetry, tracer = _spans()
        telemetry.start_root("wf")
        records = importlib.import_module("workhorse.records")
        event = records.NodeEvent(
            ts="2026-01-01T00:00:00+00:00",
            seq=1,
            node="repair",
            phase="enter",
            repository_cwd="/workspace/web-app",
            repository_add_dirs=["/workspace/docs", "/workspace/api-service"],
        )
        telemetry.record_event(event)
        telemetry.turn_start(
            "repair",
            "model",
            "high",
            60.0,
            cwd="/workspace/web-app",
            add_dirs=("/workspace/docs", "/workspace/api-service"),
        )

        node = tracer.by_name("repair")
        turn = tracer.by_name("agent_turn")
        for span in (node, turn):
            assert span.attrs["workspace.path.start"] == "/workspace/web-app"
            assert span.attrs["workspace.vcs.start"] == "git"
            assert span.attrs["git.origin.start"] == "git@example.com:web-app.git"
            assert span.attrs["git.branch.start"] == "ostler-stories"
            assert span.attrs["git.head.start"] == "c" * 40
            assert json.loads(span.attrs["workhorse.repositories.start"]) == [
                "/workspace/web-app",
                "/workspace/docs",
                "/workspace/api-service",
            ]
        assert telemetry.current_repository()["git.head"] == "c" * 40
        assert calls[-1] == (
            "/workspace/web-app",
            ("/workspace/docs", "/workspace/api-service"),
        )
    finally:
        otel.set_repository_probe(None)


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


def test_log_records_are_pinned_to_the_active_span_start_snapshot():
    current = {
        "workspace.path": "/workspace/api-service",
        "workspace.vcs": "git",
        "git.origin": "https://example.com/api.git",
        "git.branch": "main",
        "git.head": "a" * 40,
        "workhorse.repositories": "[]",
    }
    otel.set_repository_probe(lambda cwd, add_dirs, refresh: current)
    telemetry, _ = _spans()
    previous = otel.install(otel.TelemetryHost(active=telemetry))
    try:
        telemetry.start_root("wf")
        before, after = _record(), _record()
        filt = logsetup._HeadFilter()
        filt.filter(before)
        current["git.head"] = "b" * 40
        filt.filter(after)

        assert before.__dict__["git.head"] == "a" * 40
        assert after.__dict__["git.head"] == "a" * 40
        assert after.__dict__["git.origin"] == "https://example.com/api.git"
        assert after.__dict__["git.branch"] == "main"
        assert after.__dict__["head"] == "a" * 40
    finally:
        telemetry.end_run("terminal")
        otel.install(previous)
        otel.set_repository_probe(None)


def test_a_log_record_from_an_unversioned_span_keeps_the_directory():
    snapshot = {"workspace.path": "/workspace/docs", "workspace.vcs": "unversioned"}
    otel.set_repository_probe(lambda cwd, add_dirs, refresh: snapshot)
    telemetry, _ = _spans()
    previous = otel.install(otel.TelemetryHost(active=telemetry))
    try:
        telemetry.start_root("wf")
        record = _record()
        assert logsetup._HeadFilter().filter(record) is True
        assert record.__dict__["workspace.path"] == "/workspace/docs"
        assert record.__dict__["workspace.vcs"] == "unversioned"
        assert not hasattr(record, "head")
    finally:
        telemetry.end_run("terminal")
        otel.install(previous)
        otel.set_repository_probe(None)


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
