"""The observations a `verify:` bullet may declare, as named checks with typed arguments."""

from __future__ import annotations

import ast
import re
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ostler import markdown, refs

CheckValue = str | int | float | bool | list[str]

_TYPES: dict[str, tuple[type, ...]] = {
    "str": (str,),
    "int": (int,),
    "bool": (bool,),
    "scalar": (str, int, float, bool),
    "str[]": (list,),
}


@dataclass(frozen=True)
class CheckParam:
    """One argument of a named check."""

    name: str
    type: str
    required: bool = False
    path: bool = False
    locator: bool = False
    identifies: bool = False
    pattern: bool = False


Observation = str


@dataclass(frozen=True)
class CheckSpec:
    """One named check: what it observes, and the defect observing it less would admit."""

    name: str
    params: tuple[CheckParam, ...]
    excludes: str
    observes: Observation
    out_of_band: bool = False
    one_of: tuple[str, ...] = ()

    @property
    def param_by_name(self) -> dict[str, CheckParam]:
        return {p.name: p for p in self.params}

    def signature(self) -> str:
        parts = [
            f"{p.name}{'*' if p.required else ''}=<{p.type}>"
            f"{' (path)' if p.path else ''}{' (locator)' if p.locator else ''}"
            for p in self.params
        ]
        rendered = f"{self.name}({', '.join(parts)})"
        if self.one_of:
            rendered += f" — one of {', '.join(self.one_of)}"
        return rendered


