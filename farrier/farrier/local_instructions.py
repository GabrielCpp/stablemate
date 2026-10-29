"""The `localInstructions` entries of `agents.yml`: their schema, checks and the files they write."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


from farrier.manifest import ConfigLike, as_manifest


LOCAL_INSTRUCTION_FILES = ("AGENTS.md", "CLAUDE.md")


def mapping_skill_names(mapping: dict[str, Any]) -> list[str]:
    """The installed skill names a localInstructions mapping selects."""
    if mapping.get("skills"):
        return [str(name) for name in mapping["skills"]]
    if mapping.get("skill"):
        return [str(mapping["skill"])]
    return []


def mapping_policy_names(mapping: dict[str, Any]) -> list[str]:
    """The policy names a localInstructions mapping selects."""
    if mapping.get("policies"):
        return [str(name) for name in mapping["policies"]]
    if mapping.get("policy"):
        return [str(mapping["policy"])]
    return []


def mapping_prompt_names(mapping: dict[str, Any]) -> list[str]:
    """The installed prompt names a localInstructions mapping selects."""
    if mapping.get("prompts"):
        return [str(name) for name in mapping["prompts"]]
    if mapping.get("prompt"):
        return [str(mapping["prompt"])]
    return []


def mapping_text(mapping: dict[str, Any]) -> str:
    """The repo-specific text a localInstructions mapping writes after its library sources."""
    return str(mapping.get("text") or "")


@dataclass(frozen=True)
class LocalInstruction:
    """One checked localInstructions entry of agents.yml."""

    paths: tuple[str, ...]
    skills: list[str]
    prompts: list[str]
    policies: list[str]
    include_readme: bool
    writes_claude_md: bool
    text: str = ""


def local_instructions(
    config: ConfigLike,
) -> tuple[LocalInstruction, ...]:
    """The localInstructions entries of *config*, each checked once."""
    return tuple(
        LocalInstruction(
            paths=tuple(entry.paths),
            skills=entry.skill_names(),
            prompts=entry.prompt_names(),
            policies=entry.policy_names(),
            include_readme=entry.includeReadme,
            writes_claude_md=entry.claudeMd,
            text=entry.text,
        )
        for entry in as_manifest(config).localInstructions
    )
