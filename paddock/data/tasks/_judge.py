"""One agent turn that waits out usage caps, and the rubric fill every judged task uses."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

from workhorse.config_run import AgentResilience
from workhorse.runner import caps as wh_caps
from workhorse.runner import failure as wh_failure
from workhorse.runner.backends import AgentBackend
from workhorse.runner.backends.registry import get_backend
from workhorse._vendor.stablemate_core.clock import SYSTEM_CLOCK, Clock

logger = logging.getLogger(__name__)

__all__ = ["SYSTEM_CLOCK", "AgentResilience", "Judge", "call_agent", "get_backend", "render"]


def render(template: str, **fields: str) -> str:
    """Fill `{{name}}` placeholders in the rubric."""
    for key, value in fields.items():
        template = template.replace("{{" + key + "}}", value)
    return template


@dataclass(frozen=True, slots=True)
class Judge:
    """The agent CLI plus the two dependencies its recovery ladder needs."""

    backend: AgentBackend
    resilience: AgentResilience
    clock: Clock
    model: str = ""
    effort: str = ""


def call_agent(judge: Judge, prompt: str, *, node_id: str, repo: Path,
               attempts: int = 4) -> str:
    """One agent turn, waiting out usage caps the same way workhorse itself does."""
    last = ""
    for attempt in range(attempts):
        try:
            return judge.backend.run_turn(
                prompt, node_id, None,
                model=judge.model or None,
                timeout=judge.resilience.result_timeout_s,
                resilience=judge.resilience,
                cwd=str(repo),
                effort=judge.effort or None,
            )
        except wh_failure.BackendInvocationError as exc:
            last = str(exc)
            if wh_failure.is_cap(last):
                delay, when = wh_caps.cap_delay_seconds(
                    exc, resilience=judge.resilience, clock=judge.clock)
                wh_caps.sleep_with_notice(
                    delay, node_id, when, resilience=judge.resilience, clock=judge.clock)
            elif attempt < attempts - 1:
                time.sleep(5 * (attempt + 1))
            else:
                break
        except Exception as exc:  # noqa: BLE001 - a judge failing must not lose the other 17
            last = str(exc)
            break
    logger.warning("[%s] judge failed: %s", node_id, last[:200])
    return ""
