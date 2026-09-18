"""The performances an `arrange:` bullet may declare, as named acts with typed arguments.

`fixture:` arranges the world *around* a surface: a named out-of-process command run beside
the browser, which is exactly why it cannot reach the surface itself. A precondition like
*`name` non-empty and `quantity` a non-negative number* is true only once someone has typed
into the form, and no subprocess can type into a form. The performer of a step is the only
actor that can establish state on the surface it performs on, so the book needs a second
arrangement key whose values are performances, and this module is its vocabulary:

    - when: `name` non-empty and `quantity` a non-negative number
    - arrange: fill(locator="#name-field", value="Widget A")
    - arrange: fill(locator="#quantity-field", value="3")

The three properties that shape it, each already in force elsewhere:

* **Its subject is a reference into the book.** `locator=` names a `component` or
  `interaction` by its anchor, the same spelling `visible(locator=…)` uses, so a renamed
  element shows up in the book rather than going green against an element nothing declares.
* **Its driver is the performer of the step** — the browser here, a device there, an HTTP
  client for a request. Which drivers can perform an act is declared per act (`drivers`),
  because performability is a relation between what the act needs and what a driver can
  supply, not a property of the act's name.
* **Its binding is document order**, as `verify:`, `fixture:` and `capture:` already bind:
  an `arrange:` under a `when:`, or under an endpoint's `status:` arm, arranges *that* arm.

Each spec carries `establishes:` — the state performing it leaves behind — for `excludes:`'s
reason on a check: it is the sentence a refusal quotes, and the test of whether a proposed
act earns a place here at all.

**An act's argument type is a property of that act's parameter, not of acts in general.**
`fill`/`click`/`press`/`select` are all-`str` because their driver is a person: what a
browser or a device carries out is what the performer types or points at, and a person types
"3", not 3. That reasoning does not survive a driver that is not a person. Over the wire,
`{"quantity": 3}` and `{"quantity": "3"}` are different requests, and an app that requires
the first refuses the second — so `body`'s `value` is typed `scalar`, admitting the JSON
scalars a request body actually carries, while `fill`'s `value` stays `str`. `bind()` checks
each argument against its own parameter's declared type rather than one rule for every act.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ostler.checks import Call, Malformed, Refusal, _typed, literal, parse_call

#: The `driver:` values of §4.1 that can perform an arranged act. `artifact` and `iac`
#: appear on no act, because an arrangement they could make is an arrangement `fixture:`
#: already covers — but `http` does perform one: a request body is not beside the request
#: an HTTP client sends, it IS the request, so no out-of-process fixture can arrange it.
WEB = "web"
MOBILE = "mobile"
HTTP = "http"
#: `command`'s performer: a subprocess, not a person or a wire — so what it establishes is the
#: process that just ran, and `invoke`'s `argv` is typed `str[]`, not `str`, for the reason
#: `body`'s `value` is typed `scalar` and not `str`: an argv element is not typed prose the way
#: a form field is, it is one literal token a shell would hand the process unchanged. `argv`
#: carries only the arguments — the binary is the owning `cli` node's `binary:` to declare,
#: never this act's to repeat.
CLI = "cli"


@dataclass(frozen=True)
class ActParam:
    """One argument of a named act."""

    name: str
    type: str
    required: bool = False
    #: Whether the value names a component the book declares, by its anchor, rather than a
    #: selector the driver happens to accept — `CheckParam.locator`'s flag and its reason.
    locator: bool = False


@dataclass(frozen=True)
class ActSpec:
    """One named act: what performing it establishes, and who can perform it."""

    name: str
    params: tuple[ActParam, ...]
    establishes: str
    #: The drivers that can perform it. A compiler reading an act whose target's driver is
    #: absent here has to gap rather than emit — the act is declared, and this run cannot
    #: perform it, which is a different thing from the book being wrong.
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
    """Parse one `arrange:` value, or return the `Refusal` saying what was written instead.

    The call grammar is `checks.parse_call`, shared with `verify:` so that one spelling of a
    declared call serves both keys. What differs is the vocabulary, and one refusal: a value
    under `arrange:` that is not a call is most often a fixture name, which is a real
    arrangement written under the wrong key rather than a malformed act — so it relocates
    instead of being handed a vocabulary it was never reaching for.
    """
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
    """An act assembled from an already-separated name and arguments, or why it is not one.

    `checks.bind`'s counterpart and its reason: an `arrange:` bullet arrives as text, and a
    scenario's compiled call arrives as a name and a dict, and the two have to canonicalise
    through one set of rules or a plan performing exactly what the book declared would fail
    the comparison on spelling.
    """
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
        # Per-parameter, not per-act: a locator is an anchor and a value typed into a control
        # is what the user typed, so `fill`'s `value` stays `str` — but a wire request holds
        # JSON scalars, so `body`'s `value` admits them. See the module docstring.
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
    """Why this value is not an act — naming the likeliest mistake when it is recognisable.

    The habit under `arrange:` is a *fixture name*, because `fixture:` was the only
    arrangement key the grammar had. That value is not malformed; it is well-formed under
    `fixture:`, and saying so ends the loop in one lap where handing back the act vocabulary
    would send the author to invent a performance for state a subprocess already arranges.
    """
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
