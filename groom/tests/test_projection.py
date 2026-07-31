"""Tests for groom.projection — the one dataclass→JSON layer.

Two things are worth holding still here. The first is the ordering/liveness
contract the fleet list used to carry in HTML: blocked first, then live, then
silent, then finished; and "dead" meaning *observed silent*, never *never
observed*. The second is the reason this module exists at all — the websocket
push and ``GET /api/state`` must be the same payload, because the browser feeds
both to one ``applyState()``. A test that asserts they are equal is what keeps
the resync path from rotting behind the socket.

Run: uv run pytest tests/test_projection.py
"""
from __future__ import annotations

import json

from groom import projection, state, store
from groom.models import GateInfo, RunTelemetry, WorkflowContainer, WorkflowState


def _wf(container_id="abc123", **kwargs) -> WorkflowContainer:
    return WorkflowContainer(container_id=container_id, name=kwargs.pop("name", "demo"), **kwargs)


def _tel(run_id="abc123", **kwargs) -> RunTelemetry:
    return RunTelemetry(run_id=run_id, **kwargs)


def _blocked(container_id="abc123", file_path="docs/a.md", question="Which one?", **kwargs):
    wf = _wf(container_id, state=WorkflowState.BLOCKED, **kwargs)
    wf.gates[file_path] = GateInfo(workflow_id=container_id, file_path=file_path, question=question)
    return wf


class _runs_are:
    """Swap the telemetry hot cache for the duration of a test."""

    def __init__(self, mapping):
        self.mapping = mapping

    def __enter__(self):
        self.prev = dict(state.RUNS)
        state.RUNS.clear()
        state.RUNS.update(self.mapping)

    def __exit__(self, *exc):
        state.RUNS.clear()
        state.RUNS.update(self.prev)


class _scanning:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        self.prev = state.SCANNING
        state.SCANNING = self.value

    def __exit__(self, *exc):
        state.SCANNING = self.prev


# ---- the fleet is every instance, not just the gated ones ----
def test_fleet_rows_include_every_instance():
    # A run with no open gate is still a run, and a run nobody is watching is
    # exactly the one that dies silently.
    rows = projection.fleet_rows([
        _wf("run", state=WorkflowState.RUNNING, current_node="write_epic"),
        _blocked("blk", question="CI is red — pick an option"),
        _wf("fin", state=WorkflowState.FINISHED, exit_code=0),
    ])
    assert {r["id"] for r in rows} == {"run", "blk", "fin"}
    blk = next(r for r in rows if r["id"] == "blk")
    assert blk["question"] == "CI is red — pick an option"
    assert blk["gate_path"] == "docs/a.md" and blk["gate_count"] == 1


def test_fleet_rows_order_blocked_then_live_then_dead_then_finished():
    now = 1_700_000_000.0
    wfs = [
        _wf("fin", name="d", state=WorkflowState.FINISHED, exit_code=0, run_id="fin"),
        _wf("dead", name="c", state=WorkflowState.RUNNING, run_id="dead"),
        _wf("live", name="b", state=WorkflowState.RUNNING, run_id="live"),
        _blocked("blk", name="a", file_path="docs/a.md"),
    ]
    with _runs_are({
        "live": _tel("live", last_heartbeat_ts=now - 5),
        "dead": _tel("dead", last_heartbeat_ts=now - store.LIVE_AFTER_S - 600),
    }):
        rows = projection.fleet_rows(wfs, now=now)
    assert [r["id"] for r in rows] == ["blk", "live", "dead", "fin"]
    by_id = {r["id"]: r for r in rows}
    assert by_id["live"]["live"] == "live"
    assert by_id["dead"]["live"] == "dead"
    assert by_id["dead"]["live_label"].startswith("silent ")


def test_liveness_is_unknown_without_telemetry():
    # "dead" must always mean *observed silent*, never *never observed* — a docker
    # row exporting to another collector is unknown, not a corpse.
    with _runs_are({}):
        [row] = projection.fleet_rows([_wf("x", state=WorkflowState.RUNNING)])
    assert row["live"] == "unknown" and row["live_label"] == ""


def test_finished_row_carries_its_exit_hint():
    with _runs_are({}):
        rows = projection.fleet_rows([
            _wf("a", state=WorkflowState.FINISHED, exit_code=1),
            _wf("b", state=WorkflowState.RUNNING, exit_code=0),  # code set but still live
        ])
    by_id = {r["id"]: r for r in rows}
    assert by_id["a"]["exit_hint"] == "exited 1"
    assert by_id["b"]["exit_hint"] == ""


