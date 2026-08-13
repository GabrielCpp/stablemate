"""The observations a `verify:` bullet may declare, as named checks with typed arguments.

`verify:` used to name *the test that proves this* — a test id as often as a `path::symbol`,
which is why its grounding was deferred: it had no single shape. Naming a test is also the
wrong direction. A test id says which code ran; it says nothing about what was observed, so
an assertion can be arbitrarily weaker than the claim it is filed under and still cite it.

This module gives it one shape and points it at the observation instead:

    - verify: http_status(409, title="Manifest Conflict")
    - verify: keys_unchanged(subject="pages")
    - verify: unchanged(subject="manifest", except_fields=["pages.getting-started.fr.slug"])

Three readers share this vocabulary and must not drift: `doctor` grounds the bullet against
it, `qa validate` refuses a plan whose scenario does not invoke exactly the declared call,
and the harness implements each name as a callable. That is the whole point — when the
declaration is executable, the assertion cannot be weaker than the claim, because the
assertion *is* the claim. Prose declarations do not have that property; they move the
judgment from "is this covered" to "does this assertion implement that sentence", which is
narrower but still a judgment, and a judgment is what this is retiring.

Each spec carries `excludes:` — the defect a weaker assertion would let through. It is not
decoration: it is the sentence a refusal quotes, and the test of whether a proposed check
earns a place here at all. A check that excludes nothing in particular is prose with
parentheses.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

CheckValue = str | int | bool | list[str]

#: What an argument may hold. Deliberately four scalar-ish shapes and no nesting — an
#: argument complex enough to need a structure is a check that should have been two.
_TYPES: dict[str, tuple[type, ...]] = {
    "str": (str,),
    "int": (int,),
    "bool": (bool,),
    "str[]": (list,),
}


@dataclass(frozen=True)
class CheckParam:
    """One argument of a named check."""

    name: str
    type: str
    required: bool = False


@dataclass(frozen=True)
class CheckSpec:
    """One named check: what it observes, and the defect observing it less would admit."""

    name: str
    params: tuple[CheckParam, ...]
    excludes: str

    @property
    def param_by_name(self) -> dict[str, CheckParam]:
        return {p.name: p for p in self.params}

    def signature(self) -> str:
        parts = [f"{p.name}: {p.type}{'' if p.required else ' = …'}" for p in self.params]
        return f"{self.name}({', '.join(parts)})"


#: The vocabulary. Small on purpose: every entry has to name a defect class that a plausible
#: weaker assertion lets through, and every entry costs a harness callable that has to behave
#: identically under every driver. Growing it is a deliberate act, not a convenience.
CHECKS: tuple[CheckSpec, ...] = (
    CheckSpec(
        name="http_status",
        params=(
            CheckParam("code", "int", required=True),
            CheckParam("title", "str"),
            CheckParam("path", "str"),
        ),
        excludes="a branch that returns the right shape under the wrong status, and an error "
                 "response distinguished from its siblings only by a body nobody read",
    ),
    CheckSpec(
        name="json_path",
        params=(
            CheckParam("path", "str", required=True),
            CheckParam("equals", "str"),
            CheckParam("matches", "str"),
            CheckParam("absent", "bool"),
        ),
        excludes="a field asserted by presence rather than value, which passes on the "
                 "default the defect also produces",
    ),
    CheckSpec(
        name="unchanged",
        params=(
            CheckParam("subject", "str", required=True),
            CheckParam("except_fields", "str[]"),
        ),
        excludes="collateral damage outside the field under test — the defect a diff that "
                 "masks the whole object before comparing cannot see",
    ),
    CheckSpec(
        name="keys_unchanged",
        params=(CheckParam("subject", "str", required=True),),
        excludes="a move implemented as a copy: every object compared individually matches, "
                 "and only the key inventory shows the old one is still there",
    ),
    CheckSpec(
        name="count",
        params=(
            CheckParam("subject", "str", required=True),
            CheckParam("equals", "int", required=True),
        ),
        excludes="an operation that produced the expected item *and* extras nobody counted",
    ),
    CheckSpec(
        name="absent",
        params=(CheckParam("subject", "str", required=True),),
        excludes="a delete that hid the thing from one surface and left it readable on "
                 "another",
    ),
    CheckSpec(
        name="visible",
        params=(
            CheckParam("locator", "str", required=True),
            CheckParam("text", "str"),
        ),
        excludes="an element present in the tree but not on the screen, and the right widget "
                 "showing the wrong content",
    ),
    CheckSpec(
        name="persists",
        params=(CheckParam("subject", "str", required=True),),
        excludes="a write observed only through the same session that made it, which cannot "
                 "tell a commit from a cache",
    ),
    CheckSpec(
        name="emitted",
        params=(
            CheckParam("event", "str", required=True),
            CheckParam("count", "int"),
        ),
        excludes="an effect asserted at its source instead of at its subscriber, and an "
                 "at-most-once effect fired twice",
    ),
    CheckSpec(
        name="conflict_on_stale",
        params=(
            CheckParam("subject", "str", required=True),
            CheckParam("token", "str"),
        ),
        excludes="an unconditional overwrite standing in for compare-and-swap — a write "
                 "followed by a read cannot tell them apart, only a stale write refused can",
    ),
)

CHECK_BY_NAME: dict[str, CheckSpec] = {c.name: c for c in CHECKS}


@dataclass(frozen=True)
class CheckCall:
    """One parsed `verify:` value: a name from `CHECKS` and its bound arguments."""

    name: str
    args: dict[str, CheckValue]

    def text(self) -> str:
        """The canonical spelling, argument order taken from the spec, not from the author.

        Identity, not display: this is what `qa validate` compares a scenario's invocation
        against, so two spellings of the same call have to render the same string or the
        binding check would refuse on whitespace.
        """
        spec = CHECK_BY_NAME[self.name]
        parts = [
            f"{p.name}={_literal(self.args[p.name])}" for p in spec.params if p.name in self.args
        ]
        return f"{self.name}({', '.join(parts)})"


def _literal(value: CheckValue) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "[" + ", ".join(_literal(item) for item in value) + "]"
    if isinstance(value, int):
        return str(value)
    return '"' + value.replace('"', '\\"') + '"'


def parse_check(value: str) -> CheckCall | str:
    """Parse one `verify:` value, or return the sentence explaining why it is not a check.

    Parsing goes through `ast` rather than a regex because the grammar *is* a call: a regex
    that accepts `f(a="x, y")` also accepts things that are not calls, and the failure mode
    of a permissive grammar here is a declaration nobody can execute reaching the harness.
    Only literals are admitted — there is nothing to evaluate, and nothing that could be.
    """
    text = value.strip()
    if not text:
        return "empty"
    try:
        expression = ast.parse(text, mode="eval").body
    except SyntaxError:
        return _not_a_call(text)
    if not isinstance(expression, ast.Call) or not isinstance(expression.func, ast.Name):
        return _not_a_call(text)
    name = expression.func.id
    spec = CHECK_BY_NAME.get(name)
    if spec is None:
        known = ", ".join(sorted(CHECK_BY_NAME))
        return f"`{name}` is not a known check — the vocabulary is: {known}"

    args: dict[str, CheckValue] = {}
    if len(expression.args) > len(spec.params):
        return f"`{name}` takes at most {len(spec.params)} arguments"
    for param, node in zip(spec.params, expression.args, strict=False):
        bound = _value(node)
        if isinstance(bound, str) and bound.startswith("\0"):
            return f"`{name}`: {bound[1:]}"
        args[param.name] = bound
    for keyword in expression.keywords:
        if keyword.arg is None:
            return f"`{name}`: `**` is not an argument"
        param = spec.param_by_name.get(keyword.arg)
        if param is None:
            allowed = ", ".join(p.name for p in spec.params)
            return f"`{name}` has no argument `{keyword.arg}` — it takes: {allowed}"
        if param.name in args:
            return f"`{name}`: `{param.name}` given twice"
        bound = _value(keyword.value)
        if isinstance(bound, str) and bound.startswith("\0"):
            return f"`{name}`: {bound[1:]}"
        args[param.name] = bound

    return bind(name, args)


def _not_a_call(text: str) -> str:
    """Why this value is not a check — naming the likeliest mistake when it is recognisable.

    Overwhelmingly the thing written in `verify:` that is not a call is a *test reference*,
    which is the habit the vocabulary replaced (see this module's docstring). Saying only
    "expected `name(arg=…)`" leaves the author to invent a call for an observation they were
    never asked to name here, and the invented call is what fails on the next lap; saying
    where the reference belongs ends the loop in one.
    """
    if "::" in text or text.rsplit(".", 1)[-1] in _TEST_REF_SUFFIXES:
        return (f"`{text}` is a code/test reference, not a check — a test id says which code "
                f"ran, not what was observed. Put it on `tests:` and declare the observation "
                f"here as a call, e.g. `visible(locator=…)`; `ostler checks` lists the "
                f"vocabulary")
    return f"`{text}` is not a check call — expected `name(arg=…)`; see `ostler checks`"


#: Enough to recognise a path written where a call belongs. Not a filesystem probe: the value
#: may name a test that does not exist yet, and the advice is the same either way.
_TEST_REF_SUFFIXES = {"py", "ts", "tsx", "js", "jsx", "go", "rs", "php", "dart", "java", "kt"}


def expected_form(value: str) -> str:
    """The form the author was reaching for, for a `verify:` value that did not parse.

    A refusal is only actionable if it shows the shape that would have been accepted, and the
    shape depends on *which* check was attempted — a fixed example teaches the wrong signature
    to every author whose check is not that one, which is exactly how `absent(locator=…)` and
    `emitted(subject=…)` get written. When the name is recoverable and known, that check's own
    signature is the answer; when it is not, the whole vocabulary is, because the author has
    not yet chosen from it.
    """
    text = value.strip()
    try:
        expression = ast.parse(text, mode="eval").body
    except SyntaxError:
        expression = None
    if isinstance(expression, ast.Call) and isinstance(expression.func, ast.Name):
        spec = CHECK_BY_NAME.get(expression.func.id)
        if spec is not None:
            return spec.signature()
    return " | ".join(spec.signature() for spec in CHECKS)


def bind(name: str, args: Mapping[str, Any]) -> CheckCall | str:
    """A call assembled from an already-separated name and arguments, or why it is not one.

    The tail of `parse_check`, shared with the other direction: a `verify:` bullet arrives as
    text and is parsed, while a scenario's invocation arrives as a name and a dict recovered
    from its parsed body. Both have to canonicalise through the same rules, because the whole
    binding check is a comparison of the two spellings — and a rule applied on one side only
    would refuse a plan that invokes exactly what the book declared.
    """
    spec = CHECK_BY_NAME.get(name)
    if spec is None:
        known = ", ".join(sorted(CHECK_BY_NAME))
        return f"`{name}` is not a known check — the vocabulary is: {known}"
    bound: dict[str, CheckValue] = {}
    for key, value in args.items():
        param = spec.param_by_name.get(key)
        if param is None:
            allowed = ", ".join(p.name for p in spec.params)
            return f"`{name}` has no argument `{key}` — it takes: {allowed}"
        if not _typed(value, param.type):
            return f"`{name}`: `{key}` is {param.type}, got {type(value).__name__}"
        bound[key] = value
    for param in spec.params:
        if param.required and param.name not in bound:
            return f"`{name}` requires `{param.name}: {param.type}`"
    return CheckCall(name=name, args=bound)


def _typed(value: CheckValue, declared: str) -> bool:
    # `bool` before `int`: a bool *is* an int in Python, so `count(equals=true)` would type
    # as an integer and reach the harness as 1.
    if declared != "bool" and isinstance(value, bool):
        return False
    if not isinstance(value, _TYPES[declared]):
        return False
    if declared == "str[]":
        return all(isinstance(item, str) for item in value)  # ty: ignore[not-iterable]
    return True


#: A book is not Python, and the people writing `verify:` bullets write JSON's booleans. Both
#: spellings parse; `_literal` emits the lowercase one, so a call and its canonical rendering
#: round-trip — which they must, or `text()` produces something `parse_check` then refuses.
_BOOLEANS = {"true": True, "false": False, "True": True, "False": False}


def _value(node: ast.expr) -> Any:
    """A literal argument, or `"\\0"`-prefixed prose saying why it is not one."""
    if isinstance(node, ast.Name) and node.id in _BOOLEANS:
        return _BOOLEANS[node.id]
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return "\0arguments must be literals — no names, no expressions"
