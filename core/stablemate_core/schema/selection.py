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
        description="Packs to install. A pack is a named bundle of skills, prompts and roots in the library.",
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
        description="Roots to render into the always-on instruction file. A user-scope table that names one is refused, because no harness reads an instruction file from the home directory.",
        examples=[["agents-overview"]],
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