def test_telemetry_outranks_the_containers_exit_state():
    # The container says it is over; the run beat a second ago. The beat is the
    # only signal that comes from the process itself, so it wins.
    now = 5_000.0
    wf = _wf("x", state=WorkflowState.FINISHED, exit_code=0)
    tel = _tel("x", last_heartbeat_ts=now - 1, first_seen_ts=now - 100)
    with _runs_are({"x": tel}):
        [row] = projection.fleet_rows([wf], now=now)
    assert row["live"] == "live" and row["live_label"] == "alive"


# ---- telemetry pane: live is "emitting now", never span history ----
def test_run_card_live_comes_from_the_hot_cache_not_the_span_history():
    now = 5_000.0
    summary = {"run_id": "rerun1", "workflow": "author", "span_count": 740,
               "error_count": 0, "first_ts": 1.0, "last_ts": now}
    # A resumed run has a root span from its *previous* session in the store. That
    # is history; the fresh heartbeat is the run.
    tel = _tel("rerun1", last_heartbeat_ts=now - 2, first_seen_ts=1.0,
               terminal="interrupted", terminal_ts=100.0, current_node="write_story")
    assert projection.run_card(summary, tel, now=now)["live"] is False  # terminal not yet cleared
    tel.terminal, tel.terminal_ts = "", 0.0
    card = projection.run_card(summary, tel, now=now)
    assert card["live"] is True and card["doing"] == "write_story"


def test_run_card_falls_back_to_the_stores_live_ids_when_not_in_the_cache():
    # A groom that just restarted has an empty hot cache; the store still knows
    # who was beating inside the window.
    summary = {"run_id": "R7", "workflow": "coder", "span_count": 3, "error_count": 0}
    assert projection.run_card(summary, None, {"R7"})["live"] is True
    assert projection.run_card(summary, None, set())["live"] is False


def test_traces_view_passes_live_ids_through_to_every_card():
    view = projection.traces_view(
        [{"run_id": "R7", "workflow": "coder"}, {"run_id": "R8", "workflow": "coder"}],
        [], {}, {"R7"}, connected_only=False,
    )
    assert {r["run_id"]: r["live"] for r in view["runs"]} == {"R7": True, "R8": False}


def test_traces_view_shows_only_connected_runs_by_default():
    # The store keeps two weeks of runs; the pane is for watching, so a card and
    # its spans are dropped together — a span table full of a hidden run's nodes
    # is telemetry from nowhere.
    summaries = [{"run_id": "R7", "workflow": "coder"}, {"run_id": "R8", "workflow": "coder"}]
    spans = [
        {"run_id": "R7", "node": "plan", "name": "plan", "start_ts": 1.0, "end_ts": 2.0},
        {"run_id": "R8", "node": "plan", "name": "plan", "start_ts": 1.0, "end_ts": 2.0},
    ]
    view = projection.traces_view(summaries, spans, {}, {"R7"})
    assert [r["run_id"] for r in view["runs"]] == ["R7"]
    assert [s["run_id"] for s in view["spans"]] == ["R7"]


# ---- filtering ----
def test_query_filters_the_fleet():
    wfs = [
        _wf("a", name="coder-001", workflow_type="coder", state=WorkflowState.RUNNING),
        _wf("b", name="author-002", workflow_type="author", state=WorkflowState.IDLE),
    ]
    with _runs_are({}):
        assert [r["id"] for r in projection.fleet_rows(wfs, query="author")] == ["b"]
        assert [r["id"] for r in projection.fleet_rows(wfs, query="nomatch")] == []


# ---- status bar ----
def test_status_bar_counts_states():
    status = projection.status_bar([
        _blocked("a"),
        _wf("b", state=WorkflowState.RUNNING),
        _wf("c", state=WorkflowState.RUNNING),
        _wf("d", state=WorkflowState.IDLE),
    ])
    assert status["counts"]["blocked"] == 1
    assert status["counts"]["running"] == 2
    assert status["counts"]["idle"] == 1
    assert status["counts"]["finished"] == 0
    assert status["workers"] == 4


# ---- the scanning flag: an unscanned fleet must not read finished-and-empty ----
def test_state_message_reports_whether_discovery_is_still_running():
    # The browser picks the spinner over the empty state off this flag, so it has
    # to survive the projection — and it must not claim to be scanning when the
    # operator is merely filtering to no matches.
    with _scanning(True):
        assert projection.state_message([])["scanning"] is True
    with _scanning(False):
        assert projection.state_message([])["scanning"] is False


