"""Declaration: which library content one place installs. The home config's ``user_library`` harness tables and, later, the manifest share it."""

from __future__ import annotations

from .base import Section, setting


class Exclusion(Section):
    """Library content a selection drops after it has been chosen."""

    skills: list[str] = setting(
        factory=list,
        description="Skills to drop from the selection. Each entry is a skill id, a name or a glob.",
        examples=[["legacy-*", "browser-tools"]],
    )
    prompts: list[str] = setting(
        factory=list,
        description="Prompts to drop from the selection. Each entry is a prompt id, a name or a glob.",
        examples=[["release-notes"]],
    )


class Selection(Section):
    """The library content one harness installs."""

    packs: list[str] = setting(
        factory=list,
        description="Packs to install. A pack is a named bundle of skills, prompts, roots, MCP servers, guards and agents in the library.",
        examples=[["general", "stablemate"]],
    )
    skills: list[str] = setting(
        factory=list,
        description="Skills to install on top of the packs. Each entry is a skill id, a name or a glob.",
        examples=[["farrier-setup", "ostler-*"]],
    )
    prompts: list[str] = setting(
        factory=list,
        description="Prompts to install on top of the packs. Only the claude harness installs prompts at user scope.",
        examples=[["review"]],
    )
    roots: list[str] = setting(
        factory=list,
        description="Roots to render into the always-on instruction file. A claude or codex user-scope table takes one, which becomes ~/.claude/CLAUDE.md or ~/.codex/AGENTS.md.",
        examples=[["agents-overview"]],
    )
    mcp: list[str] = setting(
        factory=list,
        description="MCP servers to install on top of the packs, each a file under library/mcp. A claude or codex user-scope table takes them, and a repository does not.",
        examples=[["playwright"]],
    )
    hooks: list[str] = setting(
        factory=list,
        description="Guards to install on top of the packs, each a folder under library/hooks. A claude or codex user-scope table takes them. A guard runs before each tool call it watches and can deny the call.",
        examples=[["no-comments"]],
    )
    agents: list[str] = setting(
        factory=list,
        description="Helper agents to install on top of the packs, each a file under library/agents. A claude or codex user-scope table takes them, and each needs a model under `delegates` in the profile named after the harness.",
        examples=[["lookup"]],
    )
    scaffolds: list[str] = setting(
        factory=list,
        description="Scaffold ids available to `farrier scaffold`. They apply to a repository, not to the home directory.",
        examples=[["go-service"]],
    )
    exclude: Exclusion | None = setting(
        None,
        description="Content to drop after the packs and lists above have been resolved.",
        examples=[{"skills": ["legacy-*"]}],
        default_text="absent",
    )
