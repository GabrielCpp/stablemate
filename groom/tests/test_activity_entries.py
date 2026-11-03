"""A step and an operator gate of the Activity timeline, read in full."""
from __future__ import annotations

from typing import Any

import pytest
from test_activity_groups import BASE, RETRIED, _attrs, _bare_states, _seed
from test_run_clock import RUN, _DB, span

from groom import activity, store

GATE_FILE = "gates/qa-story.md"
ASKED = "Should a locked account answer 401 or 423?"
GATE_TEXT = f"STATUS: ANSWERED\n\n## Questions from the agent\n\n{ASKED}\n\nUse 423, and say why in the body.\n"


def _logs(node: str, at: float, lines: list[tuple[str, str]]) -> None:
    store.insert_logs([
        {"run_id": RUN, "node": node, "severity": level, "body": body, "ts": at + number * 0.5}
        for number, (level, body) in enumerate(lines)
    ])


def _wait(span_id: str, node: str, at: float, seconds: float, **extra: object) -> dict:
    attrs = {"workhorse.span_kind": "wait", "workhorse.wait_kind": "operator", "workhorse.gate_path": GATE_FILE, "workhorse.gate_question": ASKED, "workhorse.wait_outcome": "completed"} | _attrs("sign-in") | extra
    return span(span_id, "t1", "sa", node, "wait:operator", at, seconds, attrs, 1, RUN)


def _read(key: str, **given: Any) -> dict:
    return activity.entry(RUN, key, **given)


def test_a_failed_step_reads_with_its_head_and_error_class() -> None:
    with _DB():
        _seed()
        store.insert_spans([span("e1", "t1", "sa", "build", "build", BASE + 30, 4, {"error.class": "StackStartFailed", "status_message": "stack did not start"} | _attrs("sign-in"), 1) | {"status": "ERROR"}])
        reading = _read("failed:e1")
    head = reading["head"]
    assert (head["name"], head["work_id"], head["flow"], head["pass"], head["state"]) == ("build", "sign-in", "qa", 1, "failed")
    assert head["duration_s"] == 4 and head["error_class"] == "StackStartFailed"


def test_a_failed_step_reads_its_full_error_text() -> None:
    long = "stack did not start\n" + "\n".join(f"line {number}: connection refused" for number in range(40))
    with _DB():
        _seed()
        store.insert_spans([span("e1", "t1", "sa", "build", "build", BASE + 30, 4, {"status_message": long} | _attrs("sign-in"), 1) | {"status": "ERROR"}])
        reading = _read("failed:e1")
    assert reading["error"] == long


def test_a_step_reads_its_logs_with_time_level_node_and_message() -> None:
    with _DB():
        _seed()
        _logs("test", BASE + 26, [("INFO", "starting"), ("ERROR", "2 tests failed")])
        _logs("test", BASE + 900, [("INFO", "another visit")])
        _logs("lint", BASE + 26, [("INFO", "another node")])
        reading = _read("failed:a-test")
    assert reading["logs"] == [
        {"ts": BASE + 26, "level": "INFO", "node": "test", "body": "starting"},
        {"ts": BASE + 26.5, "level": "ERROR", "node": "test", "body": "2 tests failed"},
    ]
    assert reading["cut"] is False


def test_a_step_that_recorded_no_logs_reads_an_empty_list() -> None:
    with _DB():
        _seed()
        reading = _read("failed:a-test")
    assert reading["logs"] == [] and reading["cut"] is False


def test_a_step_says_what_came_next_and_the_key_of_that_row() -> None:
    with _DB():
        _seed()
        after = _read("failed:a-test")["next"]
        last = _read("step:a-pack")["next"]
    assert after["key"] == "step:a-pack" and after["noun"] == "step" and "pack ran next and passed" in after["text"]
    assert last["key"] == RETRIED and last["noun"] == "turn" and "qa-story ran next, an agent turn" in last["text"]


def test_a_step_with_nothing_after_it_says_nothing_came_after() -> None:
    with _DB():
        _seed()
        store.insert_spans([span("z1", "t1", "r1", "wrap", "wrap", BASE + 3000, 2, _attrs("reset"), 1)])
        reading = _read("step:z1")
    assert reading["next"]["key"] == "" and reading["next"]["text"] == "Nothing came after this."