# ---- the whole point: one payload, two delivery paths ----
def test_state_message_is_json_serializable():
    # It goes out over the socket as text and out of /api/state as a body; a value
    # that only survives one of those is a bug the other path would find in prod.
    now = 1_700_000_000.0
    wfs = [_blocked("blk"), _wf("run", state=WorkflowState.RUNNING, run_id="run")]
    with _runs_are({"run": _tel("run", last_heartbeat_ts=now - 5)}):
        msg = projection.state_message(wfs, now=now)
    assert json.loads(json.dumps(msg)) == msg
    assert msg["type"] == "state"
    assert {"runs", "status", "scanning", "ts"} <= set(msg)


def test_run_message_row_matches_the_same_row_in_the_state_message():
    # A single-run delta and the full state must agree about that run, or the
    # fleet drifts depending on which frame arrived last.
    now = 1_700_000_000.0
    wf = _blocked("blk", name="a")
    with _runs_are({}):
        full = projection.state_message([wf], now=now)
        one = projection.run_message(wf, now=now)
    assert one["type"] == "run"
    assert one["run"] == full["runs"][0]


# ---- detail pane: one shape, whether fetched or pushed ----
def test_run_detail_carries_gates_head_metrics_and_logs():
    # The pane's whole point, as data: what it's doing, the thing you can answer
    # next, then the numbers, then the trail. Everything the browser needs to draw
    # it arrives in one object, so a fetched pane and a pushed one cannot differ.
    now = 1_700_000_000.0
    wf = _blocked(file_path="docs/gate.md", activity="reviewing ACME-4")
    detail = projection.run_detail(
        wf,
        _tel("abc123", activity="reviewing ACME-4", pid=4242),
        {"span_count": 12, "error_count": 0},
        [{"ts": now, "severity": "INFO", "node": "review", "body": "hello"}],
        now=now,
    )
    assert detail["found"] is True and detail["id"] == "abc123"
    assert {"head", "gates", "metrics", "logs"} <= set(detail)
    assert detail["head"]["activity"] == "reviewing ACME-4"
    assert detail["metrics"]["cells"][0] == {"key": "node", "value": "—"}
    assert [line["body"] for line in detail["logs"]] == ["hello"]


def test_detail_message_matches_the_fetched_detail():
    # `GET /worker/{id}` and the pushed `detail` frame feed the same client state,
    # so a divergence here shows up as a pane that changes when it refreshes.
    now = 1_700_000_000.0
    wf = _blocked("blk")
    pushed = projection.detail_message(wf, now=now)
    assert pushed["type"] == "detail" and pushed["id"] == "blk"
    assert pushed["detail"] == projection.run_detail(wf, now=now)
    assert json.loads(json.dumps(pushed)) == pushed


def test_gate_question_travels_as_data_not_markup():
    # Questions are LLM-authored and untrusted. The wire carries the source text
    # verbatim — no server-side markdown, no escaping — because the browser is the
    # only thing that knows whether it is about to build a text node or hand the
    # string to DOMPurify. A server that half-escaped it would double-escape there.
    wf = _blocked(question="Use <script>alert(1)</script>?")
    gate = projection.run_detail(wf)["gates"][0]
    assert gate["question"] == "Use <script>alert(1)</script>?"
    assert gate["file_path"] == "docs/a.md"


def test_run_detail_lists_every_open_gate():
    # Two gates means two answer forms, keyed by file path — the client needs both
    # paths because the {"cmd": "answer", …} frame is scoped by (run, file).
    wf = _blocked()
    wf.gates["docs/b.md"] = GateInfo(workflow_id="abc123", file_path="docs/b.md", question="Q2?")
    paths = [gate["file_path"] for gate in projection.run_detail(wf)["gates"]]
    assert sorted(paths) == ["docs/a.md", "docs/b.md"]


def test_detail_of_a_finished_run_has_no_gates_but_keeps_its_node():
    # The "nothing to answer" state the client draws instead of a form: it names
    # the state and the node, so a run with no gate still says what it is doing.
    wf = _wf(state=WorkflowState.RUNNING, current_node="write_epic")
    detail = projection.run_detail(wf)
    assert detail["gates"] == []
    assert detail["state"] == "running" and detail["node"] == "write_epic"


