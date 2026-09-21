"""The channel an operator reaches a live run over, and the one wait built on it."""

from __future__ import annotations

import json
import socket
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _fakes import FakeClock  # noqa: E402
from workhorse import control  # noqa: E402
from workhorse.control import (  # noqa: E402
    NULL_CHANNEL,
    FakeChannel,
    Request,
    SocketChannel,
    wait_until,
)


def test_a_message_sent_to_a_live_run_arrives_with_its_reply() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        channel = SocketChannel.open(run_dir)
        answered: list[dict[str, object]] = []

        def client() -> None:
            answered.append(control.send(run_dir, Request(action="reload")))

        caller = threading.Thread(target=client)
        caller.start()
        try:
            request = wait_until(None, timeout=5.0, clock=FakeClock(), channel=channel, tick=0.05)
            assert request is not None
            assert request.action == "reload"
            channel.reply({"state": "review"})
        finally:
            caller.join(timeout=5)
            channel.close()

        assert answered == [{"state": "review"}]


def test_a_request_ends_a_wait_that_had_hours_left() -> None:
    clock = FakeClock()
    channel = FakeChannel(Request(action="reload", core=True))
    request = wait_until(None, timeout=500_000.0, clock=clock, channel=channel)
    assert request is not None and request.core
    assert clock.slept == []


def test_a_wait_with_no_channel_still_sleeps_through_its_clock() -> None:
    clock = FakeClock()
    assert wait_until(None, timeout=3.0, clock=clock, channel=NULL_CHANNEL, tick=1.0) is None
    assert clock.slept == [1.0, 1.0, 1.0]


def test_a_condition_already_true_costs_no_wait_at_all() -> None:
    clock = FakeClock()
    assert wait_until(lambda: True, timeout=900.0, clock=clock) is None
    assert clock.slept == []


def test_the_content_check_alone_ends_the_wait_with_no_message_sent() -> None:
    answered = {"yet": False}
    ticks: list[float] = []

    class Watching(FakeClock):
        def sleep(self, seconds: float) -> None:
            ticks.append(seconds)
            if len(ticks) == 2:
                answered["yet"] = True
            super().sleep(seconds)

    clock = Watching()
    assert wait_until(lambda: answered["yet"], timeout=100.0, clock=clock, tick=1.0) is None
    assert ticks == [1.0, 1.0]


def test_a_socket_left_by_a_killed_run_is_rebound_rather_than_fatal() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        first = SocketChannel.open(run_dir)
        path = first.path
        first._listener.close()
        assert path.exists()

        second = SocketChannel.open(run_dir)
        try:
            assert second.path == path
            assert control.send(run_dir, Request(action="status"), timeout=1.0) == {}
        finally:
            second.close()


def test_a_second_run_on_the_same_dir_is_refused_rather_than_stomped() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        channel = SocketChannel.open(run_dir)
        try:
            raised = False
            try:
                SocketChannel.open(run_dir)
            except OSError:
                raised = True
            assert raised
        finally:
            channel.close()


def test_a_run_dir_too_long_for_sun_path_still_gets_a_channel() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp).joinpath(*[f"segment-{index:02d}" for index in range(8)])
        run_dir.mkdir(parents=True)
        assert len(str(run_dir / control.SOCKET_FILE)) > 100
        channel = SocketChannel.open(run_dir)
        try:
            pointer = run_dir / control.POINTER_FILE
            assert pointer.exists()
            assert Path(pointer.read_text(encoding="utf-8").strip()) == channel.path
            assert control.send(run_dir, Request(action="status"), timeout=1.0) == {}
        finally:
            channel.close()
        assert not channel.path.exists()


def test_nothing_a_client_sends_can_end_the_run() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        channel = SocketChannel.open(run_dir)
        try:
            for payload in (b"not json\n", b'["a list"]\n', b""):
                client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                client.settimeout(1.0)
                client.connect(str(channel.path))
                if payload:
                    client.sendall(payload)
                client.close()
                assert channel.take() is None

            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.settimeout(1.0)
            client.connect(str(channel.path))
            client.sendall((Request(action="reload").to_json() + "\n").encode("utf-8"))
            request = channel.take()
            assert request is not None and request.action == "reload"
            client.close()
        finally:
            channel.close()


