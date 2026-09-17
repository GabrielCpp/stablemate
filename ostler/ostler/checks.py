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
import re
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

CheckValue = str | int | float | bool | list[str]

#: What an argument may hold. Deliberately a few scalar-ish shapes and no nesting — an
#: argument complex enough to need a structure is a check that should have been two.
#: `scalar` is any JSON scalar: a `json_path(equals=)` compares against what the document
#: holds, and a document holds numbers and booleans as well as strings.
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
    #: Whether the value is a path into the observed document rather than free prose. Both
    #: resolvers strip a leading `$` root token (`_resolve_path`, `session._extract_path`),
    #: so `$.policy.id` and `policy.id` name the same field — and a binding check that
    #: compares spellings would otherwise refuse a plan invoking exactly what was declared.
    path: bool = False
    #: Whether the value names a component the book declares, by its anchor, rather than a
    #: selector the driver happens to accept. The distinction is the same one the `link` flag
    #: draws one bullet up: written as free text a locator type-checks, runs, and goes green
    #: against an element the book has never heard of, so renaming that element breaks the run
    #: and leaves the book undisturbed — the staleness lands on the wrong artifact. `doctor`
    #: reports one resolving to no declared component as `undeclared-check-locator`, and
    #: `compile_plan` gaps rather than emitting against it.
    locator: bool = False
    #: Whether this argument names *which* thing is observed, rather than what is expected of
    #: it. Two calls that differ on an identifying argument are two claims about two different
    #: things; two that differ on an expectation are one subject claimed two ways, which is
    #: what `unspelled-alternation` reports. Counting how many arguments differ cannot tell
    #: those apart, because the count reads neither role.
    #:
    #: It is declared per parameter and not derived, because every shortcut is wrong on some
    #: check. `required` is wrong on `http_status`, whose required `code` is the expectation
    #: and whose optional `path` is the identifier. `path` is wrong because `json_path.path`
    #: (an identifier) and `http_status.path` (also an identifier) carry opposite values of
    #: that flag — it marks a document path, not a role. `locator` is right where it appears
    #: and silent everywhere else.
    identifies: bool = False


#: What a check's compiled call is handed: `response` for the HTTP response object,
#: `body` for a decoded document (`.json()`), `page` for a Playwright locator on the
#: rendered screen, `subject` for a named thing read once, after the action (a count, an
#: absence, a process's exit code), or `subject-pair` for a named thing that only means
#: anything as a before-and-after — a record re-read, a key inventory diffed, a write
#: checked for outliving the session that made it. A compiler dispatches on this to decide
#: what operand a check's call takes, whether a given driver (HTTP, Playwright) can observe
#: it at all, and — for the two subject shapes — what a plan that cannot yet arrange the
#: observation is missing, rather than guessing from the name.
Observation = str


@dataclass(frozen=True)
class CheckSpec:
    """One named check: what it observes, and the defect observing it less would admit."""

    name: str
    params: tuple[CheckParam, ...]
    excludes: str
    #: See `Observation` above.
    observes: Observation
    #: Whether the observation comes through a channel the compile-time driver (HTTP,
    #: Playwright) has no handle on — a subscriber's event log (`emitted`), a re-read that
    #: must come from somewhere other than the session that wrote (`persists`) — as opposed
    #: to a value already in scope from the response or tool result the action produced.
    #: This is independent of `observes`: shape (single vs. before-and-after) and channel
    #: (in-band vs. out-of-band) vary separately, which is why both are fields here rather
    #: than one inferred from the other or from the check's name.
    out_of_band: bool = False
    #: Arguments of which the call must carry at least one. `required` cannot say this: each
    #: of these is optional on its own, and it is the *choice* that is mandatory. Without it
    #: a check can be spelled so that nothing it observes can come out false — `json_path`
    #: with no comparison passes on any value the path resolves to — and an assertion that
    #: cannot fail is refused where it is written, not discovered green at runtime.
    one_of: tuple[str, ...] = ()

    @property
    def param_by_name(self) -> dict[str, CheckParam]:
        return {p.name: p for p in self.params}

    def signature(self) -> str:
        # `*` for required, and the argument class in parentheses. The class is part of the
        # signature because it is part of what the caller has to write: a `(path)` argument is
        # a path into the observed document and a `(locator)` argument is the anchor of a
        # component the book declares. Rendering only name and type prints a `str` where the
        # reader needs to know which of the three kinds of string is meant, and the reference
        # page claims this tool is the authority on exactly that.
        #
        # The separator is `=` and the type sits in angle brackets because this string is the
        # only example of the form most authors ever see, and an example is a thing to copy
        # while a type is a thing to read. Rendering `code: int*` — Python's *annotation*
        # spelling — put a colon exactly where a call puts `=`, and four `verify:` bullets in
        # one real book copied it: `exit_status(code: 1)`, `count(subject: …, equals: 2)`,
        # `persists(subject: …)`. `*` and `<…>` cannot be mistaken for a value; `:` could,
        # because in a call position it is one.
        parts = [
            f"{p.name}{'*' if p.required else ''}=<{p.type}>"
            f"{' (path)' if p.path else ''}{' (locator)' if p.locator else ''}"
            for p in self.params
        ]
        rendered = f"{self.name}({', '.join(parts)})"
        if self.one_of:
            rendered += f" — one of {', '.join(self.one_of)}"
        return rendered


