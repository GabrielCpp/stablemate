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
            answered.append(control.send(run_dir, Request(action="status")))

        caller = threading.Thread(target=client)
        caller.start()
        try:
            request = wait_until(None, timeout=5.0, clock=FakeClock(), channel=channel, tick=0.05)
            assert request is not None
            assert request.action == "status"
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
    print("ok")
