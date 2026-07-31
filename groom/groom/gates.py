"""Operator gate context files: what state one is in, and the answer/restart orchestration.

The STATUS line itself is read and written through :mod:`workhorse.gates` — the one
implementation of that header, shared with the workflow nodes on the other side of it.
It used to be retyped here, and "must stay byte-compatible with what the workflow writes"
was a comment rather than something the code could hold to.

The **state names** below are still this side's business: they are the cycle an operator
gate goes through, which the shared reader deliberately knows nothing about.
"""

from __future__ import annotations

import asyncio
import re

from workhorse import gates as gate_file

from groom import docker_io, localfs, state
from groom.models import AnswerResult

AWAITING = "AWAITING_OPERATOR"
ANSWERED = "ANSWERED"
CONSUMED = "CONSUMED"

_QUESTIONS_RE = re.compile(
    r"##\s*Questions?\s+from\s+the\s+agent\s*\n+(.*?)(?:\n##|\Z)",
    re.DOTALL | re.IGNORECASE,
)

_QUESTION_PREVIEW_LIMIT = 4000


def status_of(text: str) -> str:
    return gate_file.status_of(text)


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
) -> AnswerResult:
    """Write an operator's answer into a gate file.

    ``await_operator.py`` blocks in place on the normal path (watching this
    file via inotify instead of exiting), so the container is almost always
    still running and just needs the write to wake it up — no restart. A
    ``docker start`` is only issued when the container has actually stopped
    (the inotify-unavailable fallback, or a container that predates this
    redesign), so this remains correct either way.

    A **native** run shares groom's host, so ``workspace_volume`` is a host path
    read/written directly (``groom.localfs``) and there is no container to restart —
    the run's own inotify wakes it the moment the file is written.

    Scoped to a single (container, file) pair — never assumes a workflow has
    only one live gate. Re-checks the file is still AWAITING_OPERATOR under a
    per-gate lock immediately before writing, so a second browser tab racing
    to answer the same gate gets a clean rejection instead of clobbering the
    first tab's write.
    """
    if not workspace_volume:
        return AnswerResult(ok=False, message="unknown workspace volume for this container")

    read = localfs.read_file if native else docker_io.read_file
    write = localfs.write_file if native else docker_io.write_file
    lock = state.gate_lock(container_id, file_path)
    async with lock:
        current = await asyncio.to_thread(read, workspace_volume, file_path)
        if current is None:
            return AnswerResult(ok=False, message="gate file not found")
        if not is_awaiting(current):
            return AnswerResult(ok=False, message="already answered in another tab")

        new_text = apply_answer(current, answer)
        wrote = await asyncio.to_thread(write, workspace_volume, file_path, new_text)
        if not wrote:
            return AnswerResult(ok=False, message="failed to write answer")

        state.clear_gate(container_id, file_path)

        # A native run is never docker-managed: its await_operator inotify wakes on
        # the write above, so there is nothing to (re)start.
        if native:
            return AnswerResult(ok=True, message="answered")

        if await asyncio.to_thread(docker_io.is_running, container_id):
            return AnswerResult(ok=True, message="answered")

        started = await asyncio.to_thread(docker_io.docker_start, container_id)
        if not started:
            return AnswerResult(ok=True, message="answer written but restart failed — start the container manually")
        return AnswerResult(ok=True, message="answered and restarted")