def test_a_verb_a_run_is_too_old_to_know_is_delivered_not_rejected() -> None:
    request = Request.from_raw(json.loads('{"action": "quiesce", "unheard_of": 3}'))
    assert request is not None
    assert request.action == "quiesce"
    assert request.cuts_the_turn


def test_asking_a_run_that_is_not_running_says_so_immediately() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        raised = False
        try:
            control.send(Path(tmp), Request(action="status"), timeout=1.0)
        except FileNotFoundError:
            raised = True
        assert raised


def test_status_is_answered_under_every_wait_and_ends_none_of_them() -> None:
    """The verb this module answers itself, and the reason it does."""
    clock = FakeClock()
    control.report_with(lambda: {"attached": True, "state": "Qa.plan_story"})
    try:
        channel = FakeChannel(Request(action="status"))
        ended = wait_until(None, timeout=120.0, clock=clock, channel=channel, tick=30.0)
    finally:
        control.report_with(None)

    assert ended is None
    assert channel.replies == [{"attached": True, "state": "Qa.plan_story"}]
    assert sum(clock.slept) == 120.0


def test_questions_is_answered_under_every_wait_and_ends_none_of_them() -> None:
    """The second query verb, and the discovery half of the socket gate protocol."""
    clock = FakeClock()
    pending: list[dict[str, object]] = [
        {"path": "/ws/context.md", "kind": "operator", "since": "t0"}
    ]
    control.questions_with(lambda: list(pending))
    try:
        channel = FakeChannel(Request(action="questions"))
        ended = wait_until(None, timeout=120.0, clock=clock, channel=channel, tick=30.0)
    finally:
        control.questions_with(None)

    assert ended is None
    assert channel.replies == [{"ok": True, "questions": pending}]
    assert sum(clock.slept) == 120.0


def test_a_run_blocked_on_nothing_answers_an_empty_list() -> None:
    channel = FakeChannel(Request(action="questions"))
    assert wait_until(None, timeout=1.0, clock=FakeClock(), channel=channel, tick=1.0) is None
    assert channel.replies == [{"ok": True, "questions": []}]


def test_a_questions_listing_that_raises_answers_the_failure() -> None:
    channel = FakeChannel(Request(action=control.QUESTIONS))
    control.arm(channel)
    control.questions_with(lambda: (_ for _ in ()).throw(OSError("gate file vanished")))
    try:
        assert control.take() is None
    finally:
        control.arm(None)

    assert channel.replies == [{"ok": False, "error": "OSError: gate file vanished"}]


def test_disarming_forgets_what_the_last_run_was_asking() -> None:
    control.arm(FakeChannel())
    control.questions_with(lambda: [{"path": "/ws/context.md"}])
    control.arm(None)

    channel = FakeChannel(Request(action="questions"))
    assert wait_until(None, timeout=1.0, clock=FakeClock(), channel=channel, tick=1.0) is None
    assert channel.replies == [{"ok": True, "questions": []}]


def test_the_answer_fields_survive_the_wire() -> None:
    sent = Request(action=control.ANSWER, path="/ws/context.md", body="ship it\nsecond line")
    received = Request.from_raw(json.loads(sent.to_json()))
    assert received is not None
    assert received.action == control.ANSWER
    assert received.path == "/ws/context.md"
    assert received.body == "ship it\nsecond line"


def test_a_client_that_never_heard_of_the_answer_fields_still_parses() -> None:
    request = Request.from_raw(json.loads('{"action": "reload"}'))
    assert request is not None
    assert request.path == "" and request.body == ""


def test_a_process_with_no_run_attached_says_so_rather_than_going_quiet() -> None:
    channel = FakeChannel(Request(action="status"))
    assert wait_until(None, timeout=1.0, clock=FakeClock(), channel=channel, tick=1.0) is None
    assert channel.replies == [{"attached": False}]


def test_a_describe_that_raises_answers_the_query_instead_of_ending_the_run():
    """The describe callable is invoked from inside the streaming loop — the deepest and longest-lived frame in the engine — so an exception escaping it would end a week-long run over a question whose whole premise is that asking changes nothing."""
    channel = FakeChannel(control.Request(action=control.STATUS))
    control.arm(channel)
    control.report_with(lambda: (_ for _ in ()).throw(NameError("no _status_report")))
    try:
        assert control.take() is None
    finally:
        control.arm(None)

    assert channel.replies == [
        {"attached": True, "error": "NameError: no _status_report"}
    ], channel.replies


