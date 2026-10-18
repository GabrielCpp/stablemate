from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import _tui_support as support
import pytest

from groom import app as groom_app
from groom import attend, attend_ledger, attend_transcript, store
from groom.tui.link import Frame
from groom.tui.route import route

HOSTILE = "evil\x1b]52;c;ZXZpbA==\x07\x1b[2Jtext"
SESSIONS = "/api/attend/sessions"
SETTINGS = "/api/settings/attend"
T0 = 1_700_000_000.0


def isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str = "") -> None:
    monkeypatch.setenv("GROOM_DB", str(tmp_path / "groom.db"))
    monkeypatch.setenv("STABLEMATE_CONFIG", str(tmp_path / "config.toml"))
    monkeypatch.delenv("WORKHORSE_CONFIG", raising=False)
    monkeypatch.delenv("GROOM_ATTEND_DENY", raising=False)
    if mode:
        monkeypatch.setenv("GROOM_ATTEND", mode)
    else:
        monkeypatch.delenv("GROOM_ATTEND", raising=False)
    store.reset()
    attend.forget_settings()


def release() -> None:
    store.reset()
    attend.forget_settings()


def begin(
    job_id: str,
    run_id: str = "run-blocked",
    *,
    workflow: str = "okf-builder",
    session: str = "",
    started_at: float = T0,
    reason: str = "credential wall",
    kind: str = "gate",
    node: str = "await_operator",
) -> None:
    attend_ledger.attend_start(
        job_id, run_id=run_id, workflow=workflow, run_dir=f"/runs/{run_id}", workspace="/repo",
        kind=kind, reason=reason, node=node, gate_path="docs/gate.md", session_id=session,
        started_at=started_at,
    )


def end(job_id: str, exit_code: int | None = 0, released: str = "blocked", at: float = T0 + 90) -> None:
    attend_ledger.attend_finish(job_id, exit_code=exit_code, released_state=released, ended_at=at)


def turn(role: str, content: Any) -> dict[str, Any]:
    return {"type": role, "message": {"role": role, "content": content}}


CONVERSATION = [
    turn("user", "Attend this gate."),
    turn("assistant", [
        {"type": "text", "text": "Reading the **gate** first."},
        {"type": "tool_use", "id": "t1", "name": "Read",
         "input": {"file_path": "/runs/r1/docs/gate.md", "limit": 40}},
    ]),
    turn("user", [{"type": "tool_result", "tool_use_id": "t1", "content": "STATUS: AWAITING"}]),
    turn("assistant", [
        {"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "false"}},
    ]),
    turn("user", [{"type": "tool_result", "tool_use_id": "t2", "content": "exit 1", "is_error": True}]),
    turn("assistant", [{"type": "text", "text": "Declining: this is a credential wall."}]),
]
SIDECHAIN = [turn("assistant", [{"type": "text", "text": "subagent says hi"}])]


def write_transcript(session_id: str, records: list[dict[str, Any]], sidechain: list[dict[str, Any]] | None = None) -> None:
    directory = attend_transcript.session_dir(session_id)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{session_id}.jsonl").write_text("\n".join(json.dumps(record) for record in records) + "\n")
    if sidechain is not None:
        nested = directory / session_id
        nested.mkdir(parents=True, exist_ok=True)
        (nested / "sub.jsonl").write_text("\n".join(json.dumps(record) for record in sidechain) + "\n")


async def serve_sessions(link: support.FakeLink) -> None:
    link.get_replies[SESSIONS] = await groom_app.attend_sessions.fn()


async def serve_session(link: support.FakeLink, session_id: str) -> Frame:
    reply = await groom_app.attend_session.fn(session_id)
    link.get_replies[route(SESSIONS, session_id)] = reply
    return reply


async def serve_settings(link: support.FakeLink) -> None:
    link.get_replies[SETTINGS] = await groom_app.attend_settings_get.fn()

    async def save(body: Frame | None) -> Frame:
        return await groom_app.attend_settings_post.fn(data=body or {})

    link.post_handlers[SETTINGS] = save


CONTROLS = "\x1b\x07\x9b"


def prompts(listing: Any) -> list[str]:
    return [listing.get_option_at_index(i).prompt.plain for i in range(listing.option_count)]


def flatten(content: Any) -> str:
    if isinstance(content, str):
        return content
    if hasattr(content, "plain"):
        return content.plain
    if hasattr(content, "markup"):
        return content.markup
    if hasattr(content, "renderables"):
        return "\n".join(flatten(item) for item in content.renderables)
    return str(content)


def widget_text(widget: Any) -> str:
    from textual.widgets import Collapsible, Static

    parts = []
    if isinstance(widget, Collapsible):
        parts.append(str(widget.title))
    if isinstance(widget, Static):
        parts.append(flatten(widget.content))
    for child in widget.children:
        parts.append(widget_text(child))
    return "\n".join(parts)


def screen_text(screen: Any) -> str:
    return "\n".join(widget_text(child) for child in screen.children)


def static(screen: Any, selector: str) -> str:
    from textual.widgets import Static

    return flatten(screen.query_one(selector, Static).content)


def title(widget: Any) -> str:
    return str(widget.title)