CHECKS: tuple[CheckSpec, ...] = (
    CheckSpec(
        name="http_status",
        params=(
            CheckParam("code", "int", required=True),
            CheckParam("title", "str"),
            CheckParam("method", "str", identifies=True),
            CheckParam("path", "str", identifies=True),
        ),
        excludes="a branch that returns the right shape under the wrong status, and an error "
                 "response distinguished from its siblings only by a body nobody read",
        observes="response",
    ),
    CheckSpec(
        name="json_path",
        params=(
            CheckParam("path", "str", required=True, path=True, identifies=True),
            CheckParam("equals", "scalar"),
            CheckParam("matches", "str", pattern=True),
            CheckParam("absent", "bool"),
        ),
        one_of=("equals", "matches", "absent"),
        excludes="a field asserted by presence rather than value, which passes on the "
                 "default the defect also produces",
        observes="body",
    ),
    CheckSpec(
        name="unchanged",
        params=(
            CheckParam("subject", "str", required=True, identifies=True),
            CheckParam("except_fields", "str[]"),
        ),
        excludes="collateral damage outside the field under test — the defect a diff that "
                 "masks the whole object before comparing cannot see",
        observes="subject-pair",
    ),
    CheckSpec(
        name="keys_unchanged",
        params=(CheckParam("subject", "str", required=True, identifies=True),),
        excludes="a move implemented as a copy: every object compared individually matches, "
                 "and only the key inventory shows the old one is still there",
        observes="subject-pair",
    ),
    CheckSpec(
        name="count",
        params=(
            CheckParam("subject", "str", required=True, identifies=True),
            CheckParam("equals", "int", required=True),
        ),
        excludes="an operation that produced the expected item *and* extras nobody counted",
        observes="subject",
    ),
    CheckSpec(
        name="absent",
        params=(CheckParam("subject", "str", required=True, identifies=True),),
        excludes="a delete that hid the thing from one surface and left it readable on "
                 "another",
        observes="subject",
    ),
    CheckSpec(
        name="created",
        params=(CheckParam("subject", "str", required=True, identifies=True),),
        excludes="a thing that was already there reported as created — a presence check run "
                 "only afterwards passes identically on a no-op, so the absence before the "
                 "action is part of the observation rather than an assumption about it",
        observes="subject-pair",
    ),
    CheckSpec(
        name="removed",
        params=(CheckParam("subject", "str", required=True, identifies=True),),
        excludes="a delete asserted only by absence afterwards, which passes identically when "
                 "the subject was never there — the presence before the action is what makes "
                 "the disappearance attributable to it",
        observes="subject-pair",
    ),
    CheckSpec(
        name="visible",
        params=(
            CheckParam("locator", "str", required=True, locator=True, identifies=True),
            CheckParam("text", "str"),
        ),
        excludes="an element present in the tree but not on the screen, and the right widget "
                 "showing the wrong content",
        observes="page",
    ),
    CheckSpec(
        name="actionable",
        params=(CheckParam("locator", "str", required=True, locator=True, identifies=True),),
        excludes="a control the book says the user can use and the product has disabled — "
                 "which `visible` passes, because a greyed-out button is on the screen and "
                 "reads the right label",
        observes="page",
    ),
    CheckSpec(
        name="inert",
        params=(CheckParam("locator", "str", required=True, locator=True, identifies=True),),
        excludes="a control the product leaves usable after the state that should have closed "
                 "it, which no assertion about what is on the screen can see: the defect is "
                 "that the element still accepts the action, not that it is still drawn",
        observes="page",
    ),
    CheckSpec(
        name="focusable",
        params=(
            CheckParam("locator", "str", required=True, locator=True, identifies=True),
            CheckParam("activates", "str"),
        ),
        excludes="a control reachable only by pointer, which `visible`/`actionable` both pass "
                 "because it is on the screen and enabled — and, when `activates` is given, a "
                 "control that receives focus but does not fire on the key the book names, "
                 "which no assertion about what is drawn can see: the defect is in what the "
                 "keypress does, not in what is on the screen",
        observes="keyboard",
    ),
    CheckSpec(
        name="persists",
        params=(CheckParam("subject", "str", required=True, identifies=True),),
        excludes="a write observed only through the same session that made it, which cannot "
                 "tell a commit from a cache",
        observes="subject-pair",
        out_of_band=True,
    ),
    CheckSpec(
        name="emitted",
        params=(
            CheckParam("event", "str", required=True, identifies=True),
            CheckParam("count", "int"),
        ),
        excludes="an effect asserted at its source instead of at its subscriber, and an "
                 "at-most-once effect fired twice",
        observes="subject",
        out_of_band=True,
    ),
    CheckSpec(
        name="omits",
        params=(
            CheckParam("subject", "str", required=True, path=True, identifies=True),
            CheckParam("text", "str"),
            CheckParam("matches", "str", pattern=True),
        ),
        one_of=("text", "matches"),
        excludes="a value the response was never supposed to carry — a refusal quoting the "
                 "credential it rejected, an error echoing an internal path — which every "
                 "other check in this vocabulary passes over, because they all assert what "
                 "the subject does hold and a book's clause about what it may *not* hold has "
                 "no positive form",
        observes="response",
    ),
    CheckSpec(
        name="exit_status",
        params=(CheckParam("code", "int", required=True),),
        excludes="a command that failed, or succeeded for the wrong reason, and the plan only "
                 "read its output — a tool result asserted by what it printed passes identically "
                 "when the process printed it on the way to a non-zero exit",
        observes="subject",
    ),
    CheckSpec(
        name="conflict_on_stale",
        params=(
            CheckParam("subject", "str", required=True, identifies=True),
            CheckParam("token", "str"),
        ),
        excludes="an unconditional overwrite standing in for compare-and-swap — a write "
                 "followed by a read cannot tell them apart, only a stale write refused can",
        observes="response",
    ),
)

CHECK_BY_NAME: dict[str, CheckSpec] = {c.name: c for c in CHECKS}


@dataclass(frozen=True)
class CheckCall:
    """One parsed `verify:` value: a name from `CHECKS` and its bound arguments."""

    name: str
    args: dict[str, CheckValue]

    def text(self) -> str:
        """The canonical spelling, argument order taken from the spec, not from the author."""
        spec = CHECK_BY_NAME[self.name]
        parts = [
            f"{p.name}={_spelled(self.args[p.name], p)}"
            for p in spec.params if p.name in self.args
        ]
        return f"{self.name}({', '.join(parts)})"


def _spelled(value: CheckValue, param: CheckParam) -> str:
    """*value*'s literal spelling, restoring the JSONPath root `_rooted` strips."""
    if param.path and value == "":
        return '"$"'
    return literal(value)


def _rooted(value: CheckValue) -> CheckValue:
    """A path argument with the JSONPath root token dropped, so one spelling survives."""
    if not isinstance(value, str) or not value.startswith("$"):
        return value
    return value[1:].lstrip(".")


