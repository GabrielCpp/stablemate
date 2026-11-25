"""The directories and files each install scope owns."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from farrier._vendor.stablemate_core.harness import (
    Surface,
    repo_harnesses,
    with_surface,
)
from farrier.agents import Agents
from farrier.antigravity_bridge import ANTIGRAVITY_BRIDGE, ANTIGRAVITY_GUARDS
from farrier.drift import REGENERATE
from farrier.home_guards import (
    BRIDGE_FILE,
    COPILOT_BRIDGE,
    COPILOT_GUARDS,
    PI_BRIDGE_FILE,
)
from farrier.hook_managers import LEFTHOOK_INCLUDE
from farrier.launcher import (
    LAUNCHER_AGENTS_MK,
    LAUNCHER_COMPOSE,
    LAUNCHER_CONTEXT_MANIFEST,
)
from farrier.local_instructions import LocalInstruction
from farrier.renderer import USER_ROOT_FILES
from farrier.sources import POLICY_ROOT


_REPO_LAYOUTS = [spec.repo for spec in repo_harnesses() if spec.repo is not None]

MANAGED_DIRS = list(
    dict.fromkeys(
        [
            *(layout.skills for layout in _REPO_LAYOUTS),
            *(layout.prompts for layout in _REPO_LAYOUTS if layout.prompts),
            ".agents/prompts",
            POLICY_ROOT,
            ".agents/hooks",
            ".github/instructions",
            ".github/agents",
        ]
    )
)

MANAGED_FILES = [
    ".github/copilot-instructions.md",
    LAUNCHER_AGENTS_MK,
    LEFTHOOK_INCLUDE,
]

ASSUMED_OWNED = [
    LAUNCHER_COMPOSE,
    LAUNCHER_CONTEXT_MANIFEST,
    ".agents/agents-context.*.json",
]


@dataclass(frozen=True)
class Managed:
    """What one install scope owns — the directories it sweeps and the files it names."""

    dirs: tuple[str, ...]
    files: tuple[str, ...] = ()
    assumed: tuple[str, ...] = ()
    repo_scaffolding: bool = True
    links: tuple[tuple[str, str], ...] = ()
    regenerate: str = REGENERATE


REPO_MANAGED = Managed(tuple(MANAGED_DIRS), tuple(MANAGED_FILES), tuple(ASSUMED_OWNED))

USER_MANAGED = Managed(
    tuple(
        dict.fromkeys(
            [
                *(
                    f"{spec.home.dir}/skills"
                    for spec in with_surface(Surface.HOME_SKILLS)
                    if spec.home is not None
                ),
                *(
                    spec.repo.prompts
                    for spec in with_surface(Surface.HOME_PROMPTS)
                    if spec.repo is not None and spec.repo.prompts
                ),
                ".claude/agents",
                ".agents/hooks",
                ".codex/skills",
                ".codex/agents",
                ".copilot/skills",
                ".copilot/agents",
                ".config/opencode/agents",
                ".gemini/config/agents",
                ".gemini/config/hooks",
            ]
        )
    ),
    (
        *USER_ROOT_FILES.values(),
        BRIDGE_FILE,
        COPILOT_BRIDGE,
        COPILOT_GUARDS,
        ANTIGRAVITY_BRIDGE,
        ANTIGRAVITY_GUARDS,
        PI_BRIDGE_FILE,
    ),
    (COPILOT_GUARDS, ANTIGRAVITY_GUARDS),
    repo_scaffolding=False,
    regenerate="farrier install --user",
)


def repo_managed_with_claude_pointers(
    instructions: Sequence[LocalInstruction], agents: Agents | None = None
) -> Managed:
    """REPO_MANAGED plus the CLAUDE.md in every localInstructions directory and the skill links."""
    pointers = tuple(
        (Path(rel) / "CLAUDE.md").as_posix()
        for instruction in instructions
        for rel in instruction.paths
    )
    return replace(
        REPO_MANAGED,
        files=REPO_MANAGED.files + pointers,
        links=agents.link_dirs() if agents is not None else (),
    )


def link_map(repo: Path, managed: Managed) -> dict[Path, Path]:
    """Each linked skills directory of *managed*, absolute, with the directory it links from."""
    return {repo / linked: repo / source for linked, source in managed.links}
