from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
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


class FakeLink:
    def __init__(self) -> None:
        self.sent: list[Frame] = []
        self.gets: list[str] = []
        self.posts: list[str] = []
        self.accept_send = True
        self.fail_open = False
        self.opens = 0
        self.get_replies: dict[str, Frame] = {}
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

    async def get(self, path: str) -> Frame:
        self.gets.append(path)
        if path not in self.get_replies:
            raise LinkError(path)
        return self.get_replies[path]

    async def post(self, path: str) -> Frame:
        self.posts.append(path)
        return {}

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
