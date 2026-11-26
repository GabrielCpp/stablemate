"""The harnesses stablemate knows: what each reads, where, and what it can do for a workhorse turn."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

__all__ = [
    "HARNESSES",
    "RETIRED",
    "HarnessSpec",
    "HomeLayout",
    "Level",
    "RepoLayout",
    "Support",
    "Surface",
    "home_harnesses",
    "names",
    "repo_harnesses",
    "spec",
    "with_surface",
    "workhorse_harnesses",
]


class Level(StrEnum):
    NATIVE = "native"
    EMULATED = "emulated"
    NONE = "none"


class Surface(StrEnum):
    """One thing farrier writes for a harness."""

    REPO_SKILLS = "repo_skills"
    REPO_PROMPTS = "repo_prompts"
    HOME_ROOT = "home_root"
    HOME_SKILLS = "home_skills"
    HOME_PROMPTS = "home_prompts"
    GUARDS = "guards"
    AGENTS = "agents"
    MCP = "mcp"
    SETTINGS = "settings"


@dataclass(frozen=True)
class Support:
    """How far a harness goes on one capability, and the stand-in when it is emulated."""

    level: Level
    how: str = ""


@dataclass(frozen=True)
class RepoLayout:
    skills: str
    prompts: str | None
    prompt_suffix: str


@dataclass(frozen=True)
class HomeLayout:
    dir: str
    root_file: str
    reads_skill_dirs: tuple[str, ...] = ()


@dataclass(frozen=True)
class HarnessSpec:
    """The facts about one harness. Rendering and running stay in the tools."""

    name: str
    title: str
    skill_ref: Literal["slash", "dollar", "path"]
    repo: RepoLayout | None
    home: HomeLayout | None
    surfaces: frozenset[Surface]
    workhorse: bool
    workhorse_reason: str = ""
    skills_reads_others: bool = False
    config_dirs: tuple[str, ...] = ()
    extra_dirs: Support = Support(Level.NONE)
    compaction: Support = Support(Level.NONE)
    subagents: Support = Support(Level.NONE)
    confinement: Support = Support(Level.NONE)
    transcript: Support = Support(Level.NONE)


CLAUDE = HarnessSpec(
    name="claude",
    title="Claude Code",
    skill_ref="slash",
    repo=RepoLayout(skills=".claude/skills", prompts=".claude/commands", prompt_suffix=".md"),
    home=HomeLayout(dir=".claude", root_file=".claude/CLAUDE.md"),
    surfaces=frozenset(
        {
            Surface.REPO_SKILLS,
            Surface.REPO_PROMPTS,
            Surface.HOME_ROOT,
            Surface.HOME_SKILLS,
            Surface.HOME_PROMPTS,
            Surface.GUARDS,
            Surface.AGENTS,
            Surface.MCP,
            Surface.SETTINGS,
        }
    ),
    workhorse=True,
    config_dirs=(".claude",),
    extra_dirs=Support(Level.NATIVE, "--add-dir"),
    compaction=Support(Level.NATIVE),
    subagents=Support(Level.NATIVE),
    confinement=Support(Level.NATIVE),
    transcript=Support(Level.NATIVE, "session store"),
)

CODEX = HarnessSpec(
    name="codex",
    title="Codex",
    skill_ref="dollar",
    repo=RepoLayout(skills=".agents/skills", prompts=None, prompt_suffix=""),
    home=HomeLayout(dir=".agents", root_file=".codex/AGENTS.md"),
    surfaces=frozenset(
        {
            Surface.REPO_SKILLS,
            Surface.HOME_ROOT,
            Surface.HOME_SKILLS,
            Surface.GUARDS,
            Surface.AGENTS,
            Surface.MCP,
            Surface.SETTINGS,
        }
    ),
    workhorse=True,
    config_dirs=(".codex", ".agents"),
    subagents=Support(Level.NATIVE),
    confinement=Support(Level.NATIVE),
    transcript=Support(Level.NATIVE, "session store"),
)

COPILOT = HarnessSpec(
    name="copilot",
    title="GitHub Copilot",
    skill_ref="slash",
    repo=RepoLayout(skills=".github/skills", prompts=".github/prompts", prompt_suffix=".prompt.md"),
    home=HomeLayout(dir=".agents", root_file=".copilot/copilot-instructions.md"),
    surfaces=frozenset(
        {
            Surface.REPO_SKILLS,
            Surface.REPO_PROMPTS,
            Surface.HOME_ROOT,
            Surface.HOME_SKILLS,
            Surface.GUARDS,
            Surface.AGENTS,
            Surface.MCP,
            Surface.SETTINGS,
        }
    ),
    workhorse=True,
    extra_dirs=Support(Level.NATIVE, "--add-dir"),
)

OPENCODE = HarnessSpec(
    name="opencode",
    title="OpenCode",
    skill_ref="path",
    repo=None,
    home=HomeLayout(
        dir=".config/opencode",
        root_file=".config/opencode/AGENTS.md",
        reads_skill_dirs=(".claude/skills", ".agents/skills"),
    ),
    surfaces=frozenset({Surface.HOME_ROOT, Surface.GUARDS, Surface.AGENTS, Surface.MCP}),
    workhorse=True,
    skills_reads_others=True,
    config_dirs=(".config/opencode", ".claude/skills", ".agents/skills"),
    extra_dirs=Support(Level.EMULATED, "config: skills.paths, instructions, permission.external_directory"),
    compaction=Support(Level.EMULATED, "auto only"),
    subagents=Support(Level.NATIVE),
    confinement=Support(Level.NATIVE),
    transcript=Support(Level.EMULATED, "opencode export"),
)

ANTIGRAVITY = HarnessSpec(
    name="antigravity",
    title="Antigravity",
    skill_ref="slash",
    repo=RepoLayout(skills=".agents/skills", prompts=None, prompt_suffix=""),
    home=HomeLayout(dir=".gemini/config", root_file=".gemini/config/AGENTS.md"),
    surfaces=frozenset(
        {
            Surface.REPO_SKILLS,
            Surface.HOME_ROOT,
            Surface.HOME_SKILLS,
            Surface.GUARDS,
            Surface.AGENTS,
            Surface.MCP,
            Surface.SETTINGS,
        }
    ),
    workhorse=True,
    config_dirs=(".gemini/config", ".agents/skills"),
    extra_dirs=Support(Level.NATIVE, "--add-dir"),
    compaction=Support(Level.NATIVE, "/compact on the conversation"),
    confinement=Support(Level.EMULATED, "--sandbox terminal restrictions"),
)

PI = HarnessSpec(
    name="pi",
    title="Pi",
    skill_ref="path",
    repo=RepoLayout(skills=".agents/skills", prompts=".pi/prompts", prompt_suffix=".md"),
    home=HomeLayout(dir=".agents", root_file=".pi/agent/AGENTS.md"),
    surfaces=frozenset(
        {
            Surface.REPO_SKILLS,
            Surface.REPO_PROMPTS,
            Surface.HOME_ROOT,
            Surface.HOME_SKILLS,
            Surface.GUARDS,
            Surface.MCP,
            Surface.SETTINGS,
        }
    ),
    workhorse=True,
    config_dirs=(".pi/agent", ".agents/skills"),
    extra_dirs=Support(Level.EMULATED, "--skill per dir, no confinement to widen"),
    compaction=Support(Level.NATIVE, "rpc compact"),
    transcript=Support(Level.NATIVE, "session jsonl"),
)

HARNESSES: tuple[HarnessSpec, ...] = (CLAUDE, CODEX, COPILOT, OPENCODE, ANTIGRAVITY, PI)
RETIRED: frozenset[str] = frozenset({"cline"})


def names() -> tuple[str, ...]:
    return tuple(harness.name for harness in HARNESSES)


def spec(name: str) -> HarnessSpec:
    """The spec named *name*, or a ValueError listing the valid names."""
    for harness in HARNESSES:
        if harness.name == name:
            return harness
    raise ValueError(f"unknown harness {name!r}; the harnesses are {', '.join(names())}")


def with_surface(surface: Surface) -> tuple[HarnessSpec, ...]:
    return tuple(harness for harness in HARNESSES if surface in harness.surfaces)


def repo_harnesses() -> tuple[HarnessSpec, ...]:
    return tuple(harness for harness in HARNESSES if harness.repo is not None)


def home_harnesses() -> tuple[HarnessSpec, ...]:
    return tuple(harness for harness in HARNESSES if harness.home is not None)


def workhorse_harnesses() -> tuple[HarnessSpec, ...]:
    return tuple(harness for harness in HARNESSES if harness.workhorse)