def test_exit_hint_only_on_finished_with_a_code():
    # A code set on a run that is still live is leftover, not a verdict.
    ok = projection.head(_wf("a", state=WorkflowState.FINISHED, exit_code=0))
    err = projection.head(_wf("b", state=WorkflowState.FINISHED, exit_code=1))
    running = projection.head(_wf("c", state=WorkflowState.RUNNING, exit_code=0))
    assert ok["exit_hint"] == "exited 0" and ok["exit_ok"] is True
    assert err["exit_hint"] == "exited 1" and err["exit_ok"] is False
    assert running["exit_hint"] == ""


# ---- metrics + log trail: the two halves that refresh on the clock ----
def test_run_metrics_merges_hot_cache_and_durable_facts():
    now = 1_700_000_000.0
    wf = _wf("x", state=WorkflowState.RUNNING, run_id="x")
    tel = _tel("x", current_node="review", node_elapsed_s=720, turn_idle_s=200,
               last_heartbeat_ts=now - 12, first_seen_ts=now - 3600, pid=99,
               run_dir="/runs/x", fired={"STUCK"})
    m = projection.metrics(wf, tel, {"span_count": 41, "error_count": 2, "gas": 3}, now=now)
    cells = {cell["key"]: cell for cell in m["cells"]}
    assert m["empty"] is False
    assert cells["node"]["value"] == "review" and cells["in node"]["value"] == "12m 00s"
    assert cells["gas"]["value"] == "3"            # durable half
    assert cells["spans"]["value"] == "41"
    assert cells["errors"] == {"key": "errors", "value": "2", "cls": "bad"}
    assert cells["pid"]["value"] == "99"
    assert m["alerts"] == ["STUCK"] and m["run_dir"] == "/runs/x"


def test_run_metrics_cell_order_is_the_layout():
    # Cells are an ordered list, not a mapping: the order *is* the grid, and a dict
    # would hand that decision to whichever serializer touched it last.
    now = 1_700_000_000.0
    m = projection.metrics(_wf("x", state=WorkflowState.RUNNING), _tel("x"), {}, now=now)
    assert [cell["key"] for cell in m["cells"]][:3] == ["node", "in node", "agent idle"]


def test_run_metrics_empty_without_any_telemetry():
    # A docker row that never exported anything must say so rather than render a
    # wall of dashes that reads like a broken run.
    assert projection.metrics(_wf("x", state=WorkflowState.RUNNING))["empty"] is True


def test_log_trail_newest_first_with_severity_classes():
    logs = [
        {"ts": 1_700_000_000.0, "severity": "ERROR", "node": "review", "body": "boom"},
        {"ts": 1_699_999_990.0, "severity": "INFO", "node": "plan", "body": "ok"},
    ]
    lines = projection.log_lines(logs)
    assert [line["body"] for line in lines] == ["boom", "ok"]
    assert lines[0]["cls"] == "bad" and lines[0]["level"] == "ERRO"
    assert lines[1]["cls"] == ""


def test_log_trail_is_capped():
    # An unbounded trail is a memory leak in the browser and a slow frame on the
    # wire; the cap is the projection's, so every delivery path shares it.
    lines = projection.log_lines([{"ts": 0.0, "body": str(i)} for i in range(500)])
    assert len(lines) == projection.LOG_TRAIL_LIMIT


# ---- container+repo picker (Files / Diff panels) ----
def test_repo_entries_group_checkouts_under_their_container():
    wf_a = _wf("a", name="coder-001", workflow_type="coder", state=WorkflowState.RUNNING)
    wf_b = _wf("b", name="author-002", workflow_type="author", state=WorkflowState.IDLE)
    groups = projection.repo_entries([(wf_a, ["acme", "globex"]), (wf_b, [])])
    assert [g["container"] for g in groups] == ["a", "b"]
    assert [r["label"] for r in groups[0]["repos"]] == ["coder-001/acme", "coder-001/globex"]
    assert groups[0]["type"] == "coder"
    # wf_b found no checkout, but still gets a single volume-root entry so it can
    # be browsed at all — labelled by the container alone, with an empty repo dir.
    assert groups[1]["repos"] == [{"repo": "", "label": "author-002"}]


def test_repo_entries_empty_when_nothing_is_running():
    assert projection.repo_entries([]) == []


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(list(globals().items())):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"PASS  {name}")
        except Exception as exc:  # noqa: BLE001 - report and keep going
            failed += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    total = len([n for n in globals() if n.startswith("test_")])
    print(f"\n{total - failed}/{total} passed")
    raise SystemExit(1 if failed else 0)