def test_a_running_step_reads_running_with_nothing_next() -> None:
    standing = {"node": "build", "since_ts": BASE + 5000, "wait_kind": "", "turn_active": False, "path": "", "question": ""}
    with _DB():
        _seed()
        _logs("build", BASE + 5001, [("INFO", "compiling")])
        reading = _read("step:running:build", standing=standing)
    assert reading["head"]["state"] == "running" and reading["head"]["duration_s"] is None
    assert [line["body"] for line in reading["logs"]] == ["compiling"]
    assert reading["next"]["key"] == "" and reading["next"]["text"] == "Nothing yet. This is still running."


def test_a_running_step_that_ended_reads_as_the_finished_step() -> None:
    with _DB():
        _seed()
        reading = _read("step:running:test")
    assert reading["key"] == "failed:a-test" and reading["head"]["state"] == "failed"


def test_a_passed_step_reads_its_logs_and_what_came_next() -> None:
    with _DB():
        _seed()
        _logs("lint", BASE + 12, [("INFO", "clean")])
        reading = _read("step:a-lint")
    assert reading["head"]["state"] == "passed" and reading["error"] is None
    assert [line["body"] for line in reading["logs"]] == ["clean"]
    assert reading["next"]["key"] == "step:a-build"


def test_an_answered_gate_reads_its_question_answer_and_how_long_it_waited() -> None:
    with _DB():
        _seed()
        store.insert_spans([_wait("w1", "qa-story", BASE + 100, 540)])
        reading = _read("gate:qa-story#1", read=lambda path: GATE_TEXT if path == GATE_FILE else None)
    assert reading["question"] == ASKED and reading["answer"] == "Use 423, and say why in the body."
    assert reading["head"]["state"] == "answered" and reading["head"]["waited_s"] == 540
    assert reading["head"]["ended_ts"] == BASE + 640 and reading["head"]["path"] == GATE_FILE


def test_an_older_gate_finds_its_answer_above_the_newer_question() -> None:
    again = GATE_TEXT.replace("STATUS: ANSWERED", "STATUS: AWAITING_OPERATOR") + "\n## Questions from the agent\n\nAnd the error code?\n"
    with _DB():
        _seed()
        store.insert_spans([_wait("w1", "qa-story", BASE + 100, 540)])
        reading = _read("gate:qa-story#1", read=lambda _path: again)
    assert reading["answer"] == "Use 423, and say why in the body."


def _twice(first: str, second: str) -> str:
    return f"STATUS: ANSWERED\n\n## Questions from the agent\n\n{ASKED}\n\n{first}\n\n## Questions from the agent\n\n{ASKED}\n\n{second}\n"


def test_a_question_asked_twice_gives_each_gate_the_answer_of_its_own_asking() -> None:
    text = _twice("First answer.", "Second answer.")
    with _DB():
        _seed()
        store.insert_spans([_wait("w1", "qa-story", BASE + 100, 200), _wait("w2", "qa-story", BASE + 400, 200)])
        first = _read("gate:qa-story#1", read=lambda _path: text)
        second = _read("gate:qa-story#2", read=lambda _path: text)
    assert (first["answer"], second["answer"]) == ("First answer.", "Second answer.")


def test_a_gate_whose_asking_the_file_no_longer_holds_reads_no_answer_and_never_a_neighbours() -> None:
    text = GATE_TEXT
    with _DB():
        _seed()
        store.insert_spans([_wait("w1", "qa-story", BASE + 100, 200), _wait("w2", "qa-story", BASE + 400, 200)])
        first = _read("gate:qa-story#1", read=lambda _path: text)
        second = _read("gate:qa-story#2", read=lambda _path: text)
    assert first["answer"] == "" and first["head"]["state"] == "answered" and first["taken"] is True
    assert second["answer"] == "Use 423, and say why in the body."


def test_a_wait_that_was_interrupted_reads_no_answer_and_the_wait_that_completed_reads_it() -> None:
    with _DB():
        _seed()
        store.insert_spans([
            _wait("w1", "qa-story", BASE + 100, 20, **{"workhorse.wait_outcome": "interrupted"}),
            _wait("w2", "read-operator", BASE + 200, 30),
        ])
        gone = _read("gate:qa-story#1", read=lambda _path: GATE_TEXT)
        taken = _read("gate:read-operator#1", read=lambda _path: GATE_TEXT)
    assert gone["head"]["state"] == "ended" and gone["answer"] == ""
    assert taken["answer"] == "Use 423, and say why in the body."


