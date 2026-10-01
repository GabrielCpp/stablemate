"""The `localInstructions` entries of `agents.yml`: their schema, checks and the files they write."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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


_README_ALIASES = {"inline": True, "import": True, "none": False}


def mapping_include_readme(mapping: dict[str, Any]) -> bool:
    """Whether a localInstructions mapping folds in the sibling README.md."""
    value = mapping.get("includeReadme", True)
    if isinstance(value, bool):
        return value
    key = str(value)
    if key not in _README_ALIASES:
        raise SystemExit(
            f"localInstructions.includeReadme must be true or false "
            f"(got {value!r}; the {'/'.join(_README_ALIASES)} spellings are the "
            "old mechanism-picking form and still work)"
        )
    return _README_ALIASES[key]


def mapping_writes_claude_md(mapping: dict[str, Any]) -> bool:
    """Whether a localInstructions mapping also writes the `@AGENTS.md` CLAUDE.md."""
    value = mapping.get("claudeMd", False)
    if not isinstance(value, bool):
        raise SystemExit(
            f"localInstructions.claudeMd must be true or false (got {value!r})"
        )
    return value


def mapping_text(mapping: dict[str, Any]) -> str:
    """The repo-specific text a localInstructions mapping writes after its library sources."""
    value = mapping.get("text", "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise SystemExit(f"localInstructions.text must be a string (got {value!r})")
    return value


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


def _instruction_paths(mapping: dict[str, Any]) -> tuple[str, ...]:
    """The directories one localInstructions entry writes into."""
    paths = mapping.get("paths", []) or []
    if not isinstance(paths, list) or not all(isinstance(rel, str) for rel in paths):
        raise SystemExit(
            f"localInstructions.paths must be a list of directories (got {paths!r})"
        )
    return tuple(paths)


def local_instructions(config: dict[str, Any]) -> tuple[LocalInstruction, ...]:
    """The localInstructions entries of *config*, each checked once."""
    entries = config.get("localInstructions", []) or []
    if not isinstance(entries, list):
        raise SystemExit(f"localInstructions must be a list of entries (got {entries!r})")
    parsed: list[LocalInstruction] = []
    for mapping in entries:
        if not isinstance(mapping, dict):
            raise SystemExit(f"A localInstructions entry must be a mapping (got {mapping!r})")
        instruction = LocalInstruction(
            paths=_instruction_paths(mapping),
            skills=mapping_skill_names(mapping),
            prompts=mapping_prompt_names(mapping),
            policies=mapping_policy_names(mapping),
            include_readme=mapping_include_readme(mapping),
            writes_claude_md=mapping_writes_claude_md(mapping),
            text=mapping_text(mapping),
        )
        if not (
            instruction.skills
            or instruction.prompts
            or instruction.policies
            or instruction.text.strip()
        ):
            raise SystemExit(
                "A localInstructions entry must select at least one source "
                "(`policy`/`policies`, `skill`/`skills` and/or `prompt`/`prompts`) "
                "or carry `text`"
            )
        parsed.append(instruction)
    return tuple(parsed)
