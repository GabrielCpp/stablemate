"""The channel an operator reaches a live run over, and the one wait built on it.

What is asserted here is the transport and the primitive, not what any verb means — a
`reload` is tested next to the driver that acts on it. The four properties that make this
worth replacing a request file with:

- **A message wakes a wait.** The failure that motivated the channel was a run asleep in
  a six-day spending-cap pause with nothing polling anything, so "the wait ends when the
  operator speaks" is the whole feature.
- **A wait with no channel behaves exactly as it did before.** Every unit test in this
  suite waits through an injected clock, and `NullChannel` has to keep that true or the
  primitive is a rewrite of the suite rather than of the transport.
- **The content check alone is sufficient.** The operator gate's answer is a file a human
  edits; a run must resume on it whether or not anyone sends a message.
- **Nothing a client sends can end the run.** Malformed, truncated, unknown verb — the
  worst case is that it is ignored.

Run: uv run python tests/test_control_channel.py   (or via pytest)
"""

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
    # The cap-pause case: the wait was told to last a very long time, and the operator's
    # message is what actually ends it.
    clock = FakeClock()
    channel = FakeChannel(Request(action="reload", core=True))
    request = wait_until(None, timeout=500_000.0, clock=clock, channel=channel)
    assert request is not None and request.core
    assert clock.slept == []


def test_a_wait_with_no_channel_still_sleeps_through_its_clock() -> None:
    # The regression guard for every existing test in this suite: an unarmed process must
    # wait exactly as it did before the channel existed, through the injected clock.
    clock = FakeClock()
    assert wait_until(None, timeout=3.0, clock=clock, channel=NULL_CHANNEL, tick=1.0) is None
    assert clock.slept == [1.0, 1.0, 1.0]


def test_a_condition_already_true_costs_no_wait_at_all() -> None:
    clock = FakeClock()
    assert wait_until(lambda: True, timeout=900.0, clock=clock) is None
    assert clock.slept == []


def test_the_content_check_alone_ends_the_wait_with_no_message_sent() -> None:
    # The operator answers by saving a file and sends nothing. The slow re-read is what
    # makes that work, which is why it is half the primitive rather than a fallback.
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
        # SIGKILL: the process is gone, the socket file is not.
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
            # Two runs sharing a run dir is the bug; taking the channel from the live one
            # would hide it and leave the first run unreachable.
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

            # And the channel still works afterwards.
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
    # A newer CLI must never be able to kill an older run. Parsing keeps the verb it does
    # not recognise; ignoring it is the consumer's decision, made after delivery.
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
        # The honest answer, and the one a request file could never give: a channel exists
        # only while the run does, so "nobody is there" is known at the moment of asking.
        assert raised


def test_status_is_answered_under_every_wait_and_ends_none_of_them() -> None:
    """The verb this module answers itself, and the reason it does.

    Every other request has to reach a consumer, because only a consumer knows whether
    its wait may end. `status` is the one that must reach an operator *without* ending
    anything: the run it is most worth asking is the one asleep for six days in a cap
    window, and waking that wait to answer "still capped" would spend the answer.
    """
    clock = FakeClock()
    control.report_with(lambda: {"attached": True, "state": "Qa.plan_story"})
    try:
        channel = FakeChannel(Request(action="status"))
        ended = wait_until(None, timeout=120.0, clock=clock, channel=channel, tick=30.0)
    finally:
        control.report_with(None)

    assert ended is None                       # the wait ran to term
    assert channel.replies == [{"attached": True, "state": "Qa.plan_story"}]
    assert sum(clock.slept) == 120.0           # …and slept every second of it


def test_questions_is_answered_under_every_wait_and_ends_none_of_them() -> None:
    """The second query verb, and the discovery half of the socket gate protocol.

    A poller asking "what is this run blocked on" must get its answer from under any
    wait — including a wait that is not the operator gate — and the asking must never
    be the thing that ends one.
    """
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
    # The well-formed "no gate here": a reconciling poller asks every live run, and most
    # of them are working. Saying so is the answer, not an error.
    channel = FakeChannel(Request(action="questions"))
    assert wait_until(None, timeout=1.0, clock=FakeClock(), channel=channel, tick=1.0) is None
    assert channel.replies == [{"ok": True, "questions": []}]


def test_a_questions_listing_that_raises_answers_the_failure() -> None:
    # Same containment as the status reporter, same reason: the callable runs inside the
    # deepest wait there is, and a query may not be able to end the run.
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
    # `path` says which gate, `body` carries the operator's prose — both have to arrive
    # exactly as sent, through to_json and from_raw like every other field.
    sent = Request(action=control.ANSWER, path="/ws/context.md", body="ship it\nsecond line")
    received = Request.from_raw(json.loads(sent.to_json()))
    assert received is not None
    assert received.action == control.ANSWER
    assert received.path == "/ws/context.md"
    assert received.body == "ship it\nsecond line"


def test_a_client_that_never_heard_of_the_answer_fields_still_parses() -> None:
    # The one-directional forgiveness rule, in the new direction: an older CLI's message
    # has no `path`/`body`, and both default to empty rather than failing the parse.
    request = Request.from_raw(json.loads('{"action": "reload"}'))
    assert request is not None
    assert request.path == "" and request.body == ""


def test_a_process_with_no_run_attached_says_so_rather_than_going_quiet() -> None:
    # `status` is answerable by construction, including from a process that is not a run:
    # an unanswered query is indistinguishable from a wedged one, which is the state an
    # operator asks about.
    channel = FakeChannel(Request(action="status"))
    assert wait_until(None, timeout=1.0, clock=FakeClock(), channel=channel, tick=1.0) is None
    assert channel.replies == [{"attached": False}]


def test_a_describe_that_raises_answers_the_query_instead_of_ending_the_run():
    """The describe callable is invoked from inside the streaming loop — the deepest and
    longest-lived frame in the engine — so an exception escaping it would end a week-long
    run over a question whose whole premise is that asking changes nothing. It is answered
    with the failure instead, which is also what makes the failure visible at all: this
    guard exists because a describe closure referencing an undefined name took a live
    multi-hour run down the first time anyone asked it where it was."""
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
    # Not the previous run's position: a process-wide reporter outliving its run would
    # answer for a run that has already ended.
    assert channel.replies == [{"attached": False}]


def test_a_reply_far_larger_than_one_packet_arrives_whole() -> None:
    # The regression this file did not have: a stream socket splits a big reply across
    # many recv()s, and the reader has to put it back together. 698 KB is the size a real
    # `questions` reply reached — it quotes the gate file, and an operator gate re-armed
    # across a long run gets there — at which point the old 64 KiB reader returned a
    # truncated prefix that failed to parse, and every caller read that as "no question".
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
    # The defect itself. The old reader stopped at its bound and returned the bytes it
    # had, and a prefix of a JSON object is not a shorter message — it is a corrupt one
    # that parses to nothing. Every caller then read "the peer said nothing", which is
    # the opposite of what happened. Refusing is what makes the two distinguishable.
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
    # A stream socket delivers bytes, not messages: the newline is the frame, and a
    # payload written in pieces has to come back out as one. Under the limit, so this is
    # the framing on its own with no bound involved.
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
    # The bound that is still a bound: anything reaching the socket may send a request,
    # so an unterminated one must not be an unbounded allocation in the run. Ignored, as
    # every other malformed message is — the worst a client can cause is nothing.
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
                pass  # the run hung up on it, which is the point
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