def test_an_open_gate_reads_its_question_and_that_it_is_not_answered() -> None:
    standing = {"node": "qa-story", "since_ts": BASE + 5000, "wait_kind": "operator", "turn_active": False, "path": GATE_FILE, "question": ASKED}
    waiting = GATE_TEXT.replace("STATUS: ANSWERED", "STATUS: AWAITING_OPERATOR").replace("\nUse 423, and say why in the body.\n", "")
    with _DB():
        _seed()
        reading = _read("gate:qa-story#1", standing=standing, read=lambda _path: waiting)
    assert reading["head"]["state"] == "open" and reading["head"]["waited_s"] is None
    assert reading["question"] == ASKED and reading["answer"] == "" and reading["taken"] is False


def test_an_open_gate_keeps_its_key_when_it_is_answered() -> None:
    standing = {"node": "qa-story", "since_ts": BASE + 5000, "wait_kind": "operator", "turn_active": False, "path": GATE_FILE, "question": ASKED}
    with _DB():
        _seed()
        before = [one["key"] for item in activity.timeline(RUN, standing=standing)["items"] for pas in item["passes"] for one in pas["entries"] if one["kind"] == "gate"]
        store.insert_spans([_wait("w1", "qa-story", BASE + 5000, 60)])
        after = [one["key"] for item in activity.timeline(RUN)["items"] for pas in item["passes"] for one in pas["entries"] if one["kind"] == "gate"]
    assert "gate:qa-story#1" in before and "gate:qa-story#1" in after


def test_an_open_gate_whose_file_is_already_answered_reads_as_answered_and_not_taken() -> None:
    standing = {"node": "qa-story", "since_ts": BASE + 5000, "wait_kind": "operator", "turn_active": False, "path": GATE_FILE, "question": ASKED}
    with _DB():
        _seed()
        reading = _read("gate:qa-story#1", standing=standing, read=lambda _path: GATE_TEXT)
    assert reading["head"]["state"] == "answered" and reading["taken"] is False
    assert reading["answer"] == "Use 423, and say why in the body."


def test_the_timeline_lists_the_running_step_and_the_open_gate_as_rows() -> None:
    with _DB():
        _seed()
        running = {"node": "build", "since_ts": BASE + 5000, "wait_kind": "", "turn_active": False, "path": "", "question": ""}
        waiting = running | {"node": "qa-story", "wait_kind": "operator", "question": ASKED}
        busy = running | {"turn_active": True}
        found = {
            name: [one for item in activity.timeline(RUN, standing=standing)["items"] for pas in item["passes"] for one in pas["entries"] if one["kind"] in ("doing", "gate") and one["ts"] == BASE + 5000]
            for name, standing in (("running", running), ("waiting", waiting), ("busy", busy))
        }
    assert [(one["kind"], one["key"]) for one in found["running"]] == [("doing", "step:running:build")]
    assert [(one["kind"], one["key"], one["result"]) for one in found["waiting"]] == [("gate", "gate:qa-story#1", f"{ASKED} Waiting")]
    assert found["busy"] == []


@pytest.mark.parametrize("key", ["step:nope", "failed:nope", "gate:resolve#9", "gate:resolve", "gate:#1", "step:running:nope", "turn:x"])
def test_an_unknown_key_is_not_found(key: str) -> None:
    with _DB():
        _seed()
        with pytest.raises(activity.EntryNotFound):
            _read(key)


def test_a_state_step_reads_with_its_head_its_logs_and_what_came_next() -> None:
    with _DB():
        _seed()
        _bare_states()
        _logs("bring_up_stack", BASE + 51, [("INFO", "compose up")])
        reading = _read("step:bs")
    head = reading["head"]
    assert (head["name"], head["work_id"], head["flow"], head["pass"], head["state"], head["duration_s"]) == ("bring_up_stack", "sign-in", "qa", 1, "passed", 78)
    assert [line["body"] for line in reading["logs"]] == ["compose up"]
    assert reading["next"]["key"] == "step:rt" and reading["next"]["text"] == "route ran next and passed."


def test_a_failed_state_step_reads_its_error() -> None:
    with _DB():
        _seed()
        _bare_states()
        reading = _read("failed:vf")
    assert reading["error"] == "stack unreachable" and reading["head"]["state"] == "failed"
