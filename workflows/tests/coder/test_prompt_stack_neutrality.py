"""A coder prompt may not name a stack the repo it is rendering for does not have.

The failure this pins is not hypothetical. A repo with a React web app and a docs site,
and no mobile code anywhere, rendered `plan-story`'s prompt with ten mentions of Flutter
and Dart in it — an "Instruction Set Resolution" header that correctly listed only the
skills the repo installed, followed by body prose that enumerated a stack from a
different repo entirely. The agent believed the body. That is the whole bug: the
reference *helpers* were fixed to drop unresolved names, and the **prose around them**
still hardcoded the menu they were supposed to have replaced.

So this renders every coder prompt against a manifest holding one stack's skills and
asserts none of the *other* stacks' vocabulary survives. It is a rendering test rather
than a static grep because the guards are the mechanism under test — `{%- set web_refs =
find_by_tags("web") %}` at the top and `{% if web_refs %}` around the body — and a grep
cannot tell prose inside a guard from prose outside one.

The manifest carries `_instruction_tags` as well as `_instructions`, because a guard that
survives asks by capability rather than by name. The prompts no longer *list* what a repo
installs — the installed skills advertise themselves and the model loads them — so what is
left to check is the other half: that no prompt hardcodes a stack, and that none demands a
skill by a name no repo is obliged to install.

Both directions are checked. A web-only manifest must not yield mobile prose, and a
mobile-only manifest must not yield web prose, because a prompt that hardcodes *one*
stack passes the single-direction version of this test whenever that stack happens to be
the one left out.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import TypedDict

import pytest
from workhorse.templates import render

import workhorse_workflows

CODER = Path(workhorse_workflows.__file__).parent / "coder"

#: Every envelope, across the flow packages that own them. Duplicated stems are checked
#: once per copy — the copies may diverge, so neutrality has to hold in each of them.
PROMPTS = sorted(CODER.glob("*/prompts/*.md"))


def _id(path: Path) -> str:
    return f"{path.parent.parent.name}/{path.stem}"

#: What each stack's skills are called, what each declares in `tags:`, and the words that
#: only belong to that stack. The *tags* are what the prompts query — the layer tag is the
#: stack's own name, and the cross-cutting ones (`standards`, `tests`, `qa`, `runbook`,
#: `codegen`) say what the skill is for. A tag missing here resolves nothing and would make
#: every neutrality assertion below trivially true, which is why the last test re-checks
#: that the stack a repo *does* have still reaches the prompt.
class _Stack(TypedDict):
    """One stack's installed skills and the words only it may use.

    Spelled out rather than left to inference: every lookup below reads one of the two
    keys back out, and a bare literal makes each value the union of both — so the skills
    map arrives somewhere expecting a mapping and is a tuple half the time.
    """

    #: skill name → the tags its frontmatter declares.
    skills: dict[str, tuple[str, ...]]
    #: Prose that belongs to this stack and no other.
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

#: Value vocabulary the *workflow itself* understands — `services[].type` in
#: `plan-context.json`, which `nodes/regression.py` maps to a platform. A prompt
#: documenting the set of values a field accepts is not claiming the repo has that stack,
#: so those spellings are exempt. They are backticked lowercase identifiers; the prose
#: this test hunts is capitalized product names, which is why the exemption can be this
#: narrow.
SCHEMA_VOCABULARY = re.compile(r"`[a-z0-9-]+`|\"[a-z0-9-]+\"")


def _context(stack: str) -> dict[str, object]:
    """A farrier manifest holding exactly one stack's skills, and nothing else's.

    The paths are fabricated but shaped like real ones: `resolve_instruction` returns
    whatever the manifest maps a name to, so what matters is only that a name present
    resolves and a name absent does not. `_instruction_tags` is keyed by the same names,
    which is how `find_by_tags` gets from a queried capability back to an installed path.
    """
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
    # Strip the schema vocabulary first so a documented enum value can't be mistaken for
    # a claim about the repo — see SCHEMA_VOCABULARY.
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


#: The prose `instruction_ref` renders when a name does not resolve, with the name itself
#: left as a wildcard — `templates.instruction_ref` builds it as
#: `f"generated {name} instruction file when installed"`.
PLACEHOLDER = re.compile(r"generated (\S+) instruction file when installed")
