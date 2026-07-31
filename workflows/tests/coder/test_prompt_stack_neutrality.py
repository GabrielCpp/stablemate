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
instruction_refs(...) %}` at the top and `{% if web_refs %}` around the body — and a grep
cannot tell prose inside a guard from prose outside one.

Both directions are checked. A web-only manifest must not yield mobile prose, and a
mobile-only manifest must not yield web prose, because a prompt that hardcodes *one*
stack passes the single-direction version of this test whenever that stack happens to be
the one left out.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from workhorse.templates import render

import workhorse_workflows

PROMPTS = Path(workhorse_workflows.__file__).parent / "coder" / "prompts"

#: What each stack's skills are called, and the words that only belong to it. The skill
#: names must match what the prompts pass to `instruction_refs` — they are the keys
#: farrier writes into the manifest, and a typo here would resolve nothing and make every
#: assertion below trivially true.
STACKS = {
    "web": {
        "skills": (
            "react-router",
            "react-router-architecture",
            "react-router-testing",
            "react-router-a11y",
        ),
        "words": ("Svelte", "React Router", "react-router"),
    },
    "mobile": {
        "skills": ("flutter", "flutter-architecture", "flutter-state", "flutter-api"),
        "words": ("Flutter", "Dart", "Riverpod"),
    },
    "backend": {
        "skills": ("go", "go-architecture", "go-errors", "go-openapi"),
        "words": ("Firestore", "DynamoDB", "Cobra"),
    },
    "infra": {
        "skills": ("pulumi", "pulumi-ci-docker"),
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
    resolves and a name absent does not.
    """
    return {
        "_instructions": {
            name: f".claude/skills/{name}/SKILL.md" for name in STACKS[stack]["skills"]
        },
        "_prompts": {},
    }


def _foreign_words(stack: str) -> tuple[str, ...]:
    return tuple(
        word for other, spec in STACKS.items() if other != stack for word in spec["words"]
    )


@pytest.mark.parametrize("prompt", sorted(PROMPTS.glob("*.md")), ids=lambda p: p.stem)
@pytest.mark.parametrize("stack", sorted(STACKS))
def test_a_prompt_names_no_stack_the_manifest_does_not_have(stack: str, prompt: Path) -> None:
    rendered = render(prompt, _context(stack), PROMPTS.parent)
    # Strip the schema vocabulary first so a documented enum value can't be mistaken for
    # a claim about the repo — see SCHEMA_VOCABULARY.
    prose = SCHEMA_VOCABULARY.sub("", rendered)
    for word in _foreign_words(stack):
        assert word not in prose, (
            f"{prompt.name} rendered for a {stack}-only repo still says {word!r}; "
            f"gate that prose on the matching `instruction_refs(...)` variable"
        )


@pytest.mark.parametrize("prompt", sorted(PROMPTS.glob("*.md")), ids=lambda p: p.stem)
@pytest.mark.parametrize("stack", sorted(STACKS))
def test_no_prompt_demands_another_stacks_skill(stack: str, prompt: Path) -> None:
    """The same defect in its other spelling: a *required* ref to a stack-specific skill.

    `instruction_ref("go-testing")` is a promise that every repo has that skill. On one
    that does not, it renders as `generated go-testing instruction file when installed`
    and is also reported by `workhorse.references`' preflight — so the prompt both tells
    the agent to hunt for a Go skill and adds a finding to every non-Go run. A skill only
    some repos install belongs in the plural helper, or behind `isUsingInstruction`.

    Checked against the placeholder rather than the source because that is the string the
    agent would actually read, and it appears no matter which alias of the helper
    (`instruction_ref`/`instruction_file`/`skill_file`) produced it.
    """
    rendered = render(prompt, _context(stack), PROMPTS.parent)
    for other, spec in STACKS.items():
        if other == stack:
            continue
        for skill in spec["skills"]:
            assert f"generated {skill} instruction file" not in rendered, (
                f"{prompt.name} requires the {skill!r} skill of a {stack}-only repo; "
                f"move it into an `instruction_refs(...)` menu or guard it"
            )


@pytest.mark.parametrize("stack", sorted(STACKS))
def test_the_stack_it_does_have_still_reaches_the_prompt(stack: str) -> None:
    """The guard against passing by rendering nothing.

    Dropping every stack-specific paragraph would satisfy the test above perfectly, and
    would also delete the guidance the prompt exists to give. `plan-story` and
    `refine-plan` are the two that branch per layer, so each must still name at least one
    of the manifest's own skill files once the guards have run.
    """
    for name in ("plan-story.md", "refine-plan.md"):
        rendered = render(PROMPTS / name, _context(stack), PROMPTS.parent)
        assert any(skill in rendered for skill in STACKS[stack]["skills"]), (
            f"{name} rendered for a {stack} repo mentions none of its skills — the "
            f"guards are dropping the prose they were meant to select"
        )
