"""AI-driven credential selection.

``saddlebag scan --select-via <cli>`` renders the candidate list into a compact
prompt, hands it to an agent CLI, and parses the chosen id back out.

The agent runner is injected (:class:`AgentRunner`) rather than hard-wired to
:mod:`subprocess`, so the whole selection path is exercised in tests without an
agent installed.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .models import Credential, Requirement

logger = logging.getLogger(__name__)

#: Called with (agent_cli, prompt) -> raw stdout.
AgentRunner = Callable[[str, str], str]

#: Guard against a runaway agent CLI.
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
    """Render the selection prompt. Candidates are redacted — no passwords."""
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


def parse_response(text: str) -> Selection:
    """Pull the JSON object out of an agent's reply.

    Agent CLIs habitually wrap JSON in prose or a ``` fence, so locate the first
    balanced object rather than trusting the whole payload to parse.
    """
    text = text.strip()
    if not text:
        raise SelectionError("agent returned no output")

    candidates: list[str] = []
    if fence := re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL):
        candidates.append(fence.group(1).strip())
    candidates.append(text)
    if (start := text.find("{")) != -1 and (end := text.rfind("}")) > start:
        candidates.append(text[start : end + 1])

    for blob in candidates:
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict) or "selected" not in data:
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