#: The vocabulary. Small on purpose: every entry has to name a defect class that a plausible
#: weaker assertion lets through, and every entry costs a harness callable that has to behave
#: identically under every driver. Growing it is a deliberate act, not a convenience.
CHECKS: tuple[CheckSpec, ...] = (
    CheckSpec(
        name="http_status",
        params=(
            CheckParam("code", "int", required=True),
            CheckParam("title", "str"),
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
            CheckParam("matches", "str"),
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
            CheckParam("matches", "str"),
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
        """The canonical spelling, argument order taken from the spec, not from the author.

        Identity, not display: this is what `qa validate` compares a scenario's invocation
        against, so two spellings of the same call have to render the same string or the
        binding check would refuse on whitespace.
        """
        spec = CHECK_BY_NAME[self.name]
        parts = [
            f"{p.name}={literal(self.args[p.name])}" for p in spec.params if p.name in self.args
        ]
        return f"{self.name}({', '.join(parts)})"


def _rooted(value: CheckValue) -> CheckValue:
    """A path argument with the JSONPath root token dropped, so one spelling survives.

    `$` is not a key. Every resolver in the harness strips it before walking, so the two
    spellings observe the same field — and identity here is textual, which would make the
    sigil the difference between a claim asserted and a claim unasserted.
    """
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
        # `repr` is the shortest round-tripping spelling, so `equals=0.5` reads back as 0.5.
        return repr(value)
    return '"' + value.replace('"', '\\"') + '"'


def parse_expression(text: str) -> ast.Expression:
    """*text* parsed as one Python expression, without Python's warnings about its literals.

    A check's arguments are regexes as often as not, and `matches="\\d+"` is the author's
    exact intent here, where Python would warn that `\\d` is an invalid escape. Left on,
    that warning is printed once per such bullet on every doctor run, ahead of the report,
    and a reader piping the report through `head` sees only the warnings.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.parse(text, mode="eval")


@dataclass(frozen=True, slots=True)
class Call:
    """One call expression's name and literal arguments, before any vocabulary reads it.

    The *grammar* of a declared call — a bare name, parentheses, literal arguments — is one
    thing; what the name means is another. `verify:` resolves a name against `CHECKS`, and an
    `arrange:` bullet resolves one against the acts a driver can perform (`ostler.acts`).
    Sharing the parse and not the vocabulary is what keeps the two keys spelling a call the
    same way while refusing different names for different reasons: a second parser would be
    free to accept `f(a=1,)` on one key and refuse it on the other, and nothing would notice.
    """

    name: str
    positional: tuple[Any, ...]
    keywords: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Malformed:
    """A call whose name is recoverable and whose arguments are not literals.

    Kept apart from "not a call at all": the name is what decides which form to suggest, and
    it is recoverable here, so a vocabulary can answer with *that* name's signature instead
    of handing back the whole vocabulary to an author who has already chosen from it.
    """

    name: str
    problem: str


def parse_call(value: str) -> "Call | Malformed | None":
    """*value* as a call with literal arguments, a `Malformed`, or `None` for neither.

    `None` means *this is not a call at all* — empty, unparseable, or an expression of some
    other shape. Each vocabulary classifies that case for itself, because the likeliest
    mistake differs per key: a test reference under `verify:`, a component's bare name under
    `arrange:`. What a non-literal argument means does *not* differ per key, so it is worded
    once, here.
    """
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
    """Why one `verify:` value is not a check, as a value rather than a sentence.

    A refusal *classifies* — a test reference written under the wrong key is a different
    finding from a typo in an argument, and it is `parse_check` that can tell them apart,
    because it is the thing that looked. Returning only prose threw that away: the one
    consumer that needed the class had to re-derive it, and did so by re-running the parse
    that had just failed, which can never recover a name from a value that is not a call.
    The two then disagreed — for 317 bullets in one real book the message said *put this on
    `tests:`* while the suggestion beside it listed all sixteen checks.

    The suggested bullet is composed here rather than by the caller because the class is what
    decides *which key* the value belongs under, and only a refusal that relocates a value
    knows that it moves.
    """

    #: What kind of thing was written. Not free text: callers branch on it, so a new kind is a
    #: new case at every branch, which is the point — a kind nobody handles is visible.
    kind: str
    #: The sentence that goes in the finding's message, explaining what was wrong.
    message: str
    #: The form that would have been accepted — one check's signature, the whole vocabulary,
    #: or the value itself where the value is fine and only the key under it is wrong.
    form: str
    #: The key this value belongs under, when that is a *different* key from the one it was
    #: found on. Empty when the value stays put and only its spelling was wrong.
    relocates_to: str = ""

    def bullet(self, key: str) -> str:
        """The suggested replacement bullet for a value found under *key*."""
        return f"- {self.relocates_to or key}: {self.form}"


def _unknown_check(name: str) -> Refusal:
    """The refusal for a name no `CHECKS` entry declares — one spelling for both callers."""
    known = ", ".join(sorted(CHECK_BY_NAME))
    return Refusal("unknown-check",
                   f"`{name}` is not a known check — the vocabulary is: {known}",
                   _vocabulary())


def parse_check(value: str) -> CheckCall | Refusal:
    """Parse one `verify:` value, or return the `Refusal` saying what was written instead.

    Parsing goes through `ast` rather than a regex because the grammar *is* a call: a regex
    that accepts `f(a="x, y")` also accepts things that are not calls, and the failure mode
    of a permissive grammar here is a declaration nobody can execute reaching the harness.
    Only literals are admitted — there is nothing to evaluate, and nothing that could be.
    The grammar itself is `parse_call`, shared with the other declared-call key; what this
    function adds is the one vocabulary that gives a name meaning.
    """
    text = _unwrap(value)
    if not text:
        return Refusal("empty", "empty", _vocabulary())
    parsed = parse_call(text)
    if parsed is None:
        return _not_a_call(text)
    spec = CHECK_BY_NAME.get(parsed.name)
    if spec is None:
        return _unknown_check(parsed.name)

    # Past this point the name is known, so the form that would have been accepted is *this*
    # check's signature and never the vocabulary: an author shown `http_status(code=…)` after
    # mis-calling `absent` learns nothing about `absent`, and guesses again on the next lap.
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
    """Whether *value* parses as a check call — the single test for "this is a check, not a
    command", shared by every caller that must tell the two apart.

    A runbook step's `run:`/`health:` bullet is shelled (`ostler.qa.stack.ensure_stack`, and
    `ostler.qa.book_fixtures` for a fixture's own steps); `verify:` is parsed. The vocabulary
    is closed — :func:`parse_check` already recognises it or explains why not — so this is
    not a heuristic: a bullet that parses here was written for `verify:` and put on the wrong
    key, and bash would have told the author so at bring-up time, one stage later than the
    doctor now does.
    """
    return isinstance(parse_check(value), CheckCall)


def _unwrap(value: str) -> str:
    """The bullet's value as markdown reads it: soft line breaks folded, a code span opened.

    A bullet is prose first, and books wrap prose at a column — `ostler fmt` keeps the break,
    so a long `subject="…"` arrives here split across lines. CommonMark renders that break
    as a space; Python's grammar rejects it inside a string literal. Parsing the rendered
    value rather than the raw bytes is what keeps a legal wrap from reading as a malformed
    check that an author then unwraps by hand, one node at a time.

    A code span is the other thing markdown does to a bullet value, and for the same reason:
    a book writing ``- verify: `visible(locator=…)` `` has written a check, and the backticks
    are how it is *rendered*, not part of what it says. Reading them as content refuses a
    correct call and — worse, because it is silent — hands the test-reference test a value
    ending in ``ts` `` rather than `ts`, so a misfiled path is reported as an unrecognisable
    one. `refs.normalize_ref` already states this rule for the sibling `code:` key; a value
    is decorated the same way under either.
    """
    return _CODE_SPAN.sub(r"\2", _SOFT_BREAK.sub(" ", value).strip()).strip()


_SOFT_BREAK = re.compile(r"[ \t]*\n[ \t]*")

#: A value that *is* one code span, not a value that merely contains one. The closing run must
#: match the opening run and nothing may sit outside it, so ``\`a\` and \`b\`` is left alone
#: rather than unwrapped to ``a\` and \`b``, inventing a value the book never wrote.
_CODE_SPAN = re.compile(r"^(`+)((?:(?!\1).)*)\1$", re.DOTALL)


def _not_a_call(text: str) -> Refusal:
    """Why this value is not a check — naming the likeliest mistake when it is recognisable.

    Overwhelmingly the thing written in `verify:` that is not a call is a *test reference*,
    which is the habit the vocabulary replaced (see this module's docstring). Saying only
    "expected `name(arg=…)`" leaves the author to invent a call for an observation they were
    never asked to name here, and the invented call is what fails on the next lap; saying
    where the reference belongs ends the loop in one.

    The relocation is the whole finding in that case, so it travels on the refusal: the value
    is not malformed, it is well-formed under `tests:`, and the suggestion is the value itself
    under that key. Handing back the vocabulary instead — which is what the caller did while
    this classification stopped at this function — contradicts the sentence beside it.
    """
    head = _CALL_HEAD.match(text)
    if head is not None:
        spec = CHECK_BY_NAME.get(head.group(1))
        if spec is not None:
            # The author chose a check — the text says so — and only the arguments are
            # unreadable. Recovering the name from the *text* rather than from the parse is
            # the point: the parse is the thing that just failed, so a name recovered only
            # from a successful parse is unavailable in exactly the case that needs it, and
            # every such author was handed the whole vocabulary to re-choose from.
            return Refusal(
                "bad-arguments",
                f"`{text}`: `{spec.name}` is a known check, but its arguments did not "
                f"parse — they are written `name=value`",
                spec.signature())
    if "::" in text or text.rsplit(".", 1)[-1] in _TEST_REF_SUFFIXES:
        return Refusal(
            "misfiled-test-ref",
            f"`{text}` is a code/test reference, not a check — a test id says which code "
            f"ran, not what was observed. Put it on `tests:` and declare the observation "
            f"here as a call, e.g. `visible(locator=…)`; `ostler checks` lists the "
            f"vocabulary",
            text, relocates_to="tests")
    return Refusal("not-a-call",
                   f"`{text}` is not a check call — expected `name(arg=…)`; see "
                   f"`ostler checks`",
                   _vocabulary())


#: A check name in call position, read lexically. Only ever consulted after `ast` has already
#: refused the text, and only accepted when the name is one `CHECKS` declares — so it cannot
#: shadow the test-reference arm below, no test id being spelled `<a known check>(`.
_CALL_HEAD = re.compile(r"^([A-Za-z_]\w*)\s*\(")


#: Enough to recognise a path written where a call belongs. Not a filesystem probe: the value
#: may name a test that does not exist yet, and the advice is the same either way.
_TEST_REF_SUFFIXES = {"py", "ts", "tsx", "js", "jsx", "go", "rs", "php", "dart", "java", "kt"}


def _vocabulary() -> str:
    """Every check's signature — the form to suggest when the author has not yet chosen one.

    This is the fallback and not the default. A refusal that recovered a name suggests *that*
    check's signature, because a fixed example teaches the wrong signature to every author
    whose check is not that one, which is exactly how `absent(locator=…)` and
    `emitted(subject=…)` get written. The whole vocabulary is right only where the name is
    genuinely unknown, because there the author has not chosen from it yet.

    It replaced `expected_form`, which took the *value* and re-derived the class by re-running
    `parse_expression` — the parse that had just failed — so it could never reach a per-check
    signature for any value that failed to parse, and never learned about the `tests:` case at
    all. The class now arrives on the `Refusal`, which is the thing that made it.
    """
    return " | ".join(spec.signature() for spec in CHECKS)


def bind(name: str, args: Mapping[str, Any]) -> CheckCall | Refusal:
    """A call assembled from an already-separated name and arguments, or why it is not one.

    The tail of `parse_check`, shared with the other direction: a `verify:` bullet arrives as
    text and is parsed, while a scenario's invocation arrives as a name and a dict recovered
    from its parsed body. Both have to canonicalise through the same rules, because the whole
    binding check is a comparison of the two spellings — and a rule applied on one side only
    would refuse a plan that invokes exactly what the book declared.
    """
    spec = CHECK_BY_NAME.get(name)
    if spec is None:
        return _unknown_check(name)

    # Every refusal below names a check that exists, so the form to suggest is that check's
    # signature. The name is what makes the difference recoverable, and it is recoverable
    # here and nowhere downstream.
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
    # `bool` before `int`: a bool *is* an int in Python, so `count(equals=true)` would type
    # as an integer and reach the harness as 1. A `scalar` keeps its bool as a bool.
    if declared not in ("bool", "scalar") and isinstance(value, bool):
        return False
    if not isinstance(value, _TYPES[declared]):
        return False
    if declared == "str[]":
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    return True


#: A book is not Python, and the people writing `verify:` bullets write JSON's booleans. Both
#: spellings parse; `literal` emits the lowercase one, so a call and its canonical rendering
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
