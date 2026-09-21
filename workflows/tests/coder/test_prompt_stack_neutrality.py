"""A coder prompt may not name a stack the repo it is rendering for does not have."""
from __future__ import annotations

import re
from pathlib import Path
from typing import TypedDict

import pytest
from workhorse.templates import render

import workhorse_workflows

CODER = Path(workhorse_workflows.__file__).parent / "coder"

PROMPTS = sorted(CODER.glob("*/prompts/*.md"))


def _id(path: Path) -> str:
    return f"{path.parent.parent.name}/{path.stem}"

class _Stack(TypedDict):
    """One stack's installed skills and the words only it may use."""

    skills: dict[str, tuple[str, ...]]
    words: tuple[str, ...]


STACKS: dict[str, _Stack] = {
    "web": {
        "skills": {
            "react-router": ("web", "standards", "runbook"),
            "react-router-architecture": ("web", "standards"),
            "react-router-testing": ("web", "tests", "qa"),
            "react-router-a11y": ("web", "standards"),
        },
        "words": ("Svelte", "React Router", "react-router"),
    },
    "mobile": {
        "skills": {
            "flutter": ("mobile", "standards", "runbook"),
            "flutter-architecture": ("mobile", "standards"),
            "flutter-state": ("mobile", "standards"),
            "flutter-api": ("mobile", "tests", "qa"),
        },
        "words": ("Flutter", "Dart", "Riverpod"),
    },
    "backend": {
        "skills": {
            "go": ("backend", "standards", "runbook"),
            "go-architecture": ("backend", "standards"),
            "go-errors": ("backend", "tests", "qa"),
            "go-openapi": ("backend", "codegen"),
        },
        "words": ("Firestore", "DynamoDB", "Cobra"),
    },
    "infra": {
        "skills": {
            "pulumi": ("infra", "standards", "runbook"),
            "pulumi-ci-docker": ("infra", "codegen"),
        },
        "words": ("Pulumi", "Terraform", "main.tf"),
    },
}

SCHEMA_VOCABULARY = re.compile(r"`[a-z0-9-]+`|\"[a-z0-9-]+\"")


def _context(stack: str) -> dict[str, object]:
    """A farrier manifest holding exactly one stack's skills, and nothing else's."""
    skills: dict[str, tuple[str, ...]] = STACKS[stack]["skills"]
    return {
        "_instructions": {name: f".claude/skills/{name}/SKILL.md" for name in skills},
        "_instruction_tags": {name: list(tags) for name, tags in skills.items()},
        "_prompts": {},
    }


def _foreign_words(stack: str) -> tuple[str, ...]:
    return tuple(
        word for other, spec in STACKS.items() if other != stack for word in spec["words"]
    )


@pytest.mark.parametrize("prompt", PROMPTS, ids=_id)
@pytest.mark.parametrize("stack", sorted(STACKS))
def test_each_prompt_is_neutral_for_the_stack_that_renders_it(stack: str, prompt: Path) -> None:
    """Render once, then enforce all three stack-neutrality contracts."""
    rendered = render(prompt, _context(stack), CODER)
    prose = SCHEMA_VOCABULARY.sub("", rendered)
    for word in _foreign_words(stack):
        assert word not in prose, (
            f"{prompt.name} rendered for a {stack}-only repo still says {word!r}; "
            f"gate that prose on the matching `find_by_tags(...)` variable"
        )
    for other, spec in STACKS.items():
        if other == stack:
            continue
        for skill in spec["skills"]:
            assert f"generated {skill} instruction file" not in rendered, (
                f"{prompt.name} requires the {skill!r} skill of a {stack}-only repo; "
                f"ask for it by tag with `find_by_tags(...)` or guard it"
            )
    missing = sorted(set(PLACEHOLDER.findall(rendered)))
    assert not missing, (
        f"{prompt.name} requires {', '.join(missing)} — a skill no repo is obliged to "
        f"install, so the prompt names a file that may not exist. Ask for it by tag with "
        f"`find_by_tags(...)` and a `| default(...)`, or guard it with "
        f"`isUsingInstruction`"
    )


PLACEHOLDER = re.compile(r"generated (\S+) instruction file when installed")
