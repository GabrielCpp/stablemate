"""Operator gate context files: what state one is in, and the answer/restart orchestration."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from markdown_it import MarkdownIt

from workhorse import control
from workhorse import gates as gate_file

from groom import docker_io, localfs, state
from groom.models import AnswerResult

AWAITING = "AWAITING_OPERATOR"
ANSWERED = "ANSWERED"
CONSUMED = "CONSUMED"

_MARKDOWN = MarkdownIt("commonmark")
_QUESTION_HEADINGS = {"question from the agent", "questions from the agent"}
_NEXT_QUESTION = re.compile(r"^#{1,2}\s+questions?\s+from\s+the\s+agent\s*$", re.IGNORECASE | re.MULTILINE)

logger = logging.getLogger(__name__)


def status_of(text: str) -> str:
    return gate_file.status_of(text)


def is_awaiting(text: str) -> bool:
    return status_of(text) == AWAITING


def extract_question(text: str) -> str:
    """Extract the latest human-facing question from the append-only gate."""
    tokens = _MARKDOWN.parse(text)
    lines = text.splitlines()
    start = 0
    end = len(lines)
    selected = False
    for opening, title in zip(tokens, tokens[1:], strict=False):
        if opening.type != "heading_open" or opening.level != 0 or opening.map is None:
            continue
        if opening.tag == "h2" and " ".join(title.content.split()).casefold() in _QUESTION_HEADINGS:
            start = opening.map[1]
            end = len(lines)
            selected = True
        elif selected and opening.tag in ("h1", "h2"):
            end = min(end, opening.map[0])
    return "\n".join(lines[start:end]).strip()


def answer_after(text: str, asked: str, which: int = -1) -> str:
    want = asked.strip()
    if not want:
        return ""
    spots = [found.start() for found in re.finditer(re.escape(want), text)]
    if not spots or which >= len(spots):
        return ""
    at = spots[which]
    end = spots[which + 1] if which != -1 and which + 1 < len(spots) else len(text)
    rest = text[at + len(want):end]
    cut = _NEXT_QUESTION.search(rest)
    return (rest[: cut.start()] if cut else rest).strip()


def asked_of(span: dict[str, Any]) -> str:
    attrs = span["attrs"]
    return extract_question(str(attrs.get("workhorse.gate_question") or "")) or str(attrs.get("activity") or "").strip()


def asking_index(text: str, asked: str, path: str, waits: list[dict[str, Any]], mine: dict[str, Any] | None) -> int | None:
    same = [
        one for one in waits
        if str(one["attrs"].get("workhorse.gate_path") or "") == path and asked_of(one) == asked
        and one["attrs"].get("workhorse.wait_outcome") == "completed"
    ]
    if mine is not None and mine not in same:
        return None
    total = len(re.findall(re.escape(asked.strip()), text)) if asked.strip() else 0
    askings = len(same) + (1 if mine is None else 0)
    position = len(same) if mine is None else same.index(mine)
    index = position - (askings - total)
    return index if 0 <= index < total else None


def apply_answer(text: str, answer: str) -> str:
    """Flip STATUS to ANSWERED and append the operator's answer, mirroring what a human editing the file by hand would do — so await_operator.py's existing state machine picks it up completely unmodified."""
    new_text = gate_file.set_status(text, ANSWERED)
    answer = answer.strip()
    if answer:
        new_text = new_text.rstrip() + f"\n\n{answer}\n"
    return new_text


async def answer_gate(
    container_id: str,
    file_path: str,
    answer: str,
    *,
    workspace_volume: str,
    native: bool = False,
    allow_headerless: bool = False,
) -> AnswerResult:
    """Write an operator's answer into a gate file."""
    if not workspace_volume:
        return AnswerResult(ok=False, message="unknown workspace volume for this container")

    read = localfs.read_file if native else docker_io.read_file
    write = localfs.write_file if native else docker_io.write_file
    lock = state.gate_lock(container_id, file_path)
    async with lock:
        current = await asyncio.to_thread(read, workspace_volume, file_path)
        if current is None:
            return AnswerResult(ok=False, message="gate file not found")
        if not is_awaiting(current) and not (
            allow_headerless and not status_of(current)
        ):
            return AnswerResult(ok=False, message="already answered in another tab")

        new_text = apply_answer(current, answer)
        wrote = await asyncio.to_thread(write, workspace_volume, file_path, new_text)
        if not wrote:
            return AnswerResult(ok=False, message="failed to write answer")

        state.clear_gate(container_id, file_path)

        if native:
            return AnswerResult(ok=True, message="answered")

        if await asyncio.to_thread(docker_io.is_running, container_id):
            return AnswerResult(ok=True, message="answered")

        started = await asyncio.to_thread(docker_io.docker_start, container_id)
        if not started:
            return AnswerResult(ok=True, message="answer written but restart failed — start the container manually")
        return AnswerResult(ok=True, message="answered and restarted")


async def native_questions(run_dir: str, caller: str, run: str) -> dict | None:
    """A native run's `questions` reply over its control socket, or ``None`` when nothing listens there or the reply is unreadable."""
    try:
        reply = await asyncio.to_thread(control.send, run_dir, control.Request(action=control.QUESTIONS))
    except FileNotFoundError:
        return None
    except control.Unanswered:
        return {}
    except control.ControlProtocolError as exc:
        logger.warning("%s: %s answered unreadably: %s", caller, run, exc)
        return None
    return dict(reply)
