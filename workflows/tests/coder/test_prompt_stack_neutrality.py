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

The manifest carries `_instruction_tags` as well as `_instructions`, because the guards
ask by capability now rather than by name. A skill the manifest lists but does not tag is
one no query can reach, so an untagged manifest would render *every* layer's prose away
and pass the neutrality half of this file for the wrong reason — which is what the last
test here exists to catch.

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

PROMPTS = Path(workhorse_workflows.__file__).parent / "coder" / "prompts"

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
            f"gate that prose on the matching `find_by_tags(...)` variable"
        )


@pytest.mark.parametrize("prompt", sorted(PROMPTS.glob("*.md")), ids=lambda p: p.stem)
@pytest.mark.parametrize("stack", sorted(STACKS))
def test_no_prompt_demands_another_stacks_skill(stack: str, prompt: Path) -> None:
    """The same defect in its other spelling: a *required* ref to a stack-specific skill.

    `instruction_ref("go-testing")` is a promise that every repo has that skill. On one
    that does not, it renders as `generated go-testing instruction file when installed`
    and is also reported by `workhorse.references`' preflight — so the prompt both tells
    the agent to hunt for a Go skill and adds a finding to every non-Go run. A skill only
    some repos install is asked for by tag (`find_by_tags`), or with the plural
    name helper, or behind `isUsingInstruction`.

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
                f"ask for it by tag with `find_by_tags(...)` or guard it"
            )


#: The prose `instruction_ref` renders when a name does not resolve, with the name itself
#: left as a wildcard — `templates.instruction_ref` builds it as
#: `f"generated {name} instruction file when installed"`.
PLACEHOLDER = re.compile(r"generated (\S+) instruction file when installed")


@pytest.mark.parametrize("prompt", sorted(PROMPTS.glob("*.md")), ids=lambda p: p.stem)
@pytest.mark.parametrize("stack", sorted(STACKS))
def test_no_prompt_requires_a_skill_this_package_cannot_promise(stack: str, prompt: Path) -> None:
    """The generalization of the test above: *no* singular ref may go unresolved.

    That test names the stacks it knows, so it only catches a required skill belonging to
    one of them. The defect it missed was `instruction_ref("developer")`, in four prompts:
    `developer` is not a stack skill at all but a per-project one, so no entry in `STACKS`
    covered it and the preflight scan was the only thing that ever said a word. Every
    run of a repo without that project's overlay put `generated developer instruction file
    when installed` into four live agent prompts — a filename to go hunt for that exists
    nowhere.

    The bar this asserts is the one the package can actually meet: what a repo installs is
    the repo's business, so a prompt shipping here may not *require* any skill by name. A
    skill some repos have is asked for by tag with `find_by_tags(...)` — which renders
    nothing when nothing matches — or guarded with `isUsingInstruction`.
    """
    rendered = render(prompt, _context(stack), PROMPTS.parent)
    missing = sorted(set(PLACEHOLDER.findall(rendered)))
    assert not missing, (
        f"{prompt.name} requires {', '.join(missing)} — a skill no repo is obliged to "
        f"install, so the prompt names a file that may not exist. Ask for it by tag with "
        f"`find_by_tags(...)` and a `| default(...)`, or guard it with "
        f"`isUsingInstruction`"
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
