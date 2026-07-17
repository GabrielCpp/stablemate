"""STATUS-line parsing/writing for operator gate context files, plus the
answer/restart orchestration. The regex and state names here must stay
byte-compatible with the ``await_operator.py`` scripts in the workflow
library (``vigilant-octo/agents``), since those scripts read back exactly
what this module writes.
"""

from __future__ import annotations

import asyncio
import re

from groom import docker_io, state
from groom.models import AnswerResult

AWAITING = "AWAITING_OPERATOR"
ANSWERED = "ANSWERED"
CONSUMED = "CONSUMED"

_STATUS_RE = re.compile(r"^STATUS:[ \t]*(\S+)", re.MULTILINE)
_QUESTIONS_RE = re.compile(
    r"##\s*Questions?\s+from\s+the\s+agent\s*\n+(.*?)(?:\n##|\Z)",
    re.DOTALL | re.IGNORECASE,
)

_QUESTION_PREVIEW_LIMIT = 4000


def status_of(text: str) -> str:
    match = _STATUS_RE.search(text)
    return match.group(1).upper() if match else ""


def is_awaiting(text: str) -> bool:
    return status_of(text) == AWAITING


def extract_question(text: str) -> str:
    """Best-effort extraction of the human-facing question. Falls back to a
    truncated dump of the whole file when no recognizable section header is
    present — still useful, just less tidy.
    """
    match = _QUESTIONS_RE.search(text)
    body = match.group(1).strip() if match else text.strip()
    return body[:_QUESTION_PREVIEW_LIMIT]


def apply_answer(text: str, answer: str) -> str:
    """Flip STATUS to ANSWERED and append the operator's answer, mirroring
    what a human editing the file by hand would do — so await_operator.py's
    existing state machine picks it up completely unmodified.
    """
    new_text = _STATUS_RE.sub(f"STATUS: {ANSWERED}", text, count=1)
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
) -> AnswerResult:
    """Write an operator's answer into a gate file.

    ``await_operator.py`` blocks in place on the normal path (watching this
    file via inotify instead of exiting), so the container is almost always
    still running and just needs the write to wake it up — no restart. A
    ``docker start`` is only issued when the container has actually stopped
    (the inotify-unavailable fallback, or a container that predates this
    redesign), so this remains correct either way.

    Scoped to a single (container, file) pair — never assumes a workflow has
    only one live gate. Re-checks the file is still AWAITING_OPERATOR under a
    per-gate lock immediately before writing, so a second browser tab racing
    to answer the same gate gets a clean rejection instead of clobbering the
    first tab's write.
    """
    if not workspace_volume:
        return AnswerResult(ok=False, message="unknown workspace volume for this container")

    lock = state.gate_lock(container_id, file_path)
    async with lock:
        current = await asyncio.to_thread(docker_io.read_file, workspace_volume, file_path)
        if current is None:
            return AnswerResult(ok=False, message="gate file not found")
        if not is_awaiting(current):
            return AnswerResult(ok=False, message="already answered in another tab")

        new_text = apply_answer(current, answer)
        wrote = await asyncio.to_thread(docker_io.write_file, workspace_volume, file_path, new_text)
        if not wrote:
            return AnswerResult(ok=False, message="failed to write answer")

        state.clear_gate(container_id, file_path)

        if await asyncio.to_thread(docker_io.is_running, container_id):
            return AnswerResult(ok=True, message="answered")

        started = await asyncio.to_thread(docker_io.docker_start, container_id)
        if not started:
            return AnswerResult(ok=True, message="answer written but restart failed — start the container manually")
        return AnswerResult(ok=True, message="answered and restarted")
