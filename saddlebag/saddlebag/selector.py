"""AI-driven credential selection."""

from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from saddlebag.models import Credential, Requirement

logger = logging.getLogger(__name__)

AgentRunner = Callable[[str, str], str]

AGENT_TIMEOUT = 120

_PROMPT = """\
You are acquiring a test credential. Choose the best match and return only JSON.

Required: {requirement}

Candidates:
{candidates}

Respond with: {{"selected": "<id>", "reason": "<one line>"}}
"""


class SelectionError(RuntimeError):
    """The agent failed to choose a usable credential."""


@dataclass(frozen=True)
class Selection:
    selected: str
    reason: str = ""


def build_prompt(requirement: Requirement, candidates: Sequence[Credential]) -> str:
    """Render the selection prompt."""
    payload = [
        {
            "id": c.id,
            "roles": list(c.roles),
            "env": c.env,
            "features": list(c.features),
            "locked": c.is_locked(),
        }
        for c in candidates
    ]
    return _PROMPT.format(
        requirement=requirement.describe(),
        candidates=json.dumps(payload, indent=2),
    )


def _json_objects(text: str) -> list[dict]:
    """Every syntactically-complete JSON object in *text*, in source order."""
    decoder = json.JSONDecoder()
    found: list[dict] = []
    idx = 0
    while (idx := text.find("{", idx)) != -1:
        try:
            obj, end = decoder.raw_decode(text, idx)
        except ValueError:
            idx += 1
            continue
        if isinstance(obj, dict):
            found.append(obj)
            idx = end
        else:
            idx += 1
    return found


def parse_response(text: str) -> Selection:
    """Pull the JSON object out of an agent's reply."""
    text = text.strip()
    if not text:
        raise SelectionError("agent returned no output")

    for data in _json_objects(text):
        if "selected" not in data:
            continue
        selected = data["selected"]
        if not isinstance(selected, str) or not selected:
            continue
        return Selection(selected=selected, reason=str(data.get("reason", "")))

    raise SelectionError(f"could not parse a selection from agent output: {text[:200]!r}")


def _subprocess_runner(agent_cli: str, prompt: str) -> str:
    result = subprocess.run(
        [agent_cli, "-p", prompt],
        capture_output=True,
        text=True,
        check=False,
        timeout=AGENT_TIMEOUT,
    )
    if result.returncode != 0:
        raise SelectionError(
            f"{agent_cli} exited {result.returncode}: {result.stderr.strip()}"
        )
    return result.stdout


def select(
    requirement: Requirement,
    candidates: Sequence[Credential],
    agent_cli: str,
    *,
    runner: AgentRunner | None = None,
) -> tuple[Credential, Selection]:
    """Ask the agent to pick a credential; validate that it picked a real one."""
    if not candidates:
        raise SelectionError("no candidates to select from")

    run = runner or _subprocess_runner
    prompt = build_prompt(requirement, candidates)
    logger.debug("selecting via %s over %d candidates", agent_cli, len(candidates))

    try:
        raw = run(agent_cli, prompt)
    except FileNotFoundError as exc:
        raise SelectionError(f"agent CLI not found: {agent_cli}") from exc
    except subprocess.TimeoutExpired as exc:
        raise SelectionError(f"{agent_cli} timed out after {AGENT_TIMEOUT}s") from exc

    selection = parse_response(raw)
    by_id = {c.id: c for c in candidates}
    if selection.selected not in by_id:
        raise SelectionError(
            f"agent selected {selection.selected!r}, which was not a candidate "
            f"(offered: {', '.join(by_id)})"
        )
    return by_id[selection.selected], selection