def test_disarming_forgets_how_the_last_run_described_itself() -> None:
    control.arm(FakeChannel())
    control.report_with(lambda: {"attached": True, "state": "Qa.plan_story"})
    control.arm(None)

    channel = FakeChannel(Request(action="status"))
    assert wait_until(None, timeout=1.0, clock=FakeClock(), channel=channel, tick=1.0) is None
    assert channel.replies == [{"attached": False}]


def test_a_reply_far_larger_than_one_packet_arrives_whole() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        channel = SocketChannel.open(run_dir)
        question = "x" * 698_000
        answered: list[dict[str, object]] = []

        def client() -> None:
            answered.append(control.send(run_dir, Request(action="reload"), timeout=10.0))

        caller = threading.Thread(target=client)
        caller.start()
        try:
            request = wait_until(None, timeout=5.0, clock=FakeClock(), channel=channel, tick=0.05)
            assert request is not None
            channel.reply({"ok": True, "questions": [{"question": question}]})
        finally:
            caller.join(timeout=10)
            channel.close()

        assert answered == [{"ok": True, "questions": [{"question": question}]}]


def test_a_message_over_its_limit_is_refused_rather_than_truncated() -> None:
    left, right = socket.socketpair()
    try:
        right.sendall(b"y" * 4096)
        try:
            control._read_message(left, limit=1024)
        except control.ControlProtocolError:
            pass
        else:
            raise AssertionError("an over-limit message was accepted")
    finally:
        left.close()
        right.close()


def test_a_message_is_reassembled_across_however_many_packets_it_takes() -> None:
    left, right = socket.socketpair()
    try:
        body = json.dumps({"chunk": "a" * 30_000})
        for i in range(0, len(body), 997):
            right.sendall(body[i : i + 997].encode("utf-8"))
        right.sendall(b"\n")
        assert json.loads(control._read_message(left, limit=control.REPLY_LIMIT)) == json.loads(body)
    finally:
        left.close()
        right.close()


def test_a_request_over_its_limit_is_ignored_and_the_run_survives() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        channel = SocketChannel.open(run_dir)
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.settimeout(5.0)
            client.connect(str(channel.path))
            try:
                client.sendall(b"z" * (control.REQUEST_LIMIT + 4096))
            except OSError:
                pass
            assert channel.take() is None
            client.close()
        finally:
            channel.close()


if __name__ == "__main__":
    test_a_message_sent_to_a_live_run_arrives_with_its_reply()
    test_a_request_ends_a_wait_that_had_hours_left()
    test_a_wait_with_no_channel_still_sleeps_through_its_clock()
    test_a_condition_already_true_costs_no_wait_at_all()
    test_the_content_check_alone_ends_the_wait_with_no_message_sent()
    test_a_socket_left_by_a_killed_run_is_rebound_rather_than_fatal()
    test_a_second_run_on_the_same_dir_is_refused_rather_than_stomped()
    test_a_run_dir_too_long_for_sun_path_still_gets_a_channel()
    test_nothing_a_client_sends_can_end_the_run()
    test_a_verb_a_run_is_too_old_to_know_is_delivered_not_rejected()
    test_asking_a_run_that_is_not_running_says_so_immediately()
    test_status_is_answered_under_every_wait_and_ends_none_of_them()
    test_questions_is_answered_under_every_wait_and_ends_none_of_them()
    test_a_run_blocked_on_nothing_answers_an_empty_list()
    test_a_questions_listing_that_raises_answers_the_failure()
    test_disarming_forgets_what_the_last_run_was_asking()
    test_the_answer_fields_survive_the_wire()
    test_a_client_that_never_heard_of_the_answer_fields_still_parses()
    test_a_process_with_no_run_attached_says_so_rather_than_going_quiet()
    test_a_describe_that_raises_answers_the_query_instead_of_ending_the_run()
    test_disarming_forgets_how_the_last_run_described_itself()
    test_a_reply_far_larger_than_one_packet_arrives_whole()
    test_a_message_over_its_limit_is_refused_rather_than_truncated()
    test_a_message_is_reassembled_across_however_many_packets_it_takes()
    test_a_request_over_its_limit_is_ignored_and_the_run_survives()
    print("ok")
