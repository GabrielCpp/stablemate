"""The `agents:` table of `agents.yml`: which harnesses render, and which link their skills."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

HARNESSES = ("codex", "claude", "copilot")

REPO_SKILL_DIRS = {
    "copilot": ".github/skills",
    "codex": ".agents/skills",
    "claude": ".claude/skills",
}

HAND_WRITTEN_ORDER = ("claude", "codex", "copilot")

LINK_KEY = "skills_from"


@dataclass(frozen=True)
class Agents:
    """The checked `agents:` table: the enabled harnesses and the skill links among them."""

    enabled: dict[str, bool]
    links: dict[str, str] = field(default_factory=dict)

    def get(self, harness: str) -> bool:
        """Whether *harness* is enabled, linked or not."""
        return self.enabled.get(harness, False)

    def any_enabled(self) -> bool:
        return any(self.enabled.values())

    def real_skill_harnesses(self) -> list[str]:
        """The enabled harnesses that hold real skill folders, hand-written first choice first."""
        return [
            harness
            for harness in HAND_WRITTEN_ORDER
            if self.get(harness) and harness not in self.links
        ]

    def real_skill_dirs(self) -> list[str]:
        """Repo-relative skills directories of :meth:`real_skill_harnesses`."""
        return [REPO_SKILL_DIRS[harness] for harness in self.real_skill_harnesses()]

    def link_dirs(self) -> tuple[tuple[str, str], ...]:
        """``(linked skills dir, source skills dir)`` for every link, repo-relative."""
        return tuple(
            (REPO_SKILL_DIRS[linked], REPO_SKILL_DIRS[source])
            for linked, source in self.links.items()
        )


def _link_source(harness: str, value: dict[Any, Any]) -> str:
    """The harness named by a ``{skills_from: ...}`` mapping, or exit."""
    extra = sorted(str(key) for key in value if key != LINK_KEY)
    if extra or LINK_KEY not in value:
        raise SystemExit(
            f"agents.{harness} must be true, false or a mapping "
            f"{{{LINK_KEY}: <harness>}} (got {value!r})"
        )
    source = value[LINK_KEY]
    if not isinstance(source, str):
        raise SystemExit(
            f"agents.{harness}.{LINK_KEY} must name a harness, one of "
            f"{', '.join(HARNESSES)} (got {source!r})"
        )
    return source


def parse_agents(config: dict[str, Any]) -> Agents:
    """The `agents:` table of *config*, checked once."""
    raw = config.get("agents") or {}
    if isinstance(raw, list):
        return Agents({name: name in raw for name in HARNESSES})
    enabled: dict[str, bool] = {}
    links: dict[str, str] = {}
    for name in HARNESSES:
        value = raw.get(name, False)
        if isinstance(value, dict):
            links[name] = _link_source(name, value)
            enabled[name] = True
        else:
            enabled[name] = bool(value)
    for harness, source in links.items():
        where = f"agents.{harness}.{LINK_KEY}"
        if source not in HARNESSES:
            raise SystemExit(
                f"{where} names {source!r}, which is not a harness "
                f"(one of {', '.join(HARNESSES)})"
            )
        if source == harness:
            raise SystemExit(
                f"{where} names {harness!r} itself; a harness cannot link its own skills"
            )
        if not enabled[source]:
            raise SystemExit(
                f"{where} names {source!r}, which is not enabled; "
                f"set agents.{source} to true or link from an enabled harness"
            )
        if source in links:
            raise SystemExit(
                f"{where} names {source!r}, which itself links its skills from "
                f"{links[source]!r}; link from the harness that holds the real folders"
            )
    return Agents(enabled, links)
