"""The `agents:` table of `agents.yml`: which harnesses render, and which link their skills."""

from __future__ import annotations

from dataclasses import dataclass, field

from farrier._vendor.stablemate_core.schema import HARNESSES, LINK_KEY

from farrier.manifest import ConfigLike, as_manifest

__all__ = ["HARNESSES", "LINK_KEY", "Agents", "parse_agents"]

REPO_SKILL_DIRS = {
    "copilot": ".github/skills",
    "codex": ".agents/skills",
    "claude": ".claude/skills",
}

HAND_WRITTEN_ORDER = ("claude", "codex", "copilot")


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


def parse_agents(config: ConfigLike) -> Agents:
    """The `agents:` table of *config*, checked once."""
    table = as_manifest(config).agents
    return Agents(table.enabled(), table.links())
