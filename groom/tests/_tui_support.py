from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from groom import projection, state
from groom.models import GateInfo, WorkflowState
from groom.tui.link import Frame, LinkError

ACME = "acme12345678"
GLOBEX = "globex123456"
WEBAPP = "webapp123456"
HOSTILE = "Pick a **storage backend**:\x1b]52;c;ZXZpbA==\x07\n\n- postgres\n- sqlite\x1b[2J\n"


def seed(question: str = HOSTILE) -> None:
    state.WORKFLOWS.clear()
    state.SCANNING = False
    blocked = state.upsert_workflow(
        ACME,
        name="coder-acme",
        workflow_type="coder",
        repo_name="acme",
        current_node="await_operator",
        activity="waiting on the operator",
        run_id="run-blocked",
        state=WorkflowState.BLOCKED,
    )
    blocked.gates["context/gate.md"] = GateInfo(
        workflow_id=ACME, file_path="context/gate.md", question=question
    )
    state.upsert_workflow(
        GLOBEX,
        name="author-globex",
        workflow_type="author",
        repo_name="globex",
        current_node="split_stories",
        activity="splitting stories",
        run_id="run-running",
        state=WorkflowState.RUNNING,
    )
    state.upsert_workflow(
        WEBAPP,
        name="coder-web-app",
        workflow_type="coder",
        repo_name="web-app",
        current_node="done",
        run_id="run-done",
        state=WorkflowState.FINISHED,
        exit_code=0,
    )


def state_frame() -> Frame:
    return projection.state_message(list(state.WORKFLOWS.values()))


def run_frame(container_id: str) -> Frame:
    return projection.run_message(state.WORKFLOWS[container_id])


def detail_frame(container_id: str) -> Frame:
    return projection.detail_message(state.WORKFLOWS[container_id])


def log_row(ts: float, body: str, node: str = "implement", severity: str = "INFO") -> Frame:
    return {"kind": "log", "ts": ts, "node": node, "severity": severity, "body": body}


def metric_row(ts: float, name: str = "workhorse.node_s", value: float = 4.0, node: str = "implement") -> Frame:
    return {"kind": "metric", "ts": ts, "name": name, "value": value, "attrs": {"node": node}}


def span_row(ts: float, name: str = "plan", slug: str = "", status: str = "OK", node: str = "implement") -> Frame:
    return {
        "kind": "span", "ts": ts, "start_ts": ts - 2, "end_ts": ts, "status": status, "node": node,
        "name": name, "span_id": f"span-{name}-{ts}", "slug": slug,
    }


def message_update(kind: str, text: str) -> Frame:
    return {"sessionUpdate": kind, "content": {"type": "text", "text": text}}


def tool_update(title: str, result: str = "", status: str = "completed") -> Frame:
    return {
        "sessionUpdate": "tool_call", "toolCallId": title, "title": title, "kind": "execute",
        "status": status, "rawInput": {"command": "ls"}, "rawOutput": result,
    }


def transcript_row(ts: float, update: Frame, slug: str = "001-implement", node: str = "implement") -> Frame:
    return {
        "kind": "transcript", "ts": ts, "node": node, "parent": "", "slug": slug,
        "key": f"{slug}:{ts}", "update": update,
    }


FACTS = {"span_count": 7, "error_count": 2, "node": "implement"}


def history_frame(container_id: str, rows: list[Frame], now: float = 1000.0) -> Frame:
    return projection.detail_message(state.WORKFLOWS[container_id], facts=FACTS, history=rows, now=now)


class FakeLink:
    def __init__(self) -> None:
        self.sent: list[Frame] = []
        self.gets: list[str] = []
        self.posts: list[str] = []
        self.post_log: list[tuple[str, Frame | None]] = []
        self.post_replies: dict[str, Frame | Exception] = {}
        self.post_handlers: dict[str, Callable[[Frame | None], Awaitable[Frame]]] = {}
        self.accept_send = True
        self.fail_open = False
        self.opens = 0
        self.get_replies: dict[str, Frame] = {}
        self.list_replies: dict[str, list[Frame]] = {}
        self.holds: dict[str, asyncio.Event] = {}
        self._queue: asyncio.Queue[Frame | None] = asyncio.Queue()

    async def open(self) -> None:
        if self.fail_open:
            raise LinkError("refused")
        self.opens += 1

    async def frames(self) -> AsyncIterator[Frame]:
        while True:
            frame = await self._queue.get()
            if frame is None:
                return
            yield frame

    async def send(self, command: Frame) -> bool:
        if not self.accept_send:
            return False
        self.sent.append(command)
        return True

    async def _hold(self, path: str) -> None:
        if path in self.holds:
            await self.holds[path].wait()

    async def _arrive(self, path: str) -> None:
        self.gets.append(path)
        await self._hold(path)

    async def get(self, path: str) -> Frame:
        await self._arrive(path)
        if path not in self.get_replies:
            raise LinkError(path)
        return self.get_replies[path]

    async def get_list(self, path: str) -> list[Frame]:
        await self._arrive(path)
        if path not in self.list_replies:
            raise LinkError(path)
        return self.list_replies[path]

    async def post(self, path: str, body: Frame | None = None) -> Frame:
        self.posts.append(path)
        self.post_log.append((path, body))
        await self._hold(path)
        if path in self.post_handlers:
            return await self.post_handlers[path](body)
        reply = self.post_replies.get(path, {})
        if isinstance(reply, Exception):
            raise reply
        return reply

    async def close(self) -> None:
        return None

    def push(self, frame: Frame) -> None:
        self._queue.put_nowait(frame)

    def drop(self) -> None:
        self._queue.put_nowait(None)


async def until(predicate: Callable[[], Any], timeout: float = 5.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() > deadline:
            raise AssertionError("condition not reached in time")
        await asyncio.sleep(0.02)
