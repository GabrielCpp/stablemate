"""Tests for groom.sidecar_hub: the host-side registry of persistent sidecar
sessions and its correlation-id RPC. A fake sender captures the frames the hub
would send over the socket and lets the test drive replies, so nothing touches a
real WebSocket.

Run: uv run python tests/test_sidecar_hub.py   (or via pytest)
"""
from __future__ import annotations

import asyncio

from groom import sidecar_hub
from groom.sidecar_hub import SidecarConnection, SidecarError


class _FakeSocket:
    def __init__(self):
        self.sent: list[dict] = []

    async def send_json(self, data):
        self.sent.append(data)


def _reset():
    sidecar_hub.CONNECTIONS.clear()


def test_rpc_sends_request_and_returns_resolved_data():
    _reset()

    async def _scenario():
        sock = _FakeSocket()
        conn = SidecarConnection("abc123", sock)

        async def _reply():
            # Wait until the request frame has been sent, then answer it.
            while not sock.sent:
                await asyncio.sleep(0)
            corr = sock.sent[0]["id"]
            conn.resolve(corr, ok=True, data={"paths": ["a.py", "b.py"]})

        reply = asyncio.create_task(_reply())
        result = await conn.rpc("getTree", {"repo": "predykt"})
        await reply
        return sock.sent[0], result

    frame, result = asyncio.run(_scenario())
    assert frame == {"type": "rpc", "id": "1", "method": "getTree", "params": {"repo": "predykt"}}
    assert result == {"paths": ["a.py", "b.py"]}


def test_rpc_error_result_raises_sidecar_error():
    _reset()

    async def _scenario():
        sock = _FakeSocket()
        conn = SidecarConnection("abc123", sock)

        async def _reply():
            while not sock.sent:
                await asyncio.sleep(0)
            conn.resolve(sock.sent[0]["id"], ok=False, error="unsafe path")

        asyncio.create_task(_reply())
        try:
            await conn.rpc("getFile", {"path": "../etc/passwd"})
        except SidecarError as exc:
            return str(exc)
        return None

    message = asyncio.run(_scenario())
    assert message == "unsafe path"


def test_rpc_times_out_when_no_reply():
    _reset()

    async def _scenario():
        conn = SidecarConnection("abc123", _FakeSocket())
        try:
            await conn.rpc("getDiff", {"repo": "x"}, timeout=0.01)
        except SidecarError:
            return True
        return False

    assert asyncio.run(_scenario()) is True


def test_correlation_ids_increment_per_connection():
    _reset()

    async def _scenario():
        sock = _FakeSocket()
        conn = SidecarConnection("abc123", sock)
        # Fire two RPCs that both time out; we only care about the ids sent.
        await asyncio.gather(
            _swallow(conn.rpc("getTree", {}, timeout=0.01)),
            _swallow(conn.rpc("getTree", {}, timeout=0.01)),
        )
        return sorted(frame["id"] for frame in sock.sent)

    ids = asyncio.run(_scenario())
    assert ids == ["1", "2"]


async def _swallow(coro):
    try:
        await coro
    except SidecarError:
        pass


def test_resolve_is_ignored_after_timeout():
    _reset()

    async def _scenario():
        conn = SidecarConnection("abc123", _FakeSocket())
        try:
            await conn.rpc("getTree", {}, timeout=0.01)
        except SidecarError:
            pass
        # A late reply for a request whose future is already gone must not raise.
        conn.resolve("1", ok=True, data={"paths": []})
        return True

    assert asyncio.run(_scenario()) is True


def test_register_displaces_and_fails_prior_connection():
    _reset()

    async def _scenario():
        first = SidecarConnection("abc123", _FakeSocket())
        sidecar_hub.register(first)
        # Give the first connection an in-flight RPC, then a reconnect supersedes it.
        pending = asyncio.create_task(_swallow(first.rpc("getTree", {}, timeout=5)))
        await asyncio.sleep(0)  # let the rpc register its future
        second = SidecarConnection("abc123", _FakeSocket())
        sidecar_hub.register(second)
        await pending  # must complete (was failed), not hang on its 5s timeout
        return sidecar_hub.get("abc123") is second

    assert asyncio.run(_scenario()) is True


def test_unregister_only_removes_current_connection():
    _reset()
    first = SidecarConnection("abc123", _FakeSocket())
    second = SidecarConnection("abc123", _FakeSocket())
    sidecar_hub.register(first)
    sidecar_hub.register(second)  # second is now current
    sidecar_hub.unregister(first)  # a late close from the superseded socket
    assert sidecar_hub.get("abc123") is second


def test_send_reload_emits_reload_frame():
    _reset()

    async def _scenario():
        sock = _FakeSocket()
        conn = SidecarConnection("abc123", sock)
        await conn.send_reload()
        return sock.sent

    assert asyncio.run(_scenario()) == [{"type": "reload"}]


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
