"""The Activity tab's data: a stored turn read per backend, the pass a turn belongs to, the timeline and the two endpoints."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from litestar.testing import TestClient
from test_flows import _span, _state, _turn
from test_run_clock import RUN, STATE, _DB, span

from groom import activity, flows, state, store, transcript_parse, turns
from groom import app as groom_app
from groom.models import WorkflowContainer

BASE = 1_700_000_000.0
SESSION = "sess-1"
SLUG = "001-00002-qa-story"


def _iso(offset: float) -> str:
    return datetime.fromtimestamp(BASE + offset, UTC).isoformat()


def _write(path: Path, records: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record) + "\n" for record in records))
    return path


def _claude(offset: float, role: str, content: object) -> dict:
    return {"timestamp": _iso(offset), "type": role, "message": {"role": role, "content": content}}


def test_a_claude_record_keeps_the_messages_and_pairs_each_tool_with_its_result(tmp_path: Path) -> None:
    path = _write(tmp_path / "t.jsonl", [
        _claude(1, "user", "do the thing"),
        _claude(2, "assistant", [
            {"type": "text", "text": "Reading the plan."},
            {"type": "tool_use", "id": "a", "name": "Read", "input": {"file_path": "plan.md"}},
        ]),
        _claude(3, "user", [{"type": "tool_result", "tool_use_id": "a", "content": "ten lines", "is_error": True}]),
    ])
    entries = transcript_parse.read_files({"transcript.jsonl": path})
    assert entries is not None
    kinds = [(entry["kind"], entry.get("role") or entry.get("name")) for entry in entries]
    assert kinds == [("message", "user"), ("message", "assistant"), ("tool", "Read")]
    tool = entries[2]
    assert tool["summary"] == "plan.md" and tool["result"] == "ten lines" and tool["failed"] is True


def test_a_resumed_session_record_is_cut_to_the_turns_own_window(tmp_path: Path) -> None:
    path = _write(tmp_path / "t.jsonl", [
        _claude(1, "assistant", "earlier turn"),
        _claude(100, "assistant", "this turn"),
        _claude(300, "assistant", "later turn"),
    ])
    entries = transcript_parse.read_files({"transcript.jsonl": path}, (BASE + 95, BASE + 105))
    assert entries is not None
    assert [entry["text"] for entry in entries] == ["this turn"]


def test_a_malformed_line_is_skipped_and_html_stays_raw_text(tmp_path: Path) -> None:
    path = tmp_path / "t.jsonl"
    payload = '<img src=x onerror="alert(1)"><script>alert(2)</script>'
    path.write_text("{not json\n" + json.dumps(_claude(1, "assistant", payload)) + "\n[1]\n")
    entries = transcript_parse.read_files({"transcript.jsonl": path})
    assert entries is not None and [entry["text"] for entry in entries] == [payload]


def test_a_codex_rollout_gives_messages_commands_and_file_changes(tmp_path: Path) -> None:
    def item(offset: float, body: dict) -> dict:
        return {"timestamp": _iso(offset), "type": "event_msg", "payload": {"type": "item_completed", "item": body}}

    path = _write(tmp_path / "t.jsonl", [
        item(1, {"type": "AgentMessage", "content": [{"text": "Running the tests."}]}),
        item(2, {"type": "CommandExecution", "command": ["bash", "-lc", "pytest -q"], "aggregated_output": "boom", "exit_code": 1}),
        item(3, {"type": "FileChange", "changes": {"a.py": {}, "b.py": {}}}),
    ])
    entries = transcript_parse.read_files({"transcript.jsonl": path})
    assert entries is not None
    assert entries[0]["text"] == "Running the tests."
    assert (entries[1]["name"], entries[1]["summary"], entries[1]["failed"]) == ("shell", "pytest -q", True)
    assert entries[2]["summary"] == "a.py, b.py"


def test_an_opencode_tee_and_an_opencode_export_both_read(tmp_path: Path) -> None:
    tee = _write(tmp_path / "tee.jsonl", [
        {"type": "text", "timestamp": (BASE + 1) * 1000, "part": {"text": "hello"}},
        {"type": "tool_use", "timestamp": (BASE + 2) * 1000, "part": {"tool": "bash", "state": {"input": {"command": "ls"}, "output": "x", "status": "completed"}}},
    ])
    exported = tmp_path / "export.json"
    exported.write_text(json.dumps({"messages": [
        {"info": {"role": "assistant", "time": {"created": (BASE + 1) * 1000}}, "parts": [
            {"type": "text", "text": "hello"},
            {"type": "tool", "tool": "bash", "state": {"input": {"command": "ls"}, "output": "x", "status": "error"}},
        ]},
    ]}))
    from_tee = transcript_parse.read_files({"transcript.jsonl": tee})
    from_export = transcript_parse.read_files({"transcript.json": exported})
    assert from_tee is not None and from_export is not None
    assert [(e["kind"], e.get("text") or e["summary"]) for e in from_tee] == [("message", "hello"), ("tool", "ls")]
    assert from_export[1]["failed"] is True


def test_acp_chunks_join_and_a_calls_updates_merge(tmp_path: Path) -> None:
    def chunk(text: str) -> dict:
        return {"update": {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": text}}}

    path = _write(tmp_path / "t.acp.jsonl", [
        chunk("Hel"), chunk("lo"),
        {"update": {"sessionUpdate": "tool_call", "toolCallId": "c1", "title": "Read", "rawInput": {"path": "x.py"}}},
        {"update": {"sessionUpdate": "tool_call_update", "toolCallId": "c1", "status": "completed"}},
    ])
    entries = transcript_parse.read_files({"transcript.acp.jsonl": path})
    assert entries is not None
    assert [entry["kind"] for entry in entries] == ["message", "tool"]
    assert entries[0]["text"] == "Hello"


def test_a_visit_still_in_its_run_dir_lists_the_files_an_archived_record_would_name(tmp_path: Path) -> None:
    stem = tmp_path / turns.RUN_TRANSCRIPTS / f"{SLUG}__{SESSION}"
    _write(Path(f"{stem}.jsonl"), [_claude(1, "assistant", "hello")])
    found = turns.run_dir_files(tmp_path, SLUG, SESSION)
    assert list(found) == ["transcript.jsonl"]
    assert turns.run_dir_files(tmp_path, SLUG, "other") == {}


def test_a_record_with_no_transcript_file_reads_as_none(tmp_path: Path) -> None:
    assert transcript_parse.read_files({"prompt.md": tmp_path / "prompt.md"}) is None


def test_a_turn_is_numbered_by_the_runs_of_its_flow_node() -> None:
    spans = [
        _span("f1", "qa", attrs={"workhorse.depth": 0}, start=0),
        _state("s1", "review", parent="f1", depth=1),
        _span("n1", "check", parent="s1"),
        _turn("t1", "n1", "check"),
        _span("f2", "qa", attrs={"workhorse.depth": 0}, start=100),
        _state("s2", "review", parent="f2", depth=1),
        _span("n2", "check", parent="s2"),
        _turn("t2", "n2", "check"),
        _turn("lost", "gone", "check"),
    ]
    assert flows.turn_passes(spans) == {"t1": ("qa", 1), "t2": ("qa", 2)}


def _seed_run(tmp_path: Path) -> None:
    attrs = {
        "workhorse.visit.slug": SLUG, "session.id": SESSION, "work_id": "sign-in", "model": "claude-sonnet-5",
        "activity": "Stack up on a free port.\nSecond line.", "usage.output_tokens": 21400, "total_cost_usd": 6.12,
        "backend": "claude", "duration_ms": 60000,
    }
    store.insert_spans([
        span("r1", "t1", "", "coder", "run:coder", BASE, 500, {}, 1),
        span("f1", "t1", "r1", "qa", "qa", BASE + 1, 400, {"workhorse.depth": 0}, 1),
        span("s1", "t1", "f1", "work", "work", BASE + 2, 300, STATE, 1),
        span("n1", "t1", "s1", "qa-story", "qa-story", BASE + 3, 200, {"workhorse.depth": 2}, 1),
        span("a1", "t1", "n1", "qa-story", "agent_turn", BASE + 100, 60, attrs, 1),
    ])
    root = turns.transcripts_root() / RUN / f"{SLUG}__{SESSION}"
    _write(root / "transcript.jsonl", [
        _claude(10, "assistant", "from an earlier turn"),
        _claude(110, "assistant", "Bringing the stack up."),
        _claude(120, "assistant", [{"type": "tool_use", "id": "z", "name": "Bash", "input": {"command": "make up"}}]),
    ])
    store.insert_turns([{
        "run_id": RUN, "node": "qa-story", "session_id": SESSION, "generation": 1, "seq": 2, "ts": BASE + 100,
        "path": f"{RUN}/{SLUG}__{SESSION}",
    }])


def test_the_timeline_lists_a_finished_turn_with_its_figures_and_pass(tmp_path: Path) -> None:
    with _DB():
        _seed_run(tmp_path)
        rows = activity.timeline(RUN)["rows"]
    assert len(rows) == 1
    row = rows[0]
    assert (row["slug"], row["node"], row["visit"], row["work_id"]) == (SLUG, "qa-story", "001-00002", "sign-in")
    assert (row["flow"], row["pass"], row["status"], row["model"]) == ("qa", 1, "done", "claude-sonnet-5")
    assert row["result"] == "Stack up on a free port."
    assert row["cost_usd"] == 6.12 and row["output_tokens"] == 21400 and row["duration_s"] == 60


def test_a_finished_turn_reads_only_its_own_window_and_drops_the_rest(tmp_path: Path) -> None:
    with _DB():
        _seed_run(tmp_path)
        body = activity.turn(RUN, SLUG)
    assert [(entry["kind"], entry.get("text") or entry["summary"]) for entry in body["entries"]] == [
        ("message", "Bringing the stack up."), ("tool", "make up"),
    ]
    assert set(body["entries"][1]) == {"kind", "name", "summary", "failed", "duration_s", "result"}


def _live(slug: str, text: str, ts: float) -> dict:
    update = {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": text}}
    return {"key": f"{slug}-{ts}", "slug": slug, "ts": ts, "node": "qa-story", "parent": "", "update": update}


def test_a_turn_with_no_span_yet_is_running_and_reads_from_the_live_rows() -> None:
    live = {"001-00003-qa-story": [_live("001-00003-qa-story", "Rerunning it.", BASE + 5)]}
    with _DB():
        rows = activity.timeline(RUN, live)["rows"]
        body = activity.turn(RUN, "001-00003-qa-story", live)
    assert [(row["status"], row["cost_usd"], row["duration_s"], row["result"]) for row in rows] == [("running", None, None, "Rerunning it.")]
    assert [entry["text"] for entry in body["entries"]] == ["Rerunning it."]


def test_an_unknown_turn_is_not_found_and_a_container_turn_with_no_transcript_is_unreadable(tmp_path: Path) -> None:
    import pytest

    with _DB():
        _seed_run(tmp_path)
        with pytest.raises(activity.TurnNotFound):
            activity.turn(RUN, "009-00009-nothing")
        (turns.transcripts_root() / RUN / f"{SLUG}__{SESSION}" / "transcript.jsonl").unlink()
        with pytest.raises(activity.TurnUnreadable):
            activity.turn(RUN, SLUG, pending=True)


def test_the_endpoints_answer_the_list_the_turn_and_the_missing_turn(tmp_path: Path) -> None:
    with _DB():
        _seed_run(tmp_path)
        with TestClient(app=groom_app.create_app()) as client:
            listing = client.get(f"/api/run/{RUN}/activity")
            one = client.get(f"/api/run/{RUN}/activity/{SLUG}")
            missing = client.get(f"/api/run/{RUN}/activity/009-00009-nothing")
            (turns.transcripts_root() / RUN / f"{SLUG}__{SESSION}" / "transcript.jsonl").unlink()
            broken = client.get(f"/api/run/{RUN}/activity/{SLUG}")
    assert listing.status_code == 200 and [row["slug"] for row in listing.json()["rows"]] == [SLUG]
    assert one.status_code == 200 and one.json()["head"]["node"] == "qa-story"
    assert missing.status_code == 404
    assert broken.status_code == 200 and broken.json()["head"]["matched"] is False


def test_a_turns_result_is_its_recorded_summary_before_the_spans_activity_label(tmp_path: Path) -> None:
    with _DB():
        _seed_run(tmp_path)
        record = turns.transcripts_root() / RUN / f"{SLUG}__{SESSION}"
        (record / "output.json").write_text(json.dumps({"summary": "\nFixed the lockout path.\nMore.", "notes": "ignored"}))
        assert activity.timeline(RUN)["rows"][0]["result"] == "Fixed the lockout path."
        (record / "output.json").write_text(json.dumps({"notes": "Only notes here."}))
        assert activity.timeline(RUN)["rows"][0]["result"] == "Only notes here."
        (record / "output.json").write_text("not json")
        assert activity.timeline(RUN)["rows"][0]["result"] == "Stack up on a free port."


def _seed_old_run(sessions: list[str], span_session: str = SESSION) -> None:
    attrs = {"model": "gpt-5", "backend": "codex", "work_id": "sign-in", "total_cost_usd": 1.5, "duration_ms": 60000}
    if span_session:
        attrs["session.id"] = span_session
    store.insert_spans([
        span("r1", "t1", "", "coder", "run:coder", BASE, 500, {}, 1),
        span("f1", "t1", "r1", "qa", "qa", BASE + 1, 400, {"workhorse.depth": 0}, 1),
        span("s1", "t1", "f1", "work", "work", BASE + 2, 300, STATE, 1),
        span("n1", "t1", "s1", "qa-story", "qa-story", BASE + 3, 200, {"workhorse.depth": 2}, 1),
        span("a1", "t1", "n1", "qa-story", "agent_turn", BASE + 100, 60, attrs, 1),
    ])
    for number, session in enumerate(sessions, start=2):
        slug = f"001-{number:05d}-qa-story"
        _write(turns.transcripts_root() / RUN / f"{slug}__{session}" / "transcript.jsonl", [
            _claude(110, "assistant", f"said in {slug}"),
        ])
        store.insert_turns([{
            "run_id": RUN, "node": "qa-story", "session_id": session, "generation": 1, "seq": number,
            "ts": BASE + 160, "path": f"{RUN}/{slug}__{session}",
        }])


def test_an_old_span_with_one_matching_archived_row_takes_that_rows_slug_and_record() -> None:
    with _DB():
        _seed_old_run([SESSION, "other-session"])
        rows = activity.timeline(RUN)["rows"]
        body = activity.turn(RUN, "001-00002-qa-story")
    assert [(row["slug"], row["matched"], row["flow"], row["pass"]) for row in rows] == [("001-00002-qa-story", True, "qa", 1)]
    assert [entry["text"] for entry in body["entries"]] == ["said in 001-00002-qa-story"]


def test_an_old_span_with_no_matching_row_is_a_row_with_a_stable_key_and_no_record() -> None:
    with _DB():
        _seed_old_run(["other-session"])
        first = activity.timeline(RUN)["rows"]
        second = activity.timeline(RUN)["rows"]
        body = activity.turn(RUN, first[0]["slug"])
    assert [row["slug"] for row in first] == ["unmatched-a1"] == [row["slug"] for row in second]
    assert (first[0]["matched"], first[0]["visit"], first[0]["cost_usd"], first[0]["work_id"]) == (False, "", 1.5, "sign-in")
    assert body["entries"] == [] and body["head"]["matched"] is False


def test_an_old_span_with_several_matching_rows_picks_none_of_them() -> None:
    with _DB():
        _seed_old_run([SESSION, "other-session"], span_session="")
        rows = activity.timeline(RUN)["rows"]
        body = activity.turn(RUN, "unmatched-a1")
    assert [(row["slug"], row["matched"]) for row in rows] == [("unmatched-a1", False)]
    assert body["entries"] == []


def test_an_unmatched_turn_answers_200_with_no_entries_never_a_failure() -> None:
    with _DB():
        _seed_old_run([])
        with TestClient(app=groom_app.create_app()) as client:
            answer = client.get(f"/api/run/{RUN}/activity/unmatched-a1")
    assert answer.status_code == 200 and answer.json()["entries"] == []


def test_a_live_turn_whose_start_the_history_dropped_is_marked_cut() -> None:
    slug = "001-00003-qa-story"
    whole = _live(slug, "Start.", BASE + 1) | {"key": f"{slug}:0"}
    tail = _live(slug, "Later.", BASE + 2) | {"key": f"{slug}:90"}
    with _DB():
        assert activity.turn(RUN, slug, {slug: [whole, tail]})["cut"] is False
        assert activity.turn(RUN, slug, {slug: [tail]})["cut"] is True


def _seed_reading(tmp_path: Path, *, prompt: str | None, records: list[dict]) -> None:
    _seed_run(tmp_path)
    root = turns.transcripts_root() / RUN / f"{SLUG}__{SESSION}"
    _write(root / "transcript.jsonl", records)
    if prompt is not None:
        (root / "prompt.md").write_text(prompt)


def test_a_turn_carries_its_recorded_prompt_and_its_thinking(tmp_path: Path) -> None:
    with _DB():
        _seed_reading(tmp_path, prompt="You own QA for the story.\n\nRun every scenario.", records=[
            _claude(110, "assistant", [{"type": "thinking", "thinking": "The port is taken."}, {"type": "text", "text": "Bringing it up."}]),
        ])
        body = activity.turn(RUN, SLUG)
    assert body["prompt"] == "You own QA for the story.\n\nRun every scenario."
    assert body["thinking"] == "The port is taken."
    assert [entry["role"] for entry in body["entries"]] == ["assistant"]


def test_a_prompt_the_record_lacks_comes_from_the_transcripts_user_messages(tmp_path: Path) -> None:
    with _DB():
        _seed_reading(tmp_path, prompt=None, records=[_claude(105, "user", "Run the plan."), _claude(110, "assistant", "Done.")])
        body = activity.turn(RUN, SLUG)
    assert body["prompt"] == "Run the plan."


def test_a_turn_with_no_recorded_prompt_or_thinking_carries_none(tmp_path: Path) -> None:
    with _DB():
        _seed_reading(tmp_path, prompt=None, records=[_claude(110, "assistant", "Done.")])
        body = activity.turn(RUN, SLUG)
    assert body["prompt"] is None and body["thinking"] is None


def test_a_failed_tool_call_carries_its_whole_output_and_a_passed_one_carries_none(tmp_path: Path) -> None:
    long_output = "\n".join(f"line {number}" for number in range(2000))
    with _DB():
        _seed_reading(tmp_path, prompt=None, records=[
            _claude(110, "assistant", [
                {"type": "tool_use", "id": "a", "name": "Bash", "input": {"command": "make test"}},
                {"type": "tool_use", "id": "b", "name": "Read", "input": {"file_path": "x.py"}},
            ]),
            _claude(112, "user", [
                {"type": "tool_result", "tool_use_id": "a", "content": long_output, "is_error": True},
                {"type": "tool_result", "tool_use_id": "b", "content": "ten lines", "is_error": False},
            ]),
        ])
        failed, passed = activity.turn(RUN, SLUG)["entries"]
    assert failed["failed"] is True and failed["result"] == long_output
    assert passed["failed"] is False and passed["result"] == ""


def test_a_tool_call_carries_its_time_from_its_call_to_its_result(tmp_path: Path) -> None:
    with _DB():
        _seed_reading(tmp_path, prompt=None, records=[
            _claude(110, "assistant", [
                {"type": "tool_use", "id": "a", "name": "Bash", "input": {"command": "make test"}},
                {"type": "tool_use", "id": "b", "name": "Read", "input": {"file_path": "x.py"}},
            ]),
            _claude(134, "user", [{"type": "tool_result", "tool_use_id": "a", "content": "ok"}]),
        ])
        timed, open_call = activity.turn(RUN, SLUG)["entries"]
    assert timed["duration_s"] == 24.0 and open_call["duration_s"] is None


def test_an_acp_call_is_named_by_its_tool_and_timed_from_its_first_update_to_its_last() -> None:
    def record(ts: float, update: dict) -> dict:
        return {"update": update, "_meta": {"ts": ts}}

    updates = [
        record(100.0, {"sessionUpdate": "tool_call", "toolCallId": "c1", "title": "Bash pytest -k locked", "kind": "execute", "status": "in_progress"}),
        record(108.0, {"sessionUpdate": "tool_call_update", "toolCallId": "c1", "status": "failed", "content": [{"type": "content", "content": {"type": "text", "text": "E  assert 401 == 423"}}]}),
    ]
    entries = transcript_parse.from_updates({**record_["update"], "_ts": record_["_meta"]["ts"]} for record_ in updates)
    assert len(entries) == 1
    call = entries[0]
    assert (call["name"], call["summary"], call["failed"], call["duration_s"]) == ("Bash", "pytest -k locked", True, 8.0)
    assert call["result"] == "E  assert 401 == 423"


def test_the_last_assistant_message_of_a_finished_turn_is_final_and_a_running_turns_is_not(tmp_path: Path) -> None:
    with _DB():
        _seed_reading(tmp_path, prompt=None, records=[_claude(110, "assistant", "First."), _claude(115, "assistant", "Last.")])
        finished = activity.turn(RUN, SLUG)["entries"]
        slug = "001-00003-qa-story"
        live = {slug: [_live(slug, "Working.", BASE + 5) | {"key": f"{slug}:0"}]}
        running = activity.turn(RUN, slug, live)["entries"]
    assert [entry["final"] for entry in finished] == [False, True]
    assert [entry["final"] for entry in running] == [False]


def _drop_the_record(tmp_path: Path) -> None:
    import shutil

    _seed_run(tmp_path)
    shutil.rmtree(turns.transcripts_root() / RUN / f"{SLUG}__{SESSION}")


def test_a_finished_native_turn_with_no_record_reads_as_unmatched_never_a_failure(tmp_path: Path) -> None:
    with _DB():
        _drop_the_record(tmp_path)
        body = activity.turn(RUN, SLUG)
        with TestClient(app=groom_app.create_app()) as client:
            answer = client.get(f"/api/run/{RUN}/activity/{SLUG}")
    assert body["entries"] == [] and body["head"]["matched"] is False
    assert answer.status_code == 200 and answer.json()["head"]["matched"] is False


def test_a_finished_native_turn_whose_record_holds_no_transcript_reads_as_unmatched(tmp_path: Path) -> None:
    with _DB():
        _seed_run(tmp_path)
        (turns.transcripts_root() / RUN / f"{SLUG}__{SESSION}" / "transcript.jsonl").unlink()
        body = activity.turn(RUN, SLUG)
    assert body["entries"] == [] and body["head"]["matched"] is False


def test_a_finished_container_turn_whose_records_are_not_pulled_still_answers_503(tmp_path: Path) -> None:
    import pytest

    with _DB():
        _drop_the_record(tmp_path)
        with pytest.raises(activity.TurnUnreadable):
            activity.turn(RUN, SLUG, pending=True)
        state.WORKFLOWS[RUN] = WorkflowContainer(container_id=RUN, name="coder")
        try:
            with TestClient(app=groom_app.create_app()) as client:
                answer = client.get(f"/api/run/{RUN}/activity/{SLUG}")
        finally:
            state.WORKFLOWS.pop(RUN, None)
    assert answer.status_code == 503
