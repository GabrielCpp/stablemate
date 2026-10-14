"""The ACP ``session/update`` vocabulary a transcript line holds, and the port that maps a CLI's events onto it."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

Update = dict[str, Any]

TOOL_KINDS = ("read", "edit", "delete", "move", "search", "execute", "think", "fetch", "other")
TOOL_STATUSES = ("pending", "in_progress", "completed", "failed")


@dataclass(frozen=True, slots=True)
class MappedUpdate:
    """One ``update`` object, and the tool call a subagent's event came from when it did."""

    update: Update
    parent: str | None = None


class TranscriptMapper(ABC):
    """One CLI's events turned into ACP updates, for the length of one turn."""

    def __init__(self) -> None:
        self.session_id = ""

    @abstractmethod
    def updates(self, event: dict[str, Any]) -> list[MappedUpdate]:
        """The updates one parsed event yields, keeping ``session_id`` current as events name it."""


class NullTranscript(TranscriptMapper):
    """A CLI with nothing to show."""

    def updates(self, event: dict[str, Any]) -> list[MappedUpdate]:
        return []


def text_content(text: str) -> dict[str, str]:
    return {"type": "text", "text": text}


def _chunk(kind: str, text: str) -> Update:
    return {"sessionUpdate": kind, "content": text_content(text)}


def user_message_chunk(text: str) -> Update:
    return _chunk("user_message_chunk", text)


def agent_message_chunk(text: str) -> Update:
    return _chunk("agent_message_chunk", text)


def agent_thought_chunk(text: str) -> Update:
    return _chunk("agent_thought_chunk", text)


def text_item(text: str) -> dict[str, Any]:
    """A tool call's content item holding plain text."""
    return {"type": "content", "content": text_content(text)}


def diff_item(path: str, old_text: str | None, new_text: str) -> dict[str, Any]:
    """A tool call's content item holding a file change."""
    return {"type": "diff", "path": path, "oldText": old_text, "newText": new_text}


def tool_call(
    tool_call_id: str,
    title: str,
    kind: str,
    status: str = "in_progress",
    *,
    content: list[dict[str, Any]] | None = None,
    locations: list[dict[str, Any]] | None = None,
    raw_input: Any = None,
) -> Update:
    update: Update = {
        "sessionUpdate": "tool_call",
        "toolCallId": tool_call_id,
        "title": title,
        "kind": kind,
        "status": status,
    }
    if content:
        update["content"] = content
    if locations:
        update["locations"] = locations
    if raw_input is not None:
        update["rawInput"] = raw_input
    return update


def tool_call_update(
    tool_call_id: str,
    *,
    status: str | None = None,
    content: list[dict[str, Any]] | None = None,
    raw_output: Any = None,
) -> Update:
    update: Update = {"sessionUpdate": "tool_call_update", "toolCallId": tool_call_id}
    if status is not None:
        update["status"] = status
    if content:
        update["content"] = content
    if raw_output is not None:
        update["rawOutput"] = raw_output
    return update


def plan(entries: list[dict[str, str]]) -> Update:
    return {"sessionUpdate": "plan", "entries": entries}


def plan_entry(content: str, status: str, priority: str = "medium") -> dict[str, str]:
    return {"content": content, "priority": priority, "status": status}
