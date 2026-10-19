from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import _attend_support as at
import _trail_support as tr
import _tui_support as support
import pytest
from textual.widgets import OptionList, Static

from groom import app as groom_app
from groom import dispatch, dispatch_ledger
from groom.tui.route import route
from groom.tui.screens.dispatch import DispatchScreen

BASE = "/api/dispatch"
QUEUES = f"{BASE}/queues"
HOSTILE = at.HOSTILE
CONTROLS = at.CONTROLS
T0 = at.T0

PLANS = dict(
    command="workhorse-plan-runner",
    concurrency=2,
    params=[
        dict(name="plan_path", label="Plan path", type="string", required=True),
        dict(name="cli", label="Agent CLI", type="select", options=["claude", "codex"], default="claude"),
        dict(name="note", type="string", default="nightly"),
        dict(name="mode", type="select", options=["fast", "slow"]),
    ],
)
REVIEWS = dict(command="workhorse-review-runner", concurrency=1)


def posted(link: support.FakeLink, index: int) -> dict[str, Any]:
    body = link.post_log[index][1]
    assert body is not None
    return body


def items_path(queue: str) -> str:
    return route(BASE, queue) + "/items"


def item_path(queue: str, item_id: str) -> str:
    return route(items_path(queue), item_id)


def write_config(tmp_path: Path, queues: dict[str, dict[str, Any]]) -> None:
    lines: list[str] = []
    for name, opts in queues.items():
        lines.append(f"[groom.dispatch.{json.dumps(name)}]")
        lines.append(f"command = {json.dumps(opts['command'])}")
        lines.append(f"concurrency = {opts.get('concurrency', 1)}")
        for param in opts.get("params", []):
            lines.append(f"[[groom.dispatch.{json.dumps(name)}.params]]")
            for key, value in param.items():
                lines.append(f"{key} = {json.dumps(value)}")
    (tmp_path / "config.toml").write_text("\n".join(lines) + "\n")


def isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, queues: dict[str, dict[str, Any]] | None = None) -> None:
    at.isolate(tmp_path, monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    write_config(tmp_path, {"plans": PLANS, "reviews": REVIEWS} if queues is None else queues)
    dispatch.reset()


def release() -> None:
    dispatch.reset()
    at.release()


def put(
    item_id: str,
    queue: str = "plans",
    status: str = "pending",
    *,
    at_: float = T0,
    params: dict[str, Any] | None = None,
    exit_code: int | None = None,
    pid: int = 4242,
    run_id: str = "",
) -> None:
    dispatch_ledger.dispatch_enqueue(
        item_id, queue=queue, command=f"workhorse-{queue}-runner", params=params or {}, enqueued_at=at_
    )
    if status == "cancelled":
        dispatch_ledger.dispatch_cancel_pending(item_id)
    elif status != "pending":
        dispatch_ledger.dispatch_start(item_id, run_id=run_id, pid=pid, started_at=at_ + 5)
    if status in ("done", "failed"):
        dispatch_ledger.dispatch_finish(item_id, status=status, exit_code=exit_code, ended_at=at_ + 60)


def stock_items() -> None:
    put("p-fail", status="failed", at_=T0, exit_code=2, params={"plan_path": "docs/old.md"})
    put("p-done", status="done", at_=T0 + 10, exit_code=0, params={"plan_path": "docs/a.md", "cli": "codex"}, run_id="run-a")
    put("p-run", status="running", at_=T0 + 20, params={"plan_path": "docs/b.md"}, run_id="run-b")
    put("p-pend", status="pending", at_=T0 + 30, params={"plan_path": "docs/c.md"})
    put("p-gone", status="cancelled", at_=T0 + 40)
    put("r-run", "reviews", "running", at_=T0 + 50, pid=777)


async def serve(link: support.FakeLink) -> None:
    link.get_replies[QUEUES] = await groom_app.dispatch_queues.fn()
    for queue in dispatch.queues():
        link.get_replies[items_path(queue)] = await groom_app.dispatch_items.fn(queue)


async def open_dispatch(app: Any, pilot: Any, link: support.FakeLink, queues: int = 2) -> DispatchScreen:
    link.push(support.state_frame())
    await support.until(lambda: app.main.query_one("#runs", OptionList).option_count == 3)
    await pilot.press("D")
    await support.until(lambda: isinstance(app.screen, DispatchScreen))
    await support.until(lambda: queue_list(app.screen).option_count == queues)
    return app.screen


def queue_list(screen: Any) -> OptionList:
    return screen.query_one("#dispatch-queues", OptionList)


def item_list(screen: Any) -> OptionList:
    return screen.query_one("#dispatch-items", OptionList)


def ids(listing: OptionList) -> list[str]:
    return [str(listing.get_option_at_index(i).id) for i in range(listing.option_count)]


def highlighted(listing: OptionList) -> str:
    assert listing.highlighted is not None
    return str(listing.get_option_at_index(listing.highlighted).id)


def note(screen: Any, which: str) -> str:
    return at.flatten(screen.query_one(f"#dispatch-{which}-note", Static).content)


def detail(screen: Any) -> str:
    return at.flatten(screen.query_one("#dispatch-detail-text", Static).content)


def toasts(app: Any) -> list[str]:
    return [n.message for n in app._notifications]


def whole(screen: Any) -> str:
    return "\n".join([
        *at.prompts(queue_list(screen)), *at.prompts(item_list(screen)),
        note(screen, "queues"), note(screen, "items"), detail(screen),
    ])


async def settle() -> None:
    await asyncio.sleep(0.05)


run = tr.run
booted = tr.booted