def literal(value: CheckValue) -> str:
    """One argument value, spelled the way `verify:` spells it."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "[" + ", ".join(literal(item) for item in value) + "]"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    return '"' + value.replace('"', '\\"') + '"'


def parse_expression(text: str) -> ast.Expression:
    """*text* parsed as one Python expression, without Python's warnings about its literals."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.parse(text, mode="eval")


@dataclass(frozen=True, slots=True)
class Call:
    """One call expression's name and literal arguments, before any vocabulary reads it."""

    name: str
    positional: tuple[Any, ...]
    keywords: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Malformed:
    """A call whose name is recoverable and whose arguments are not literals."""

    name: str
    problem: str


def parse_call(value: str) -> "Call | Malformed | None":
    """*value* as a call with literal arguments, a `Malformed`, or `None` for neither."""
    text = _unwrap(value)
    if not text:
        return None
    try:
        expression = parse_expression(text).body
    except SyntaxError:
        return None
    if not isinstance(expression, ast.Call) or not isinstance(expression.func, ast.Name):
        return None
    name = expression.func.id
    positional: list[Any] = []
    for node in expression.args:
        bound = _value(node)
        if isinstance(bound, str) and bound.startswith("\0"):
            return Malformed(name, bound[1:])
        positional.append(bound)
    keywords: dict[str, Any] = {}
    for keyword in expression.keywords:
        if keyword.arg is None:
            return Malformed(name, "`**` is not an argument")
        if keyword.arg in keywords:
            return Malformed(name, f"`{keyword.arg}` given twice")
        bound = _value(keyword.value)
        if isinstance(bound, str) and bound.startswith("\0"):
            return Malformed(name, bound[1:])
        keywords[keyword.arg] = bound
    return Call(name=name, positional=tuple(positional), keywords=keywords)


@dataclass(frozen=True, slots=True)
class Refusal:
    """Why one `verify:` value is not a check, as a value rather than a sentence."""

    kind: str
    message: str
    form: str
    relocates_to: str = ""

    def bullet(self, key: str, declared: frozenset[str] | None = None) -> str:
        """The suggested replacement bullet for a value found under *key*."""
        if declared is not None and self.relocates_to and self.relocates_to not in declared:
            return f"- {key}: {_vocabulary()}"
        return f"- {self.relocates_to or key}: {self.form}"


def _unknown_check(name: str) -> Refusal:
    """The refusal for a name no `CHECKS` entry declares — one spelling for both callers."""
    known = ", ".join(sorted(CHECK_BY_NAME))
    return Refusal("unknown-check",
                   f"`{name}` is not a known check — the vocabulary is: {known}",
                   _vocabulary())


def parse_check(value: str) -> CheckCall | Refusal:
    """Parse one `verify:` value, or return the `Refusal` saying what was written instead."""
    text = _unwrap(value)
    if not text:
        return Refusal("empty", "empty", _vocabulary())
    parsed = parse_call(text)
    if parsed is None:
        return _not_a_call(text)
    spec = CHECK_BY_NAME.get(parsed.name)
    if spec is None:
        return _unknown_check(parsed.name)

    def wrong(message: str) -> Refusal:
        return Refusal("bad-arguments", message, spec.signature())

    if isinstance(parsed, Malformed):
        return wrong(f"`{parsed.name}`: {parsed.problem}")
    name = parsed.name
    args: dict[str, CheckValue] = {}
    if len(parsed.positional) > len(spec.params):
        return wrong(f"`{name}` takes at most {len(spec.params)} arguments")
    for param, bound in zip(spec.params, parsed.positional, strict=False):
        args[param.name] = bound
    for key, bound in parsed.keywords.items():
        param = spec.param_by_name.get(key)
        if param is None:
            allowed = ", ".join(p.name for p in spec.params)
            return wrong(f"`{name}` has no argument `{key}` — it takes: {allowed}")
        if param.name in args:
            return wrong(f"`{name}`: `{param.name}` given twice")
        args[param.name] = bound

    return bind(name, args)


def is_check_expression(value: str) -> bool:
    """Whether *value* parses as a check call — the single test for "this is a check, not a command", shared by every caller that must tell the two apart."""
    return isinstance(parse_check(value), CheckCall)


def _unwrap(value: str) -> str:
    """The bullet's value as markdown reads it: soft line breaks folded, a code span opened."""
    return _CODE_SPAN.sub(r"\2", _SOFT_BREAK.sub(" ", value).strip()).strip()


