"""A coder prompt may not name a stack the repo it is rendering for does not have."""
from __future__ import annotations

import re
from pathlib import Path
from typing import TypedDict

import pytest
from workhorse._vendor.stablemate_core.skill_refs import MissingSkill
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


def _context(stack: str, root: Path) -> dict[str, object]:
    """A repo holding exactly one stack's skills and the docs skill, and nothing else's."""
    skills: dict[str, tuple[str, ...]] = {**STACKS[stack]["skills"], "ostler-okf": ("docs",)}
    (root / ".git").mkdir(parents=True)
    for name, tags in skills.items():
        skill = root / ".claude/skills" / f"acme-{name}" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(
            f"---\nname: acme-{name}\nmetadata:\n  name: {name}\n  tags: [{', '.join(tags)}]\n---\n",
            encoding="utf-8",
        )
    return {"_node_cwd": str(root)}


def _foreign_words(stack: str) -> tuple[str, ...]:
    return tuple(
        word for other, spec in STACKS.items() if other != stack for word in spec["words"]
    )


@pytest.mark.parametrize("prompt", PROMPTS, ids=_id)
@pytest.mark.parametrize("stack", sorted(STACKS))
def test_each_prompt_is_neutral_for_the_stack_that_renders_it(
    stack: str, prompt: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Render once for a repo of one stack, and require no other stack's words or skills."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AGENT_CLI", "claude")
    try:
        rendered = render(prompt, _context(stack, tmp_path / "acme"), CODER)
    except MissingSkill as exc:
        pytest.fail(
            f"{prompt.name} requires the {exc.name!r} skill of a {stack}-only repo, a skill "
            f"no repo is obliged to install. Ask for it by tag with `find_by_tags(...)` and "
            f"a `| default(...)`, or guard it with `has_skill`"
        )
    prose = SCHEMA_VOCABULARY.sub("", rendered)
    for word in _foreign_words(stack):
        assert word not in prose, (
            f"{prompt.name} rendered for a {stack}-only repo still says {word!r}; "
            f"gate that prose on the matching `find_by_tags(...)` variable"
        )
