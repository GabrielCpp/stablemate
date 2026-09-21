"""The performances an `arrange:` bullet may declare, as named acts with typed arguments."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ostler.checks import Call, Malformed, Refusal, _typed, literal, parse_call

WEB = "web"
MOBILE = "mobile"
HTTP = "http"
CLI = "cli"

ACT_DRIVER_OMISSIONS: dict[str, str] = {
    "artifact": "an arrangement it could make is an arrangement `fixture:` already covers",
    "iac": "an arrangement it could make is an arrangement `fixture:` already covers",
    "none": "the book declares no performer for this runbook's surfaces, so there is none to "
            "carry out any act",
}


@dataclass(frozen=True)
class ActParam:
    """One argument of a named act."""

    name: str
    type: str
    required: bool = False
    locator: bool = False


@dataclass(frozen=True)
class ActSpec:
    """One named act: what performing it establishes, and who can perform it."""

    name: str
    params: tuple[ActParam, ...]
    establishes: str
    drivers: tuple[str, ...]

    @property
    def param_by_name(self) -> dict[str, ActParam]:
        return {p.name: p for p in self.params}

    def signature(self) -> str:
        """The form to suggest, spelled the way a caller writes it — `CheckSpec.signature`."""
        args = ", ".join(
            f"{p.name}=<{p.type}>{'*' if p.required else ''}" for p in self.params)
        return f"{self.name}({args})"


ACTS: tuple[ActSpec, ...] = (
    ActSpec(
        name="fill",
        params=(ActParam("locator", "str", required=True, locator=True),
                ActParam("value", "str", required=True)),
        establishes="a text control holds a stated value, which is the only way a `when:` "
                    "over what the user typed can be made true",
        drivers=(WEB, MOBILE),
    ),
    ActSpec(
        name="click",
        params=(ActParam("locator", "str", required=True, locator=True),),
        establishes="a control has been operated once — an expander opened, a row selected — "
                    "so the state a later step needs is on screen",
        drivers=(WEB, MOBILE),
    ),
    ActSpec(
        name="press",
        params=(ActParam("locator", "str", required=True, locator=True),
                ActParam("key", "str", required=True)),
        establishes="a real keypress has reached a control, which is the only way to arrange "
                    "state a pointer cannot (focus order, a key-handled shortcut)",
        drivers=(WEB, MOBILE),
    ),
    ActSpec(
        name="select",
        params=(ActParam("locator", "str", required=True, locator=True),
                ActParam("option", "str", required=True)),
        establishes="a chooser holds a stated option. Web only: a `<select>` is a control the "
                    "platform renders, and a mobile chooser is a screen of its own — arranging "
                    "one there is the steps that reach it, not one act",
        drivers=(WEB,),
    ),
    ActSpec(
        name="body",
        params=(ActParam("field", "str", required=True),
                ActParam("value", "scalar", required=True)),
        establishes="a member of the request this step sends carries a stated value — the "
                    "only state an HTTP performer can establish on the surface it performs "
                    "on, and the only way a claim about a created resource can name what "
                    "created it",
        drivers=(HTTP,),
    ),
    ActSpec(
        name="invoke",
        params=(ActParam("argv", "str[]", required=True),),
        establishes="the process this command's binary — named by the owning `cli` node's "
                    "`binary:`, not by this act — was run with the arguments `argv` names, "
                    "and has exited; that exit and those arguments are the only state a "
                    "subprocess performer can establish, and the fact "
                    "`exit_status`/`stdout`/`stderr` observe",
        drivers=(CLI,),
    ),
)

ACT_BY_NAME: dict[str, ActSpec] = {a.name: a for a in ACTS}


@dataclass(frozen=True)
class ActCall:
    """One parsed `arrange:` value: a name from `ACTS` and its bound arguments."""

    name: str
    args: dict[str, Any]

    def text(self) -> str:
        """The canonical spelling, argument order taken from the spec — `CheckCall.text`."""
        spec = ACT_BY_NAME[self.name]
        parts = [f"{p.name}={literal(self.args[p.name])}"
                 for p in spec.params if p.name in self.args]
        return f"{self.name}({', '.join(parts)})"


def vocabulary() -> str:
    """Every act's signature — the form to suggest when the author has not chosen one yet."""
    return " | ".join(spec.signature() for spec in ACTS)


def _unknown(name: str) -> Refusal:
    known = ", ".join(sorted(ACT_BY_NAME))
    return Refusal("unknown-act",
                   f"`{name}` is not a known act — the vocabulary is: {known}",
                   vocabulary())


def parse_act(value: str) -> ActCall | Refusal:
    """Parse one `arrange:` value, or return the `Refusal` saying what was written instead."""
    parsed = parse_call(value)
    if parsed is None:
        return _not_an_act(value)
    spec = ACT_BY_NAME.get(parsed.name)
    if spec is None:
        return _unknown(parsed.name)

    def wrong(message: str) -> Refusal:
        return Refusal("bad-arguments", message, spec.signature())

    if isinstance(parsed, Malformed):
        return wrong(f"`{parsed.name}`: {parsed.problem}")
    assert isinstance(parsed, Call)
    if len(parsed.positional) > len(spec.params):
        return wrong(f"`{spec.name}` takes at most {len(spec.params)} arguments")
    args: dict[str, Any] = {}
    for param, bound in zip(spec.params, parsed.positional, strict=False):
        args[param.name] = bound
    for key, bound in parsed.keywords.items():
        param = spec.param_by_name.get(key)
        if param is None:
            allowed = ", ".join(p.name for p in spec.params)
            return wrong(f"`{spec.name}` has no argument `{key}` — it takes: {allowed}")
        if param.name in args:
            return wrong(f"`{spec.name}`: `{param.name}` given twice")
        args[param.name] = bound
    return bind(parsed.name, args)


def bind(name: str, args: Mapping[str, Any]) -> ActCall | Refusal:
    """An act assembled from an already-separated name and arguments, or why it is not one."""
    spec = ACT_BY_NAME.get(name)
    if spec is None:
        return _unknown(name)

    def wrong(message: str) -> Refusal:
        return Refusal("bad-arguments", message, spec.signature())

    bound: dict[str, Any] = {}
    for key, value in args.items():
        param = spec.param_by_name.get(key)
        if param is None:
            allowed = ", ".join(p.name for p in spec.params)
            return wrong(f"`{spec.name}` has no argument `{key}` — it takes: {allowed}")
        if not _typed(value, param.type):
            return wrong(f"`{spec.name}`: `{key}` is {param.type}, got "
                         f"{type(value).__name__} — an act's arguments are what the "
                         f"performer types, points at, or sends")
        bound[key] = value
    for param in spec.params:
        if param.required and param.name not in bound:
            return wrong(f"`{spec.name}` requires `{param.name}: {param.type}`")
    return ActCall(name=name, args=bound)


def _not_an_act(value: str) -> Refusal:
    """Why this value is not an act — naming the likeliest mistake when it is recognisable."""
    text = value.strip().strip("`")
    if text and "(" not in text:
        return Refusal(
            "misfiled-fixture",
            f"`{text}` is not a performance — an `arrange:` value is an act the performer of "
            f"the step carries out on this node's own components. A named, out-of-process "
            f"arrangement belongs on `fixture:`",
            text, relocates_to="fixture")
    return Refusal("not-a-call",
                   f"`{text}` is not an act call — expected `name(arg=…)`",
                   vocabulary())


def is_act_expression(value: str) -> bool:
    """Whether *value* parses as an act call — the single test shared by every caller."""
    return isinstance(parse_act(value), ActCall)