_SOFT_BREAK = re.compile(r"[ \t]*\n[ \t]*")

_CODE_SPAN = re.compile(r"^(`+)((?:(?!\1).)*)\1$", re.DOTALL)


def relocatable_to_tests(value: str) -> bool:
    """True when a `verify:` value is *provably* the `tests:` citation form."""
    if parse_call(_unwrap(value)) is not None:
        return False
    spans = markdown.leading_code_spans(value)
    if not spans or any(parse_call(_unwrap(span)) is not None for span in spans):
        return False
    cited = [ref for span in spans if (ref := refs.normalize_ref(span))]
    return bool(cited) and all(Path(refs.ref_path(ref)).suffix for ref in cited)


def _not_a_call(text: str) -> Refusal:
    """Why this value is not a check — naming the likeliest mistake when it is recognisable."""
    head = _CALL_HEAD.match(text)
    if head is not None:
        spec = CHECK_BY_NAME.get(head.group(1))
        if spec is not None:
            return Refusal(
                "bad-arguments",
                f"`{text}`: `{spec.name}` is a known check, but its arguments did not "
                f"parse — they are written `name=value`",
                spec.signature())
    if "::" in text or text.rsplit(".", 1)[-1] in _TEST_REF_SUFFIXES \
            or relocatable_to_tests(text):
        return Refusal(
            "misfiled-test-ref",
            f"`{text}` is a code/test reference, not a check — a test id says which code "
            f"ran, not what was observed. Declare the observation here as a call, e.g. "
            f"`visible(locator=…)`; `ostler checks` lists the vocabulary",
            text, relocates_to="tests")
    return Refusal("not-a-call",
                   f"`{text}` is not a check call — expected `name(arg=…)`; see "
                   f"`ostler checks`",
                   _vocabulary())


_CALL_HEAD = re.compile(r"^([A-Za-z_]\w*)\s*\(")


_TEST_REF_SUFFIXES = {"py", "ts", "tsx", "js", "jsx", "go", "rs", "php", "dart", "java", "kt"}


def _vocabulary() -> str:
    """Every check's signature — the form to suggest when the author has not yet chosen one."""
    return " | ".join(spec.signature() for spec in CHECKS)


def bind(name: str, args: Mapping[str, Any]) -> CheckCall | Refusal:
    """A call assembled from an already-separated name and arguments, or why it is not one."""
    spec = CHECK_BY_NAME.get(name)
    if spec is None:
        return _unknown_check(name)

    def wrong(message: str) -> Refusal:
        return Refusal("bad-arguments", message, spec.signature())

    bound: dict[str, CheckValue] = {}
    for key, value in args.items():
        param = spec.param_by_name.get(key)
        if param is None:
            allowed = ", ".join(p.name for p in spec.params)
            return wrong(f"`{name}` has no argument `{key}` — it takes: {allowed}")
        if not _typed(value, param.type):
            return wrong(f"`{name}`: `{key}` is {param.type}, got {type(value).__name__}")
        if param.pattern:
            try:
                re.compile(value)
            except re.error as exc:
                return wrong(f"`{name}`: `{key}` is not a valid regular expression — {exc}")
        bound[key] = _rooted(value) if param.path else value
    for param in spec.params:
        if param.required and param.name not in bound:
            return wrong(f"`{name}` requires `{param.name}: {param.type}`")
    if spec.one_of and not any(key in bound for key in spec.one_of):
        choices = ", ".join(f"`{key}`" for key in spec.one_of)
        return wrong(
            f"`{name}` needs one of {choices} — without a comparison it asserts only that "
            f"the path resolved, and {spec.excludes}"
        )
    return CheckCall(name=name, args=bound)


def _typed(value: CheckValue, declared: str) -> bool:
    if declared not in ("bool", "scalar") and isinstance(value, bool):
        return False
    if not isinstance(value, _TYPES[declared]):
        return False
    if declared == "str[]":
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    return True


_BOOLEANS = {"true": True, "false": False, "True": True, "False": False}


def _value(node: ast.expr) -> Any:
    """A literal argument, or `"\\0"`-prefixed prose saying why it is not one."""
    if isinstance(node, ast.Name) and node.id in _BOOLEANS:
        return _BOOLEANS[node.id]
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return "\0arguments must be literals — no names, no expressions"
