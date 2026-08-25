"""Preflight for the skill/prompt references a workflow's prompts make.

``instruction_ref("story-docs")`` resolves against the per-repo context manifest
(see :mod:`workhorse.templates`). When it does *not* resolve, the helper returns a
human-readable placeholder — ``generated story-docs instruction file when
installed`` — and that string is rendered straight into the agent's prompt where a
path belonged. Nothing fails; the agent is simply handed prose and left to find the
skill itself. It has cost real runs (author's epic-split gate escalating to its
auto-resolver) and it is invisible in the logs.

So the references are checked **before the first node runs**, against the manifest
this run actually loaded, and every name that will not resolve is named up front.
The check is a Jinja parse, not a regex: the templates are Jinja already, so the
call sites are in the AST — which also means every alias of the helper
(``instruction_file``/``skill_file``, ``prompt_file``) is covered for free, and a
mention inside a comment or a string is not mistaken for a call.

Only *required* references are reported, and a prompt has three ways to say a reference
is optional. ``instruction_refs("go", "flutter", ...)`` — plural — asks which of a set
this repo actually installed and renders just those, so an absent one is the answer
rather than a defect; ``find_by_tags('web', 'tests')`` asks the same question without
naming anything, since its arguments are tags; and a reference written inside
``{% if isUsingInstruction('flutter') %}`` cannot render on a repo without that skill,
so reporting it is a false positive. All three are what a prompt reaching for per-stack
skills needs: a Go repo must not be told to go read a Flutter skill, and must not fail
preflight for not having one.

Two further limits. Only *constant* arguments are checkable — ``instruction_ref(
skill)`` names something known at render time only, and is skipped rather than
guessed at. And a run with **no** manifest (hello-world, most tests) is skipped
whole: there, unresolved is the normal state, not a symptom.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import Environment, TemplateSyntaxError, nodes

from workhorse.manifest import ManifestContext

# The helper names exposed by workhorse.templates, grouped by what they look up.
#
# `skill_load_ref` belongs here even though it renders an instruction rather than a
# path: it is the *most* required of the singular helpers, since its call sites read
# "Load the skill and follow it" and name exactly one. Leaving it out is what let the
# coder's `document_story` and `code_review` prompts point at `ostler-documentation`
# and `code-review` on repos installing neither — a preflight that reports every other
# unresolved reference and stays silent about the two that are load-bearing is worse
# than one that reports nothing, because its silence reads as an answer.
SKILL_HELPERS = frozenset(
    {"instruction_ref", "instruction_file", "skill_file", "skill_load_ref"}
)
PROMPT_HELPERS = frozenset({"prompt_ref", "prompt_file"})

# …and their plural counterparts, which ask "which of these does this repo have?".
# Every name they take is a candidate, so an absent one is the expected answer rather
# than a finding — they render the resolved subset and drop the rest.
OPTIONAL_SKILL_HELPERS = frozenset({"instruction_refs", "instruction_files", "skill_files"})
OPTIONAL_PROMPT_HELPERS = frozenset({"prompt_refs", "prompt_files"})

# `find_by_tags('web', 'tests')` takes TAGS, not names. Its arguments name a capability
# the repo may or may not have installed a skill for, so there is nothing here to check
# — and descending into them would report every tag in every prompt as a missing skill.
TAG_HELPERS = frozenset({"find_by_tags"})

# `{% if isUsingInstruction('flutter') %}` is a prompt saying, in the only vocabulary
# available to it, "only when this repo has that skill". A reference inside such a
# branch therefore cannot render on a repo that lacks it, and reporting it is a false
# positive — the exact one that made `--dry-run` fail on every repo that legitimately
# does not install some stack.
GUARD_HELPERS = frozenset({"isUsingInstruction", "is_using_instruction"})

# Where a workflow keeps the templates rendered as node prompts. Scoped on purpose:
# a workflow's own docs may show `{{ instruction_ref(...) }}` in a fenced example,
# and a documented example is not a broken reference.
#
# Any depth, because a flow owns the prompts it renders: `coder/dev/prompts/` and
# `coder/main/prompts/` are as much prompt directories as a root-level one, and a glob
# anchored at the root would sweep only the workflows that never split them up — passing
# vacuously on the ones that did, which is the worst way for this check to fail.
PROMPT_GLOB = "**/prompts/**/*.md"


@dataclass(frozen=True)
class MissingReference:
    """One reference in one template that the loaded manifest cannot resolve."""

    kind: str  # "skill" or "prompt"
    name: str
    template: str  # path relative to the workflow dir

    def __str__(self) -> str:
        return f"{self.kind} '{self.name}' (referenced in {self.template})"


def resolve_instruction(instructions: Mapping[str, str], name: str) -> str | None:
    """The installed path for a skill, tolerating pack namespacing. None when unresolved.

    A prompt asks for a *capability* (``story-docs``) while a pack is free to namespace
    the skill that provides it (``process/process-story-docs``, installed as
    ``process-story-docs``). An exact-only lookup makes those two names miss each other.

    So: exact match first, then a **unique** suffix match on the last path segment.
    Unique is the safety rule — two packs both ending in ``-story-docs`` is a genuine
    ambiguity, and silently picking one would be a worse failure than not resolving.

    Uniqueness is judged on the resolved *path*, not the key. Farrier indexes one skill
    under several aliases (bare ``process-story-docs`` and repo-prefixed
    ``todo-app-process-story-docs``), so counting keys makes every namespaced skill look
    ambiguous with itself and resolve to nothing.
    """
    if name in instructions:
        return instructions[name]
    suffix = f"-{name}"
    hits = {
        instructions[key]
        for key in instructions
        if "/" not in key and (key == name or key.endswith(suffix))
    }
    return next(iter(hits)) if len(hits) == 1 else None


def _is_guard(test: nodes.Node) -> bool:
    """Whether an ``{% if %}`` test asks whether a skill is installed.

    The test node itself is checked alongside its descendants: ``find_all`` yields only
    the latter, and the commonest guard of all — ``{% if isUsingInstruction('x') %}`` —
    *is* the call, with nothing below it to find.
    """
    candidates = [test, *test.find_all(nodes.Call)]
    return any(
        isinstance(call, nodes.Call)
        and isinstance(call.node, nodes.Name)
        and call.node.name in GUARD_HELPERS
        for call in candidates
    )


def _collect(node: nodes.Node, guarded: bool, found: set[tuple[str, str]]) -> None:
    """Walk the AST, carrying whether this subtree sits behind an installed-skill guard.

    A hand-rolled descent rather than ``find_all`` because the guard is *positional*:
    whether a call is a required reference depends on which branch of which ``{% if %}``
    it is written in, and a flat iterator has thrown that away by the time it yields.
    """
    if isinstance(node, nodes.If):
        # The test's own subtree is not conditional — it is what decides the condition.
        _collect(node.test, guarded, found)
        body_guarded = guarded or _is_guard(node.test)
        for child in node.body:
            _collect(child, body_guarded, found)
        # `elif_` holds further `If` nodes with tests of their own, and `else_` renders
        # precisely when the guard did NOT hold. Neither inherits this branch's guard.
        for child in [*node.elif_, *node.else_]:
            _collect(child, guarded, found)
        return

    if isinstance(node, nodes.Call) and isinstance(node.node, nodes.Name):
        name = node.node.name
        if name in SKILL_HELPERS or name in PROMPT_HELPERS:
            kind = "skill" if name in SKILL_HELPERS else "prompt"
            # Only the first argument names the reference. The rest are formatting, or
            # — for `skill_load_ref(name, path)` — a fallback path, which is by
            # definition not something the manifest is expected to resolve.
            first = node.args[0] if node.args else None
            if (
                not guarded
                and isinstance(first, nodes.Const)
                and isinstance(first.value, str)
            ):
                found.add((kind, first.value))
        elif (
            name in OPTIONAL_SKILL_HELPERS
            or name in OPTIONAL_PROMPT_HELPERS
            or name in TAG_HELPERS
        ):
            # Every argument is a candidate (a name for the plural helpers, a tag for
            # the tag query), and a candidate that is absent is the answer, not a
            # defect. Recorded nowhere, and its arguments are not descended into as
            # references.
            return

    for child in node.iter_child_nodes():
        _collect(child, guarded, found)


def referenced_names(source: str) -> set[tuple[str, str]]:
    """Return ``{(kind, name)}`` for every REQUIRED reference with a constant argument.

    Required means: a singular ``*_ref``/``*_file`` helper, called outside any
    ``isUsingInstruction`` guard. Those are the references whose absence really does
    put placeholder prose in front of an agent. The plural ``*_refs`` helpers and the
    bodies of installed-skill guards are deliberately excluded — see the constants above.

    A template that will not parse yields nothing: the syntax error is the render's
    to report, and swallowing it here would only turn one clear failure into two.
    """
    env = Environment()
    try:
        ast = env.parse(source)
    except TemplateSyntaxError:
        return set()

    found: set[tuple[str, str]] = set()
    _collect(ast, False, found)
    return found


def missing_references(
    workflow_dir: str | Path, context: Mapping[str, Any]
) -> list[MissingReference]:
    """Every constant skill/prompt reference in the workflow's prompts that will not resolve.

    Sorted, so the report reads the same on every run. An empty ``context`` (no
    manifest was loaded) returns nothing — see the module docstring.
    """
    if not context:
        return []
    manifest = ManifestContext.from_context(context)
    instructions: Mapping[str, str] = manifest.instructions
    prompts: Mapping[str, str] = manifest.prompts

    root = Path(workflow_dir)
    missing: set[MissingReference] = set()
    for template in sorted(root.glob(PROMPT_GLOB)):
        if not template.is_file():
            continue
        try:
            source = template.read_text(encoding="utf-8")
        except OSError:
            continue
        rel = template.relative_to(root).as_posix()
        for kind, name in referenced_names(source):
            resolved = (
                resolve_instruction(instructions, name) is not None
                if kind == "skill"
                else name in prompts
            )
            if not resolved:
                missing.add(MissingReference(kind, name, rel))
    return sorted(missing, key=lambda m: (m.template, m.kind, m.name))


def format_missing(missing: Iterable[MissingReference]) -> str:
    """The operator-facing report: what is unresolved, and what it costs."""
    items = list(missing)
    if not items:
        return ""
    lines = "\n".join(f"  - {item}" for item in items)
    return (
        f"{len(items)} reference(s) will not resolve against this repo's context "
        f"manifest:\n{lines}\n"
        "  Each renders as prose ('generated <name> instruction file when installed') "
        "into a live agent prompt.\n"
        "  Add the skill/prompt to this repo's agents.yml selection and re-run "
        "`make agent-install`."
    )
