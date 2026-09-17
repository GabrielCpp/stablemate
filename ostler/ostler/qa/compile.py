"""Compile a QA plan skeleton out of the book, without reading the implementation.

A plan written by looking at the code tests what the code already does. The book is the
only artefact that says what the code is *supposed* to do, and — unlike the code — it says
it in a grammar: `verify:` values are parsed calls (`checks.parse_check`), `route:` and
`entry:` are addresses, and `attributed_checks` already binds each call to the one claim it
observes. That is enough to emit the assertion half of a plan mechanically, with every
`covers=` list correct by construction rather than by an author's recollection.

What the book does *not* carry is the arrangement: how to reach the state the assertion
observes, in what order, with which fixture. Those come out as `TODO` markers naming the
obligation they block, and they are the only thing left for a human or a model to fill.

The count of markers is the point as much as the plan is. An obligation that is owed live
evidence and declares no check is a claim the book asserts and does not say how to observe;
a compiled plan that comes back thin is a measurement of book construction, taken without
an agent turn and without ever opening the implementation.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import get_args as _get_args

from ostler.checks import CHECK_BY_NAME
from ostler.checks import _rooted
from ostler.markdown import extract_refs
from ostler.qa import references
from ostler.routes import literal_route, why_unreadable
from ostler.qa.outcome import QaOutcome


#: Gap kinds that describe the *arrangement* a scenario stands on rather than the observation
#: it makes. Two independent axes land on one obligation id: whether the claim was observed,
#: and whether the state it was observed in was set up the way the book says. A precondition
#: gap says the scenario reaches the claim through a scaffold — a fixture nobody arranged, a
#: trigger compiled to a bare click, a screen whose preconditions the book never declared —
#: while the assertion it ends on is real and does claim its id. `unidentifiable-screen` is
#: the same shape seen from a third axis: the scenario's own assertions are compiled and
#: observed, and what was withheld is the placement grading of a screen nothing could
#: establish as the subject. `unparsed-capture-bullet` is a fourth: the claim is observed and
#: does claim its id, and what the unreadable bullet cost is a fact the *rest* of the scenario
#: stands on. `uncaptured-declaration` is a fifth and the same shape once more: the claim is
#: observed and claims its id, and what went unbound is a value some *other* obligation would
#: have read. It is here for a reason the other four make obvious only in hindsight — before
#: this kind existed, a UI-locator capture on a routed obligation minted an `uncompilable-claim`
#: beside that obligation's own compiled `covers=[...]`, which is exactly the contradiction the
#: mirror assert exists to catch, and it went unseen only because no book in the corpus declares
#: a non-empty `capture:`. So these stack with a
#: `covers=[...]` on purpose, and the mirror assert in `compile_plan_gaps` reads past them;
#: every other kind says nobody looked, and stacking *that* with a claim is a contradiction.
#: A plan still carrying these is not a plan whose greens mean anything — `doctor` reports
#: them to a human exactly like any other gap, which is the part that is not relaxed here.
_ARRANGEMENT_GAPS = frozenset({
    "unresolved-precondition",
    "screen-preconditions-undeclared",
    "unarranged-interaction-precondition",
    "unidentifiable-screen",
    "unparsed-capture-bullet",
    "uncaptured-declaration",
})

#: Every kind `compile_plan` can mint. Declared rather than discovered, because the set is
#: read from two directions and neither direction can see the other: the minting sites are
#: scattered across this file (some passing a kind through a variable, so no reader can
#: recover them from the literals), and `doctor.gap_findings` translates the kind into a
#: doctor code through an if/elif chain that ends in a catch-all. A catch-all is what makes
#: the drift invisible — an unenumerated kind does not fail there, it produces a valid
#: `Finding` carrying the wrong code, and a wrong answer is not observable as a missing case.
#: So the vocabulary is stated once here, and
#: `test_every_gap_kind_has_its_own_branch_in_the_doctor_bridge` asserts the two sides
#: against it. A new kind fails that test until someone decides what doctor should call it.
GAP_KINDS = frozenset({
    "uncompilable-claim",
    "unresolved-precondition",
    "unreachable-screen",
    "screen-preconditions-undeclared",
    "needs-snapshot",
    "needs-out-of-band-observation",
    "undeclared-entry-url",
    "unresolved-extends",
    "undeclared-check-locator",
    "unstated-claim-combiner",
    "no-verify-declared",
    "unarranged-state",
    "unarranged-journey",
    "unarranged-request-body",
    "unarranged-interaction-precondition",
    "unidentifiable-screen",
    "unparsed-fixture",
    "unparsed-capture-bullet",
    "unparsed-check-bullet",
    "uncaptured-declaration",
    "needs-target-backend",
    "needs-multi-target-runtime",
})

#: The kinds that say *this compiler* ran out, not that the book did. Every other kind names
#: something an author can go and write; these two name a path nobody has built here, so a
#: book that mints one is already correct and has nothing to repair. `doctor` reports them
#: like any other gap — the difference is on the okf-builder side, where they are classified
#: `NON_ACTIONABLE_CODES` and never drain into a repair turn (see
#: `workflows/src/workhorse_workflows/okf_builder/shared/checkpoint.py`), the same treatment
#: `needs-snapshot` and `needs-out-of-band-observation` already get for a harness limit.
HARNESS_LIMIT_GAPS = frozenset({
    "needs-target-backend",
    "needs-multi-target-runtime",
})


@dataclass(frozen=True)
class Gap:
    """One obligation left uncompiled, and why — `compile_plan`'s structured gap report.

    `checkpoints=[]` and `forbid=[]` are not gaps: they are always emitted, for every
    scenario, whether or not the book gave a reason — there is nothing conditional to
    report. Everything here is instead a fact compile.py discovered about one obligation
    while trying to compile it, in the vocabulary `doctor` reads rather than redefines:
    `unresolved-precondition` for a state the plan cannot yet reach (a missing fixture, an
    unresolved reference, a template variable, a request body the book never wrote), and
    `uncompilable-claim` for a node with no action to observe at all — no fixture or
    capture could supply one, so it is not a precondition gap.

    Which of those two a kind is decides whether it may stand beside a compiled claim for the
    same id — see `_ARRANGEMENT_GAPS` above and the mirror assert in `compile_plan_gaps`.
    """
    obligation_id: str
    kind: str
    detail: str

#: What each check is handed is declared on the check itself (`CheckSpec.observes` and
#: `.out_of_band`, in `ostler.checks`), not guessed here from its name — `_operand` below
#: never compares against a literal check name. A `"response"` check reads the HTTP
#: response — status line, headers, problem body; `"body"` walks a decoded document;
#: `"page"` addresses the rendered screen; `"keyboard"` addresses it through a real keypress
#: dispatched at it, not a read, which is why it is a channel of its own rather than folded
#: into `"page"` — a driver can render a screen without being able to drive a key through it.
#: Of the rest, `.out_of_band` and `.observes` vary
#: independently: `.out_of_band` (a subscriber's event log, a re-read that cannot come
#: through the writing session) compiles to a `needs-out-of-band-observation` gap
#: regardless of shape. Otherwise a `"subject"` check is read once, after the action, from
#: what the scenario is already holding, so it compiles for real; a `"subject-pair"` check
#: wants a before-and-after this compiler has no snapshot mechanism to take, so it compiles
#: to a `needs-snapshot` gap.
#:
#: Observability is a relation between what a claim needs and what a driver can supply — a
#: property of neither one alone. A claim declares its channel (`CheckSpec.observes`); a
#: driver declares which channels it can supply (`DriverSpec.observes` below); a gap fires
#: only when the *relation* is empty for the driver actually chosen. Playwright, for
#: instance, can see `"response"` and `"body"` too (`page.expect_response`), so a
#: `"response"`-observed check reaching the page path is not inherently unobservable the way
#: a `"subject"` one is — this compiler simply has no page-scenario arrangement for it yet.
#: `_unobservable_gap` tells those two cases apart and names both the driver and the missing
#: channel, rather than asserting a blanket "not observable from a Playwright driver" that
#: was only ever true back when Playwright was assumed to see nothing but the page.


@dataclass(frozen=True)
class DriverSpec:
    """A driver's declared observation channels — the other half of the observability relation.

    Duplicated in `ostler.qa.harness.ostler_qa`, which cannot import from here: that harness
    is stdlib-only and runs under the *target project's* interpreter, where `ostler` is not
    installed (see `ostler.qa.drivers.DEFAULT_VIEWPORT` for the same pattern). The two
    declarations have to agree by hand.
    """
    name: str
    observes: frozenset[str]


#: The python driver drives HTTP calls directly: it can read the response line/headers, a
#: decoded body, and a subject already held by the scenario. It cannot hold a rendered page.
PYTHON = DriverSpec("python", frozenset({"response", "body", "subject"}))

#: The Playwright driver renders a real page and can also observe the response/body of any
#: navigation or fetch it drives (`page.expect_response`) — but it never holds a bare
#: in-process "subject" value the way the python driver does. `"keyboard"` is here and
#: nowhere else: it is not a read of the page but a real keypress dispatched at it
#: (`page.keyboard.press`), and only this driver can fire one.
PLAYWRIGHT = DriverSpec("playwright", frozenset({"page", "response", "body", "keyboard"}))

#: Maestro drives a mobile UI: it can see the rendered screen and read back a subject value
#: from it, but has no notion of an HTTP response or body, and no keyboard to dispatch a
#: press through — touch has no Tab order. Named here so the compiler can refer to it; it
#: has no compile path of its own yet (see `ostler.qa.harness.ostler_qa` for its runtime).
MAESTRO = DriverSpec("maestro", frozenset({"page", "subject"}))


def _observes(name: str | None) -> str | None:
    """What check *name* is handed to look at, or `None` for an unknown/missing check."""
    spec = CHECK_BY_NAME.get(name) if name else None
    return spec.observes if spec is not None else None


def _out_of_band(name: str | None) -> bool:
    """Whether *name* observes through a channel this compiler has no handle on.

    See `CheckSpec.out_of_band`: declared per-check, not inferred here from the name or
    from `observes` — shape and channel vary independently, so a check compiles for real,
    `needs-snapshot`, or `needs-out-of-band-observation` by reading two fields off the spec
    it was handed, never a literal check name.
    """
    spec = CHECK_BY_NAME.get(name) if name else None
    return spec.out_of_band if spec is not None else False


def _unobservable_gap(oid: str, name: str | None, driver: DriverSpec) -> Gap:
    """*driver* cannot serve *name* — a real gap, not a silently dropped row.

    Two distinct reasons collapse to the same gap kind but get different wording: the
    channel may be one *driver* genuinely has no way to supply (the relation is empty), or
    it may be one the driver can supply in principle but this compiler has no page-scenario
    arrangement for yet (true today of `"response"`/`"body"` under Playwright). Either way
    the message names both the driver and the missing channel, so a reader is never left
    needing to already know which driver was picked.
    """
    observes = _observes(name)
    what = f"a {observes}" if observes else "an unknown check"
    if observes is not None and observes in driver.observes:
        return Gap(oid, "uncompilable-claim",
                    f"`{name}` observes {what}, which the {driver.name} driver can see, but "
                    f"this compiler has no page-scenario arrangement for it yet")
    return Gap(oid, "uncompilable-claim",
               f"`{name}` observes {what}, not observable from the {driver.name} driver")


_ROUTE = re.compile(r"^\s*`?\s*(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(\S+?)\s*`?\s*$", re.I)
_IDENT = re.compile(r"[^0-9a-zA-Z]+")

#: A screen's `visible(...)` bullets are never addressed by parsing its `route:` bullet as an
#: HTTP verb+path (that is what `_ROUTE` is for, and it is deliberately never extended to
#: accept a bare path as an implicit GET). They are addressed by *navigating there* — walking
#: the click-path `context["navigation"][surface]["routes"][screen]` already carries (derived
#: by `ostler.reach`, at context-build time, per `ostler.qa.context._navigation` — compile.py
#: never imports `reach` or touches a live `Graph`, it only ever reads the packet). See
#: `_compile_page_scenarios` below for the partitioning this drives.


def _route(obligation: dict[str, Any]) -> tuple[str, str] | None:
    """The HTTP method and path template this obligation's node is addressed by.

    Two declared spellings reach here. A `screen` states its address as one `route:` bullet,
    `` `VERB /path` `` (matched by `_ROUTE` above, kept for that spelling). An `endpoint` states
    it as two bullets, `method:` and `path:` (`registry.py`'s `endpoint` profile — it declares no
    `route:` at all), and those are read directly rather than joined into one string for `_ROUTE`
    to re-parse: the path the book wrote is the exact template it wrote, not what a regex would
    recover from a string built for the other node type's spelling.
    """
    locators = obligation.get("locators", {})
    for value in locators.get("route", []):
        matched = _ROUTE.match(value)
        if matched:
            return matched.group(1).upper(), matched.group(2)
    method = _bullet_value(next(iter(locators.get("method", [])), None))
    path = _bullet_value(next(iter(locators.get("path", [])), None))
    if method and path:
        return method.upper(), path
    return None


def _concrete_path(rows: list[dict[str, Any]]) -> str | None:
    """A real path from a declared check, preferred over the route's `{id}` template.

    `http_status(409, title="Stale Policy", path="/api/policies/pn-1001")` names the exact
    request the book expects that refusal from. Substituting a path variable is guesswork;
    reading the one the book already wrote is not.
    """
    for row in rows:
        path = row.get("args", {}).get("path")
        if isinstance(path, str) and path.startswith("/"):
            return path
    return None


def _expect_status(rows: list[dict[str, Any]]) -> int | None:
    for row in rows:
        if row.get("name") == "http_status":
            code = row.get("args", {}).get("code")
            if isinstance(code, int):
                return code
    return None


def _lit(value: Any) -> str:
    """A Python literal spelled the way the repo's formatter would spell it.

    `repr` picks single quotes, which every other plan in the tree does not use; the
    compiled file has to read like one an author wrote or the diff against a filled-in
    version is all quotation marks. `json.dumps` picks the right quotes and the wrong
    booleans and the wrong absence — `absent=false` and `base_url=null` are the book's
    and JSON's spelling and both are a `NameError` in Python — so the three literals
    JSON and Python disagree about are spelled here.
    """
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, list):
        return "[" + ", ".join(_lit(item) for item in value) + "]"
    return json.dumps(value)


def _kwargs(args: dict[str, Any]) -> str:
    """Render a check's declared arguments verbatim, wrapping only literals holding a reference.

    Every declared argument is rendered, including one the operand was built from. A check call
    states two things, read by two different readers: the operand is what the scenario went and
    got, which `VERIFIERS` collapses to a verdict, and the arguments are the claim's own
    statement of what it is about, which `ostler qa validate` matches against the `verify:`
    bullet and which the evidence record carries as the expectation. The claim is not derivable
    from the observation, so resolving `locator=` into an expression does not repeat it — and
    dropping it emits a call the check's own signature refuses, since `locator` is `required`.

    `qa.resolve(...)` is the harness's one explicit substitution entry point (Fix 2) — a
    literal with no `@node.key`/`$name` embedded in it stays a plain literal, since wrapping
    it would cost nothing today but would ask the harness to scan it every run for a
    reference it will never contain.
    """
    parts = []
    for name, value in args.items():
        if isinstance(value, str) and references.find_references(value):
            parts.append(f", {name}=qa.resolve({_lit(value)})")
        else:
            parts.append(f", {name}={_lit(value)}")
    return "".join(parts)


def _trailing_comment(text: str) -> str:
    """*text*, flattened onto one line, safe to follow real code on the same line.

    A wrapped book bullet carries an embedded newline; appended raw after a statement
    (`expr.click()  # trigger: {text}`), that newline ends the statement mid-line and
    turns the rest of the sentence into code. A trailing comment can never itself hold
    a newline without breaking the line it trails, so — unlike a standalone comment —
    there is no multi-line form to fall back to: the prose is collapsed instead.
    """
    return " ".join(text.split())


def _prose_comment(text: str, *, label: str = "") -> list[str]:
    """*text* rendered as one or more `#`-prefixed lines, each four-space indented.

    Book prose wraps across lines; a bare `f"    # {text}"` embeds that newline
    unescaped, which ends the comment token and turns the wrapped remainder into
    code. Every line of the wrap gets its own `#` so the emitted source parses
    regardless of how the source bullet wrapped.
    """
    first, *rest = text.splitlines() or [""]
    lines = [f"    # {label}{first}"]
    lines.extend(f"    #   {line}" for line in rest)
    return lines


def _slug(path: str) -> str:
    stem = path.rsplit("/", 1)[-1].removesuffix(".md")
    ident = _IDENT.sub("_", stem).strip("_").lower()
    return ident or "book"


def _owed(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [o for o in context.get("obligations", []) if o.get("required", True)]


def book_digest(context: dict[str, Any]) -> str:
    """A digest of *context*'s obligation id set — what a compiled plan's `book=` names.

    The ids, not the tree: the plan derives from the obligations a compile pass owed proof
    for, and an id-set digest is stable under a book edit that reformats or reorders without
    changing what is owed, so it does not fire on noise. Sorted before hashing so two packets
    naming the same set in a different walk order agree. `_owed` (not raw `obligations`) —
    a `required: False` context-only obligation was never a claim the plan owed a scenario
    for, so its coming or going is not a reason to call the plan stale.
    """
    ids = sorted(str(o["id"]) for o in _owed(context) if o.get("id"))
    return hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()


#: D1's dispatch table (§4.1): `(the obligation's own node type) x (owning surface's runbook
#: `driver:`)`. The node type is the obligation's, not its link target's: for a step
#: obligation the two coincide, and where they diverge — a `flow`'s own `start:`/`end:`, a
#: `component`'s `states:` — the claim belongs to the node that wrote it, which is why those
#: types are handled by `_OBSERVE_ROW` below rather than by a row here.
#: A cell this table has no row for, or names no target in — the `—` cells, `endpoint`x`cli`,
#: `interaction`x`http` — is a gap, never a default (`_dispatch_target` below), the same as a
#: `driver:` the book never states.
_DISPATCH_TABLE: dict[str, dict[str, str]] = {
    "interaction": {"web": "playwright", "mobile": "maestro"},
    "endpoint": {"web": "http", "mobile": "http", "http": "http"},
    "command": {"web": "cli", "mobile": "cli", "http": "cli", "cli": "cli"},
    "invocation": {"web": "in-process", "mobile": "in-process", "http": "in-process", "cli": "in-process"},
    "method": {"web": "in-process", "mobile": "in-process", "http": "in-process", "cli": "in-process"},
}
#: The node types a book documents that **nobody performs**. A `flow` orders steps that are
#: performed; a `component` and a `screen` are places a claim is true. D1's table asks "what
#: performs this step", and for these there is no step to perform — only a check to run, which
#: is emitted by whatever drives the surface the claim's subject lives on. So they key on the
#: `driver:` alone, with no action type to cross it with, and `context.py` stamps a flow's
#: `surface` from the node its own `start:`/`end:` bullet names (`_linked_surface`) so a journey
#: that crosses surfaces is observed on the one it actually ends on.
_OBSERVED_TYPES = frozenset({"flow", "component", "screen"})
#: Every driver can observe, which is what makes this a row and not a table: an `http` driver
#: cannot *perform* an interaction (`_DISPATCH_TABLE` leaves that cell empty on purpose) but it
#: can assert a status on a journey that ends at an endpoint.
_OBSERVE_ROW: dict[str, str] = {
    "web": "playwright", "mobile": "maestro", "http": "http", "cli": "cli",
}
#: Targets this compiler actually builds a compile path for. `maestro` and `in-process` are
#: correct cells in D1's table (D9: mobile is a row in the table, not a backend to build) that
#: this compiler leaves inert until a book exercises them — `_dispatch_target` still names the
#: target so the gap it returns says exactly what the table says, not "no row for this."
_BUILT_TARGETS = frozenset({"playwright", "http", "cli"})


def _dispatch_target(node_type: str, driver: str | None) -> tuple[str | None, str]:
    """D1's table — or `_OBSERVE_ROW`, for a type nobody performs — read once per obligation.

    `(target, "")` when it names a target this compiler builds; `(None, detail)` when the
    table has no row, no cell, or no `driver:` to key on — a gap, per D1's "a step whose driver the book does not determine is not
    emitted," never a default; `(target, detail)` when the table names a real target this
    compiler does not build yet (`maestro`, `in-process`), so the caller can still gap it
    honestly rather than mistake it for "no row for this type."
    """
    row = _OBSERVE_ROW if node_type in _OBSERVED_TYPES else _DISPATCH_TABLE.get(node_type)
    if row is None:
        return None, (
            f"the book links this step to a {node_type or 'untyped'!r} node, which D1's "
            "dispatch table (§4.1) names no row for"
        )
    if driver is None:
        return None, (
            "the surface this step's node lives on states no `driver:` on any `runbook`, so "
            "D1's dispatch table (§4.1) cannot determine what performs this step"
        )
    target = row.get(driver)
    if target is None:
        return None, (
            f"D1's dispatch table (§4.1) names no target for a {node_type} step on a "
            f"{driver!r}-driven surface"
        )
    if target not in _BUILT_TARGETS:
        return target, (
            f"D1's dispatch table (§4.1) names {target!r} for a {node_type} step on a "
            f"{driver!r}-driven surface, but this compiler builds no {target} path yet"
        )
    return target, ""


def _gap_cli_obligations(obligations: list[dict[str, Any]], gaps: list[Gap]) -> None:
    """Command-linked obligations the CLI path owes evidence for, gapped rather than compiled.

    `ostler_qa.py`'s `Qa.tool(name).run(*argv)` and its `exit_status` verifier already fully
    support this at runtime — the gap is not there. It is that a `command` node's
    `usage:`/`flags:`/`args:` bullets are prose ("tally import <file> [--dry-run]"), not a
    structured argv, and no book in this repo declares a `command` node to check a derivation
    against. Inventing a parse for untested prose here is the "rewrite the compiler from
    scratch and it still holds" mistake D1 warns against, so this names the real reason
    precisely — a CLI-dispatched obligation reaching here is not route-less the way an HTTP
    one is, and saying so beats routing it through the unrelated "no `route:`" message.
    """
    for obligation in obligations:
        gaps.append(Gap(
            str(obligation["id"]), "uncompilable-claim",
            "the book states this command's `usage:`/`flags:`/`args:` as prose, not a "
            "structured invocation this compiler can turn into `qa.tool(...).run(...)`",
        ))


def _declared_captures(obligations: list[dict[str, Any]]) -> set[tuple[str, str]]:
    """Every `(obligation id, capture name)` the packet declares — the set to account for."""
    return {
        (str(obligation["id"]), str(capture["name"]))
        for obligation in obligations
        for capture in obligation.get("capturesDeclared") or []
        if capture.get("name")
    }


def _decline_captures(
    obligations: list[dict[str, Any]],
    gaps: list[Gap],
    captured: set[tuple[str, str]],
    *,
    because: str,
) -> None:
    """Gap the captures this builder will not emit, from inside the builder that declined.

    A declared capture reaches exactly one builder that can act on it, and every other builder
    used to drop it by not looking — no emitted call, no gap, nothing in the plan or the report
    that says the book asked for something. An unconsumed declaration is indistinguishable from
    an absent one, and the reader who would notice is the author who wrote the bullet.

    So the decline is minted here rather than reconstructed by the caller: the stage that defers
    is the only stage that can say *why* it deferred, and "the Playwright builder has no way to
    bind a value out of the page" and "a journey compiles its steps' captures where those steps
    live" are different facts that a diff of declared-against-emitted would flatten into one.
    Both halves land in `captured`, which the totality assert in `compile_plan_gaps` reads: a
    pair in neither the emitted nor the declined half is the silent drop this exists to prevent.
    """
    for obligation in obligations:
        for capture in obligation.get("capturesDeclared") or []:
            name = capture.get("name")
            if not name:
                continue
            captured.add((str(obligation["id"]), str(name)))
            gaps.append(Gap(
                str(obligation["id"]), "uncaptured-declaration",
                f"capture {str(name)!r} from {str(capture.get('from', ''))!r} is declared on "
                f"this node and {because}",
            ))


def _has_screens(navigation: dict[str, Any]) -> bool:
    """Condition 1: a book with zero screen nodes on every surface grows no Playwright target.

    `navigation[surface]["counts"]["screens"]` is `_navigation`'s own tally (0 for the zeroed
    stub it emits when `reach.screens_of` finds nothing on that surface) — reading it here is
    exactly the "book has screen nodes" test, without compile.py re-deriving it from a graph
    it never touches.
    """
    return any(
        int(surface_nav.get("counts", {}).get("screens", 0)) > 0
        for surface_nav in navigation.values()
    )


def _split_by_entry_url(
    obligations: list[dict[str, Any]],
    navigation: dict[str, Any],
    base_url: str | None,
    gaps: list[Gap],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Partition *obligations* on whether their surface's target `base_url` is known.

    A target is the pairing of a driver with a service, and naming it after only one of the
    two leaves the other undetermined — so one target is emitted **per surface**, not one
    shared across however many surfaces happen to feed this driver kind. Each surface may
    state its own address — `navigation[surface]["entryUrl"]`, Phase 2h's per-surface
    resolution in `reach.entry_origin`. A surface with nothing stated falls back to the CLI
    `--base-url` only when one was actually passed (`base_url is not None`); with neither,
    every obligation on that surface is gapped `undeclared-entry-url` and dropped from the
    returned list rather than silently compiled against a fixed, unrelated address.

    The second return value is every surface's resolved address, keyed by surface — the
    caller emits one `target(...)` per entry, never a single one picked among several.
    """
    resolved_by_surface: dict[str, str | None] = {}
    for obligation in obligations:
        surface = str(obligation.get("surface") or "")
        if surface in resolved_by_surface:
            continue
        entry_url = navigation.get(surface, {}).get("entryUrl") if surface else None
        resolved_by_surface[surface] = entry_url or base_url

    kept: list[dict[str, Any]] = []
    for obligation in obligations:
        surface = str(obligation.get("surface") or "")
        url = resolved_by_surface[surface]
        if url is None:
            gaps.append(Gap(
                str(obligation["id"]), "undeclared-entry-url",
                f"surface {surface!r} states no `entry-url:` on a `server` or `runbook` node, "
                "and no --base-url was passed to fall back on",
            ))
            continue
        kept.append(obligation)

    resolved = {surface: url for surface, url in resolved_by_surface.items() if url is not None}
    return kept, resolved


def _target_var(surface: str, kind: str) -> str:
    """The variable (and literal target `name`) one surface's `kind` ("api"/"web") target gets."""
    return f"{_slug(surface)}_{kind}"


def _screen_routes(context: dict[str, Any]) -> dict[str, str]:
    """Each screen file's `route:`, as `qa context` read it off the book.

    Read from the packet rather than recomputed here, so the compiler and the driver that
    grades an arrival are answering the same question off the same reading — this file never
    opens a `Graph`, and a second reading of the same bullet is a second thing to keep true.
    """
    return {
        str(path): str(route)
        for path, route in (context.get("screenRoutes") or {}).items()
    }


def _node_locator_index(context: dict[str, Any]) -> dict[str, dict[str, list[str]]]:
    """Every node's own `locators`, keyed by node id — including ones with no *required* claim.

    A navigation hop can walk through an interaction the diff itself did not reach (an
    intermediate screen unrelated to the change), so this reads every obligation the packet
    carries, not just `_owed`'s required subset — a hop with nothing to look up here is a gap,
    not a `KeyError`.
    """
    index: dict[str, dict[str, list[str]]] = {}
    for obligation in context.get("obligations", []):
        node_id = obligation.get("node")
        if node_id and node_id not in index:
            index[node_id] = obligation.get("locators", {})
    return index


#: The book writes a bullet value as ordinary markdown prose, which means a value can be
#: wrapped in a code span (`` `button` ``) the same way `route:` values are (`_ROUTE` already
#: strips this). `_page_locator_expr` reads the same grammar and has to strip it the same way —
#: a backtick carried verbatim into `get_by_role("`button`")` is not a role, it is a spelling of
#: one, and Playwright raises `InvalidSelectorError` on it at run time instead of failing an
#: assertion, which is a worse outcome than either a pass or a gap.
_CODE_SPAN = re.compile(r"^\s*`?\s*(.*?)\s*`?\s*$")

#: The book's explicit sentinel for "this bullet has nothing to say" — `role: none` / `name: none`
#: — is prose, not a value. Treating the literal string `"none"` as a real role or accessible
#: name compiles to a locator that structurally cannot match anything real (`by_role("alert",
#: name="none")` on an alert with no accessible name at all), which is the same "plausible but
#: wrong" failure mode Finding 1 fixes for the assertion operand, just one layer further down —
#: a false *failure* on a correct app instead of a false pass.
_NONE_SENTINEL = "none"


def _bullet_value(raw: str | None) -> str | None:
    """*raw*, stripped of a wrapping code span, with the book's `none` sentinel read as absent."""
    if raw is None:
        return None
    match = _CODE_SPAN.match(raw)
    assert match is not None, "_CODE_SPAN matches any string (its inner group is `.*?`)"
    value = match.group(1).strip()
    if not value or value.lower() == _NONE_SENTINEL:
        return None
    return value


#: Playwright does not validate a `get_by_role` role name — an unrecognized one is not an error,
#: it is a query that matches nothing, exactly as silent as the vacuity Finding 1 fixes. The
#: matchable set has to be carried as data rather than guessed at, and it is derived from the
#: installed `playwright` package's own typed role literal rather than hand-copied, so it never
#: drifts from the version this repo actually pins. Three of its 82 members are excluded on
#: purpose, not by omission: `none` and `presentation` are the two real ARIA roles that both mean
#: "this element has no semantic role" (so `role: none` in the book, even read as prose rather
#: than as `_bullet_value`'s sentinel, names something Playwright's accessibility tree never
#: surfaces), and `generic` is the role an element falls back to when it has no better one — all
#: three are real, spellable roles that structurally never match a `get_by_role` query.
#: `None` here means "the matchable set could not be derived," never "validation is optional."
#: A tree missing the `qa` extra (so `playwright` is not importable) cannot correctly compile a
#: Playwright-targeted plan in the first place; treating that as permission to skip role
#: validation would silently restore Finding 5's exact defect (`role: generic` compiling to
#: `by_role("generic")` again) with no signal that anything degraded. So `_page_locator_expr`
#: treats "the role set is unknown" the same as "no role is in it" — every role falls through to
#: `selector:` — which degrades toward a visible, blocking gap rather than a silent false locator.
try:
    from playwright._impl._api_structures import AriaRole as _AriaRole
    _MATCHABLE_ROLES: frozenset[str] | None = frozenset(_get_args(_AriaRole)) - {
        "generic", "none", "presentation",
    }
except ImportError:  # pragma: no cover - the `qa` extra is what installs playwright
    _MATCHABLE_ROLES = None


def _page_locator_expr(locators: dict[str, list[str]]) -> str | None:
    """A concrete Playwright locator expression built from a node's own book-declared locators.

    `_verify_visible` (the harness's `visible` check implementation) calls `observed.is_visible()`
    when `observed` has that method, and otherwise falls back to `bool(observed)` — which is
    always `True` for a Playwright `Page`. Handing it the bare `page` object (as the older,
    HTTP-oriented `_operand` does for every `page`-observed row) is a check that can never fail;
    this builds a real `Locator` instead, from `role`/`name` (preferred — the same identity a
    person clicking through the screen would use) or `selector` (the escape hatch a `role:`-less
    component's book entry gives it).

    `role`/`name` are read through `_bullet_value`, so a code-span-wrapped value and the `none`
    sentinel are both handled before a locator is built, not transcribed into one.
    """
    role = _bullet_value(next(iter(locators.get("role", [])), None))
    if role is not None and (_MATCHABLE_ROLES is None or role not in _MATCHABLE_ROLES):
        # A role that is real prose but not a matchable ARIA role (`generic`, `presentation`), one
        # that is not a recognized role at all (a book typo), or one this tree cannot even check
        # (`_MATCHABLE_ROLES is None` — playwright not importable) has no `get_by_role` query that
        # is known to match it — fall through to `selector:` exactly as if no role had been
        # declared, rather than guess.
        role = None
    name = _bullet_value(next(iter(locators.get("name", [])), None))
    selector = _bullet_value(next(iter(locators.get("selector", [])), None))
    if role and name:
        return f"qa.by_role({_lit(role)}, name={_lit(name)})"
    # A role with no name is not addressable on its own: Playwright's strict mode raises rather
    # than returning a false result when `get_by_role(role)` resolves to more than one element on
    # the page (the common case — `role: textbox`/`role: link` name real pages, not single
    # elements), and the compiler has no runtime page to check that against statically. `role:`
    # alone is therefore never emitted as a locator; a node that names a role but no accessible
    # name falls through to `selector:` (which is what `name: none` is telling the book to use),
    # or gaps if it has neither.
    if selector:
        return f"qa.by_css({_lit(selector)})"
    return None


def compile_plan(
    context: dict[str, Any],
    *,
    story: str,
    run_id: str | None = None,
    base_url: str | None = None,
) -> str:
    """Render a `qa_plan.py` skeleton covering every obligation the change owes live proof.

    The plan is not expected to pass as emitted — a POST whose body the book never wrote
    cannot be. It is expected to *validate*: `ostler qa validate` reports zero uncovered
    obligations against it exactly when the book declared a check for everything it owes.

    `base_url` is a fallback, not a default: each target's real `base_url` is read off the
    book (`context["navigation"][surface]["entryUrl"]`, Phase 2h), and this is used only when
    a surface's book states none *and* a caller explicitly passed this. Left `None`, a surface
    with nothing to say compiles an `undeclared-entry-url` gap instead of silently defaulting
    to a fixed address that has nothing to do with the surface being tested.
    """
    source, _gaps = compile_plan_gaps(context, story=story, run_id=run_id, base_url=base_url)
    return source


def compile_plan_gaps(
    context: dict[str, Any],
    *,
    story: str,
    run_id: str | None = None,
    base_url: str | None = None,
    covered_ids: set[str] | None = None,
) -> tuple[str, list[Gap]]:
    """`compile_plan`'s source, plus the structured gap report it compiled alongside it.

    Same rendering, same TODO markers in the source — this is the one place that also
    hands back *why* each conditional TODO fired, as `(obligation id, gap kind, detail)`,
    for a caller (`doctor`) that wants to map book debt to obligations without re-parsing
    the compiled Python. `covered_ids`, if a caller passes a set in, is populated as a
    side effect with every id a `covers=[...]` was actually emitted for —
    `deferred_obligations` below is the caller that needs it, to tell a gapped-but-still-
    covered obligation (the `open-new-widget` `_ARRANGEMENT_GAPS` shape) from one this
    compiler produced no evidence for at all. Not a return value: every existing caller
    unpacks a 2-tuple, and this is opt-in rather than a break to all of them.
    """
    gaps: list[Gap] = []
    # Every id an emitted `covers=[...]` actually names — filled in by the same code that
    # writes each `covers=[...]` list below, never reconstructed from the compiled source
    # after the fact. The totality assert (below) and its mirror both read off this and `gaps`.
    covered_ids = set() if covered_ids is None else covered_ids
    owed = _owed(context)
    # A claim whose nested list never said how its children combine is *undetermined*, and the
    # rule about undetermined form is that nothing executable comes out of it: the check above
    # the list observes either every child or exactly one of them, and emitting it against this
    # child picks the reading that fails open — a refutation filed as a proof. Partitioned out
    # here, before any scenario sees it, so no later stage has to remember not to. The packet
    # stamped it (`qa context` reads `registry.undetermined_claims`); this only obeys the stamp.
    undetermined = [o for o in owed if o.get("claimCombiner") == "unstated"]
    gaps.extend(
        Gap(o["id"], "unstated-claim-combiner",
            "the claim list this belongs to does not say whether its children are parts of one "
            "effect or alternative outcomes, so the check written above them proves this claim "
            "or refutes it and the book does not say which")
        for o in undetermined
    )
    undetermined_ids = {o["id"] for o in undetermined}
    owed = [o for o in owed if o["id"] not in undetermined_ids]
    # The same rule, reached from the other side. A claim is documented in a state, and an
    # obligation whose `fixture:` bullet the parser rejected does not say which state — so the
    # arrangement is undetermined and nothing executable comes out of it either. Partitioned
    # here rather than handled at each builder for the reason that matters: left in `owed`, one
    # of these reaches the journey builder, finds no arranged row and no `arrangesNothing`, and
    # is gapped `unarranged-journey` — which tells an author who wrote a `fixture:` bullet to
    # write one. A rejected bullet and an absent bullet are the same absent row downstream, and
    # the only place that can tell them apart is the packet, which now carries the rejection.
    unparsed = [o for o in owed if o.get("fixturesUnparsed")]
    gaps.extend(
        Gap(o["id"], "unparsed-fixture",
            "this claim's arrangement could not be read: "
            + "; ".join(f"`fixture: {row['value']}` is not a fixture reference — {row['problem']}"
                        for row in o["fixturesUnparsed"]))
        for o in unparsed
    )
    unparsed_ids = {o["id"] for o in unparsed}
    owed = [o for o in owed if o["id"] not in unparsed_ids]
    # And the third side of the same rule. An observation nobody could read is not an
    # observation, so there is nothing to emit; what is wrong without this partition is not the
    # missing code but the reason given for it — the obligation falls through to
    # `no-verify-declared`, "the book declares no check for this obligation to prove", at an
    # author who declared one and got the spelling wrong. `ostler doctor` refuses that bullet by
    # name, which is what makes the fall-through a disagreement in writing rather than a gap:
    # two readers of one bullet, and the one that decides whether to emit code held the wrong
    # account of it. The refusal's own sentence is quoted rather than re-derived here, for the
    # reason it was made a value in the first place.
    refused = [o for o in owed if o.get("checksUnparsed")]
    gaps.extend(
        Gap(o["id"], "unparsed-check-bullet",
            "this claim's check could not be read: "
            + "; ".join(f"`{row['value']}` {row['problem']}" for row in o["checksUnparsed"]))
        for o in refused
    )
    refused_ids = {o["id"] for o in refused}
    owed = [o for o in owed if o["id"] not in refused_ids]
    # And the fourth side, which deliberately does NOT partition. A `capture:` bullet the
    # parser rejected costs this obligation nothing — its own claim is still stated and still
    # checkable — so dropping it here would withhold code that is perfectly derivable. What is
    # lost is the *fact*: the name was never minted, and the obligation that pays is a later
    # one whose `$name` reference then reports `unresolved-precondition`, about a bullet its
    # author wrote correctly. So the gap is recorded against the bullet that is actually wrong,
    # and the obligation stays owed.
    uncaptured = [o for o in owed if o.get("capturesUnparsed")]
    gaps.extend(
        Gap(o["id"], "unparsed-capture-bullet",
            "this claim's capture could not be read, so it mints no fact for a later `$name` "
            "to resolve against: "
            + "; ".join(f"`capture: {row['value']}` {row['problem']}"
                        for row in o["capturesUnparsed"]))
        for o in uncaptured
    )
    # D1: the driver of a step is `(the obligation's own node type) x (owning surface's
    # runbook driver:)`, not (as this used to read) whether any declared check happens to observe
    # "page" — that bit is per-check, not per-node, and let two `does:` bullets on the same
    # node compile under two different drivers. Read `navigation` first: each obligation's
    # target is looked up per surface, keyed on the `driver` `_navigation` now stamps there.
    navigation = context.get("navigation", {}) if isinstance(context.get("navigation"), dict) else {}
    http_owed: list[dict[str, Any]] = []
    page_owed: list[dict[str, Any]] = []
    cli_owed: list[dict[str, Any]] = []
    flow_owed: list[dict[str, Any]] = []
    for obligation in owed:
        if not obligation.get("checksDeclared") and obligation.get("kind") != "states":
            # No claim to dispatch — falls through to the existing `no-verify-declared`
            # handling below, same as before D1's table existed, regardless of what node
            # type or driver it names. A `states:` obligation is the one exception: a check
            # is exactly what an unarranged state may be missing, and it still needs to reach
            # the page dispatch table below to be told apart from `no-verify-declared` debt
            # and gapped `unarranged-state` instead (see the by-node loop in
            # `_compile_page_scenarios`).
            http_owed.append(obligation)
            continue
        surface = str(obligation.get("surface") or "")
        driver = navigation.get(surface, {}).get("driver")
        node_type = str(obligation.get("nodeType") or "")
        if node_type == "flow":
            # A flow's own `start:`/`end:` is a claim about what its `steps:` did, and the
            # builders below compile one scenario per *place* — an arrival, one interaction, one
            # route — never one per journey. Handing an end-state to them addresses it at the
            # node it names and asserts it on arrival, with the steps that were supposed to
            # produce it never run: a check that passes in a world where the journey did not
            # happen. So flows are routed to their own builder, which walks the ordered `steps:`
            # the packet now carries and observes the claim where the walk actually left the
            # world (`_journey_scenarios`).
            flow_owed.append(obligation)
            continue
        target, detail = _dispatch_target(node_type, driver)
        if target == "playwright":
            page_owed.append(obligation)
        elif target == "http":
            http_owed.append(obligation)
        elif target == "cli":
            cli_owed.append(obligation)
        else:
            # `_dispatch_target` already told these two apart and the kind has to keep them
            # apart: a `None` target means the book left the step's dispatch undetermined —
            # something an author fixes — while a named target this compiler builds no path
            # for is a correct book waiting on a backend nobody has written.
            kind = "needs-target-backend" if target is not None else "uncompilable-claim"
            gaps.append(Gap(str(obligation["id"]), kind, detail))
    http_owed, api_urls = _split_by_entry_url(http_owed, navigation, base_url, gaps)
    page_owed, web_urls = _split_by_entry_url(page_owed, navigation, base_url, gaps)
    lines: list[str] = [
        "# Compiled from the book by `ostler qa compile-plan`. Every `covers=` below is the",
        "# obligation the book itself attributed the check to. Fill the TODO markers from the",
        "# story, the fixtures and the flows — not from the implementation, which is the thing",
        "# under test and cannot also be the specification it is tested against.",
        "",
        "from ostler_qa import Qa, plan, scenario, target",
        "",
        "",
        f"plan(run_id={_lit(run_id or f'qa-{story}')}, story={_lit(story)}, "
        f"book={_lit(book_digest(context))})",
    ]

    by_source: dict[str, list[dict[str, Any]]] = {}
    for obligation in http_owed:
        by_source.setdefault(str(obligation.get("source", "book")), []).append(obligation)

    # Every `target(...)` already assigned in this plan. A target is the pairing of a
    # driver with a service, so the same pairing is the same variable no matter which
    # builder reached it first — shared across the http, page and journey builders so
    # a journey over a surface that already has scenarios reuses its target rather
    # than assigning a second, identical one under the same name.
    emitted_targets: set[str] = set()
    # Every `(obligation id, capture name)` some builder has accounted for — emitted as a real
    # `qa.capture_field(...)` call, or declined with a gap saying why. Shared across the builders
    # the way `emitted_targets` is, because a declaration is stamped on the obligation and the
    # obligation reaches whichever builder its `(nodeType, surface)` dispatches to. The closing
    # assert reads it.
    captured: set[tuple[str, str]] = set()
    debt: list[dict[str, Any]] = []
    for source, obligations in by_source.items():
        declared = [o for o in obligations if o.get("checksDeclared")]
        undeclared = [o for o in obligations if not o.get("checksDeclared")]
        debt.extend(undeclared)
        # A scenario claiming an id its body never asserts is refused by `qa validate`, and
        # rightly: the claim would read as covered in every report while nothing observed it.
        # An obligation with no declared check is book debt, listed below rather than claimed —
        # and, so a caller reading `gaps` alone sees the whole owed set accounted for, gapped
        # here by the same code that declined to emit it, not left to a diff against `owed`.
        gaps.extend(
            Gap(o["id"], "no-verify-declared", "the book declares no check for this obligation to prove")
            for o in undeclared
        )
        if not declared:
            continue
        scenario_covered: set[str] = set()
        body_lines = _scenario_body(declared, gaps, scenario_covered, captured)
        if not scenario_covered:
            # Every declared obligation here turned out route-less — `_scenario_body` already
            # gapped each one as `uncompilable-claim` and emitted no `qa.verify` for any of
            # them. A scenario with nothing left to claim is not emitted with an empty
            # `covers=[]`; it is not emitted at all.
            continue
        covered_ids.update(scenario_covered)
        surface = str(obligations[0].get("surface") or "")
        target_var = _target_var(surface, "api")
        if target_var not in emitted_targets:
            lines.append("")
            lines.append(f"{target_var} = target({_lit(target_var)}, driver={_lit(PYTHON.name)}, "
                          f"base_url={_lit(api_urls.get(surface))})")
            emitted_targets.add(target_var)
        lines.append("")
        lines.append("")
        lines.append("@scenario(")
        lines.append(f"    target={target_var},")
        lines.append('    mechanism="live",')
        lines.append("    covers=[")
        lines.extend(f"        {_lit(o['id'])}," for o in declared if o["id"] in scenario_covered)
        lines.append("    ],")
        arranged = _arrangements(declared)
        if arranged:
            # The preconditions are the book's own words for the state each fixture leaves
            # behind. A scenario states what must hold before it runs, and the node that owns
            # the claim already said it — copying it here beats an author paraphrasing it.
            lines.append("    preconditions=[")
            lines.extend(f"        {_lit(row['provides'] or row['name'])},"
                         for row in arranged)
            lines.append("    ],")
        else:
            lines.append("    preconditions=[],  # TODO(arrange): what must hold before this scenario runs")
            gaps.extend(
                Gap(o["id"], "unresolved-precondition", "no fixture arranged for this obligation")
                for o in declared
            )
        lines.append("    checkpoints=[],  # TODO(arrange): what an observer should see it prove")
        lines.append("    forbid=[],  # TODO: the weaker observations this scenario must not settle for")
        lines.append(")")
        lines.append(f"def {_slug(source)}_from_the_book(qa: Qa) -> None:")
        lines.append(f'    """Obligations {source} owes live evidence for."""')
        if arranged:
            lines.append("")
            lines.extend(
                f"    qa.fixture({_lit(row['name'])}"
                + "".join(f", {_lit(arg)}" for arg in row.get("args", []))
                + ")"
                for row in arranged
            )
        lines.extend(body_lines)

    cli_declared = [o for o in cli_owed if o.get("checksDeclared")]
    cli_undeclared = [o for o in cli_owed if not o.get("checksDeclared")]
    debt.extend(cli_undeclared)
    gaps.extend(
        Gap(o["id"], "no-verify-declared", "the book declares no check for this obligation to prove")
        for o in cli_undeclared
    )
    _gap_cli_obligations(cli_declared, gaps)

    # A `states:` obligation is not withheld by the same rule as every other page claim: a
    # state with neither a check nor a fixture is not book debt, it is an unarranged
    # arrangement — the by-node loop below tells the two apart and gaps accordingly
    # (`unarranged-state`), so every `states:`-kind obligation reaches it regardless of
    # whether it declares a check.
    page_declared = [
        o for o in page_owed if o.get("checksDeclared") or o.get("kind") == "states"
    ]
    page_undeclared = [
        o for o in page_owed if not o.get("checksDeclared") and o.get("kind") != "states"
    ]
    debt.extend(page_undeclared)
    gaps.extend(
        Gap(o["id"], "no-verify-declared", "the book declares no check for this obligation to prove")
        for o in page_undeclared
    )
    if page_declared:
        if _has_screens(navigation):
            lines.extend(
                _compile_page_scenarios(context, page_declared, gaps, covered_ids, web_urls,
                                        emitted_targets, captured))
        else:
            # The book declares page checks but its navigation graph has no screen nodes on any
            # surface — there is nothing here to walk to, the same dead end `unreachable-screen`
            # names for a single node, just found before a walk ever starts rather than mid-hop.
            gaps.extend(
                Gap(o["id"], "unreachable-screen",
                    "the book's navigation graph has no screen nodes on any surface to walk to")
                for o in page_declared
            )

    # Journeys last: a flow's scenario names the same `target(...)` its steps' own surfaces
    # already assigned, and reading that off `emitted_targets` rather than re-assigning it is
    # only correct once every place-scoped builder above has run.
    lines.extend(_journey_scenarios(context, flow_owed, gaps, covered_ids, navigation,
                                    web_urls, api_urls, emitted_targets, captured))

    if debt:
        lines.append("")
        lines.append("")
        lines.append("# Book debt. Each of these is owed live evidence by this change and declares no")
        lines.append("# `verify:`, so there is nothing to compile and nothing an author could copy. The")
        lines.append("# fix is a check on the bullet in the book, not an assertion invented down here.")
        for obligation in debt:
            requirement = " ".join(str(obligation.get("requirement", "")).split())
            lines.append(f"#   {obligation['id']}")
            lines.append(f"#     {requirement[:100]}")

    known_ids = {str(o.get("id")) for o in context.get("obligations", [])}
    for gap in gaps:
        assert gap.obligation_id in known_ids, (
            f"compiled a {gap.kind!r} gap keyed by {gap.obligation_id!r}, which is not a known "
            "obligation id — every Gap must be filterable by the live-audit's "
            "`covers` intersection, which only ever holds real obligation ids"
        )

    # Totality: every obligation this compiler owes evidence for either got a real `covers=[...]`
    # claim compiled for it, or carries a gap explaining why not — minted by the code that
    # declined, above, not reconstructed here by diffing `owed` against what happened to come
    # out. An id in neither bucket is a silent drop, the defect this loop exists to make
    # impossible.
    gapped_ids = {gap.obligation_id for gap in gaps}
    dropped = {str(o["id"]) for o in owed} - gapped_ids - covered_ids
    assert not dropped, (
        f"{len(dropped)} owed obligation(s) landed in neither `gaps` nor a compiled scenario: "
        f"{sorted(dropped)!r}"
    )
    # The mirror: an obligation reported as unobserved and also claimed by a scenario is the
    # same silent drop seen from the other side — the report says nobody looked and the plan
    # says somebody did, and whichever a reader consults first is the one they believe. Read
    # over the gaps that are claims about the observation; an arrangement gap
    # (`kind` in `_ARRANGEMENT_GAPS`, see `Gap`) stacks on the same id on purpose and is not one.
    unobserved = {gap.obligation_id for gap in gaps if gap.kind not in _ARRANGEMENT_GAPS}
    # Declaration totality, the mirror of the obligation totality above. A `capture:` bullet is
    # a thing the book said, and until this assert existed exactly one builder read it: an
    # interaction's capture parsed, grounded, rode into the packet and was dropped by a builder
    # that never looked — no emitted call, no gap, nothing distinguishing it from a bullet
    # nobody wrote. A capture on an obligation nobody observed at all goes with its obligation:
    # the gap already says nothing here was looked at, and a second one would report the same
    # silence twice.
    unaccounted = _declared_captures(owed) - captured
    unaccounted -= {pair for pair in unaccounted if pair[0] in unobserved}
    assert not unaccounted, (
        f"{len(unaccounted)} declared capture(s) were neither emitted nor gapped by the builder "
        f"that declined them: {sorted(unaccounted)!r}"
    )
    contradicted = unobserved & covered_ids
    assert not contradicted, (
        f"{len(contradicted)} obligation(s) are both gapped as unobserved and claimed by a "
        f"compiled scenario: {sorted(contradicted)!r}"
    )

    return "\n".join(lines).rstrip() + "\n", gaps


def deferred_obligations(context: dict[str, Any], *, story: str) -> dict[str, Gap]:
    """Which owed obligations the reference compiler gapped without also covering.

    An obligation gapped by an arrangement-kind gap (`_ARRANGEMENT_GAPS`) but still
    covered by a real `covers=[...]` claim compiled elsewhere — the `open-new-widget`
    shape, where the gap is a caveat standing beside a compiled assertion, not a reason
    nothing was compiled — is not deferred: a real plan can be held to the same standard
    the reference compiler met. Anything else gapped, arrangement-kind or not, is an
    obligation this compiler itself produced no evidence for; requiring a real plan to
    cover what the reference compiler could not is what sent planners after routes and
    preconditions that do not exist.
    """
    covered: set[str] = set()
    _source, gaps = compile_plan_gaps(context, story=story, covered_ids=covered)
    deferred: dict[str, Gap] = {}
    for gap in gaps:
        if gap.obligation_id in covered:
            continue
        deferred.setdefault(gap.obligation_id, gap)
    return deferred


def annotate_deferred_obligations(context: dict[str, Any], *, story: str) -> dict[str, Any]:
    """Stamp each obligation `deferred_obligations` names, in place, with why.

    Written by the producer (`ostler qa context`) so the consumer (`validate_v2`) can
    read a `deferred` field off the obligation instead of re-deriving "unhandled" from a
    bare set difference against asserted coverage — the difference that, before this,
    refused a valid, compiled, sound plan wholesale because it could not tell a genuinely
    unhandled obligation from one the reference compiler had already explained.
    """
    deferred = deferred_obligations(context, story=story)
    for obligation in context.get("obligations", []):
        gap = deferred.get(str(obligation.get("id")))
        if gap is not None:
            obligation["deferred"] = {"kind": gap.kind, "detail": gap.detail}
    return context


def _arrangements(obligations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every fixture the obligations in one scenario declare, in order, arranged once each.

    Deduped on name *and* arguments: two claims documented in the same seeded ledger name one
    arrangement, and running it twice would be a second ledger rather than the one they share.
    Two that differ in an argument are two states, and both are arranged.
    """
    rows: list[dict[str, Any]] = []
    for obligation in obligations:
        rows.extend(obligation.get("fixturesDeclared", []))
    return list({(row["name"], tuple(row.get("args", []))): row for row in rows}.values())


def _resolved(
    ref: references.Reference,
    produced_facts: set[tuple[str, str]],
    produced_captures: set[str],
) -> bool:
    """Whether *ref* names a fact some earlier producer in the scenario already left behind.

    `@node.key` resolves against `produced_facts`, which by the time this obligation's own
    references are checked already carries this obligation's own arranged fixtures — arranging
    happens before verifying on the same node, so a fixture that node itself arranges resolves
    its own references. `$name` resolves against `produced_captures`, which does *not* yet carry
    this obligation's own captures: a capture is the thing an action just produced, not a fact in
    hand before that action ran, so a reference on the same obligation that captures it is still
    a gap — only a *strictly earlier* obligation's capture resolves it.
    """
    if isinstance(ref, references.NodeRef):
        return (ref.node, ref.key) in produced_facts
    return ref.name in produced_captures


def _scenario_body(obligations: list[dict[str, Any]], gaps: list[Gap], covered: set[str],
                   captured: set[tuple[str, str]]) -> list[str]:
    """Compile every obligation's assertion half. Called only with `checksDeclared` obligations.

    `compile_plan` filters to `declared = [o for o in obligations if o.get("checksDeclared")]`
    before ever reaching here, so every obligation this sees already has at least one row —
    there is no "declares no `verify:`" case left to report from inside the loop.

    References are resolved statically against a running producer set built by walking these
    obligations in the book's own document order: a `@node.key`/`$name` the book has not yet
    produced by this point is a gap, one it has is not — see `_resolved`.

    `obligations` arrives sorted by `_sort_key` (alphabetical on id, for stable ids and display),
    which is not the book's document order — a node written `returns:` (capturing a value) then
    `raises:` (reading it) sorts as `raises` before `returns`. The walk here re-sorts by each
    obligation's stamped `docPosition`, a `[node line, bullet ordinal]` pair, so the producer set
    fills in the order the author actually wrote the bullets — across the several nodes one
    scenario can owe evidence for, not just within one — rather than the order their key names
    happen to alphabetize to.
    """
    lines: list[str] = []
    index = 0
    produced_facts: set[tuple[str, str]] = set()
    produced_captures: set[str] = set()
    for obligation in sorted(obligations, key=lambda o: tuple(o.get("docPosition") or (0, 0))):
        oid = obligation["id"]
        rows = obligation.get("checksDeclared", [])
        requirement = " ".join(str(obligation.get("requirement", "")).split())
        lines.append("")
        lines.append(f"    # {oid}")
        lines.append(f"    # {requirement}")

        for fixture_row in obligation.get("fixturesDeclared", []):
            for qualified in fixture_row.get("providesKeys", []):
                owner, sep, key = qualified.rpartition(".")
                if sep:
                    produced_facts.add((owner, key))

        route = _route(obligation)
        index += 1
        name = f"observed_{index}"
        action_emitted = False
        if route is not None:
            method, template = route
            path = _concrete_path(rows) or template
            status = _expect_status(rows)
            path_refs = references.find_references(path)
            for ref in path_refs:
                if not _resolved(ref, produced_facts, produced_captures):
                    gaps.append(Gap(oid, "unresolved-precondition",
                                     f"the path references {ref!r}, not resolvable without running the plan"))
            body = "" if method in {"GET", "DELETE", "HEAD", "OPTIONS"} else ", json_body={}"
            if body != "":
                # A request the compiler cannot construct is not a weaker version of the real
                # one — `json_body={}` against an endpoint that requires a body gets refused
                # by the app (422), and that refusal would land in the ledger as a behavioural
                # failure against code that did nothing wrong. Unlike an unresolved path
                # reference or template variable (left as an executed call with a caveat,
                # `_ARRANGEMENT_GAPS`), there is no partial request to send, so the call is
                # withheld entirely — the same "undetermined precondition, no executable code"
                # rule `on_resolved` already applies to a UI trigger it cannot resolve.
                lines.append("    # TODO(arrange): the book carries no request body")
                lines.append(f"    {name} = None  # TODO(arrange): what this scenario observes")
                gaps.append(Gap(oid, "unarranged-request-body", "the book carries no request body"))
            else:
                # A route path is almost never a whole reference —
                # `/orgs/@seeded-acme.id/projects` embeds one mid-string. `Http` takes plain
                # literals now (Fix 2), so a path that found a reference is wrapped in the
                # harness's one explicit substitution call; every other path is left a bare
                # literal `Http` never touches for resolution.
                path_expr = f"qa.resolve({_lit(path)})" if path_refs else _lit(path)
                expect = f", expect_status={status}" if status is not None else ""
                lines.append(f"    {name} = qa.http.{method.lower()}({path_expr}{expect})")
                action_emitted = True
                if "{" in path:
                    lines.append("    # TODO(arrange): the path above still carries a template variable")
                    gaps.append(Gap(oid, "unresolved-precondition", "the path still carries a template variable"))
        else:
            lines.append("    # TODO(arrange): the book gives this node no `route:` to act on")
            lines.append(f"    {name} = None  # TODO(arrange): what this scenario observes")
            gaps.append(Gap(oid, "uncompilable-claim", "the book gives this node no `route:` to act on"))

        for capture in obligation.get("capturesDeclared", []):
            cname = capture.get("name")
            source_path = str(capture.get("from", ""))
            if not cname:
                continue
            if source_path.startswith("$") and action_emitted:
                # A `$.`-rooted capture reads out of the response this obligation just bound —
                # emitting the call here, not just crediting `produced_captures`, is the fix:
                # a credit with nothing behind it at runtime means `$name` resolves against a
                # fact that was never captured. Emitted right after `observed_N` is bound, so
                # a strictly later obligation's `qa.resolve($name)` finds it already run. When
                # this obligation has no route, `observed_N` is `None` and there is nothing to
                # read `.json()` off of — that case falls through to the gap branch below, the
                # same as a UI-locator capture, rather than crediting a call that never runs.
                lines.append(
                    f'    qa.capture_field({_lit(cname)}, {name}.json(), {_lit(str(_rooted(source_path)))})'
                )
                produced_captures.add(cname)
                captured.add((oid, cname))
            else:
                # A UI-locator capture has no response here to read — the book says what to
                # capture and not where the page action that would produce it lives. A `$.`-
                # rooted capture with no route is the same shape: nothing was observed to read
                # a field off of. Both get the same scaffolding as an arrangement gap: a TODO
                # and a gap, no credit.
                because = ("names a UI locator, not a response field, and this builder holds a "
                           "response")
                if source_path.startswith("$"):
                    because = "has no observed response here to read the field off of"
                lines.append(
                    f"    # TODO(arrange): capture {cname!r} from {source_path!r} {because}")
                _decline_captures([obligation], gaps, captured, because=because)

        # A gap already fired above for a route-less obligation, or one whose request body the
        # book never wrote — `name` is bound to `None` in both cases, and a `qa.verify` call
        # built from it would read as a real assertion, one that crashes the moment anyone runs
        # the plan. The gap already minted is the whole story; nothing here would add to it,
        # only stand a broken call up alongside it.
        if not action_emitted:
            continue

        # An obligation's `verify:` bullets are a conjunction: they all describe the same claim,
        # so observing some of them is not observing it. A row this compiler cannot observe
        # therefore withdraws the whole obligation rather than the one bullet — otherwise the
        # plan claims the id on the strength of the half that compiled and the gap report says
        # nobody looked, which is the same claim contradicted twice. Every row is walked first,
        # so the gaps are complete, and only then is the obligation emitted or withdrawn.
        assertions: list[str] = []
        whole = True
        for row in rows:
            for ref in references.find_references(json.dumps(row.get("args", {}))):
                if not _resolved(ref, produced_facts, produced_captures):
                    gaps.append(Gap(oid, "unresolved-precondition",
                                     f"a verify argument references {ref!r}, not resolvable without running the plan"))
            operand, note, kind = _operand(row["name"], name)
            if note:
                lines.append(f"    # TODO(arrange): {note}")
                gaps.append(Gap(oid, kind, note))
                whole = False
                continue
            assertions.append(
                f"    qa.verify({_lit(row['name'])}, {operand}{_kwargs(row.get('args', {}))}, covers=[{_lit(oid)}])"
            )
        if whole:
            lines.extend(assertions)
            covered.add(oid)
    return lines


def _operand(check: str, observed: str) -> tuple[str, str, str]:
    """What the compiled call is handed, the arrangement note it still needs, and why.

    The third element is the `Gap.kind` the note becomes — empty when there is no note,
    because the check compiled for real. `page` cannot reach here (D1's dispatch table
    routes any `interaction`-node obligation on a `web`-driven surface to
    `_compile_page_scenarios` instead), and an unknown check has already been refused by
    `checks.parse_check` before compile.py ever sees it — neither needs a branch for a case
    this function is never actually called with.

    Every branch below reads `CheckSpec.observes`/`.out_of_band` off the check it was
    handed — no check name is compared here, because shape and channel are declared on
    the spec, not on this function.
    """
    observes = _observes(check)
    if observes == "response":
        return observed, "", ""
    if observes == "body":
        return f"{observed}.json()", "", ""
    if _out_of_band(check):
        return (
            observed,
            f"`{check}` observes a subject read through a channel this compiler has no "
            "handle on — arrange it out of band",
            "needs-out-of-band-observation",
        )
    if observes == "subject":
        # Read once, after the action, from what the scenario already holds — no
        # arrangement this compiler cannot already make.
        return observed, "", ""
    # The remaining `subject-pair` checks want a before-and-after this compiler has no
    # snapshot mechanism to take.
    return (
        observed,
        f"`{check}` observes a subject before and after the action — hand it the pair",
        "needs-snapshot",
    )


def _compile_page_scenarios(
    context: dict[str, Any],
    page_declared: list[dict[str, Any]],
    gaps: list[Gap],
    covered: set[str],
    web_urls: dict[str, str],
    emitted_targets: set[str],
    captured: set[tuple[str, str]],
) -> list[str]:
    """Compile every screen's `visible(...)` bullets, partitioned per Amendment 3.

    One screen is not one scenario. Its page-checked obligations are grouped by the node that
    owns each `verify:` row (a `### <component>` or a `## Interactions` entry), then split:

    - a component with neither `states:` nor `exclusive-with:` joins the screen's one *arrival*
      scenario — the navigation hop list from `context["navigation"][surface]["routes"][screen]`
      compiled into one click per hop (Correction 2'), ending on the screen's own assertions;
    - a component carrying `exclusive-with:` gets its own scenario (still an arrival scenario,
      just not sharing with anything else on the screen — see the module docstring below for why
      this is looser than a full symmetric partition);
    - a component carrying `states:` compiles to nothing — a `states:`-scoped arrangement is not
      the plain "screen just loaded" state the arrival route puts the page in, and inventing one
      would be arranging behind the book's back, so it is an `unresolved-precondition` gap
      instead, quoting the `states:` text verbatim;
    - a `## Interactions` entry (identified by carrying `on:`) reuses the arrival hops, then
      performs a best-effort click on the `on:` component before asserting — see
      `_interaction_scenario` for what "best-effort" means here and why it is always also gapped;
    - a `visible(...)` row with no owning `### <component>` (a screen-level node id, no `#`, and
      no `role`/`name`/`selector` of its own) has no addressable subject at all: `uncompilable-claim`.

    A component carrying *both* `states:` and `exclusive-with:` (real in this fixture —
    `vehicle-vin-field`/`property-address-field` in `new-policy.md`) is treated as `states:`
    first: `states:` blocks compiling any scenario outright, which is the stronger claim, so it
    wins over `exclusive-with:`'s weaker "just don't share a scenario". The ruling set lists the
    two as if they were mutually exclusive categories; this fixture shows they are not, and this
    is the explicit precedence decision for that case.

    `exclusive-with:` is read as symmetric *for whether a pair may ever end up sharing a
    scenario* (never), but this compiler does not compute the full symmetric closure across a
    screen's components to decide who else must therefore be isolated: every `exclusive-with:`-
    carrying component gets its own scenario, singleton, on its own — a strictly stronger
    guarantee than "not sharing with its named partner", so the "never share" requirement holds
    either way a screen writes the bullet (on one side only, or on both).
    """
    scenario_lines_by_surface: dict[str, list[str]] = {}
    node_index = _node_locator_index(context)
    screen_routes = _screen_routes(context)
    by_screen: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for obligation in page_declared:
        key = (str(obligation.get("surface", "")), str(obligation.get("source", "")))
        by_screen.setdefault(key, []).append(obligation)

    navigation = context.get("navigation", {}) if isinstance(context.get("navigation"), dict) else {}
    for (surface, source), group in sorted(by_screen.items()):
        ids = sorted(o["id"] for o in group)
        nav = navigation.get(surface) if surface else None
        if nav is None:
            # Amendment 1: one gap per obligation the group actually owes, not one per screen —
            # a single representative id only defeats the live-audit's `covers` intersection by
            # accident (it needs just one match), and would silently stop working the moment a
            # screen's obligations split across more than one scenario.
            gaps.extend(Gap(oid, "uncompilable-claim",
                             f"surface {surface!r} has no `navigation` data to address this screen by")
                        for oid in ids)
            continue
        if source in set(nav.get("unreachable", [])):
            # Correction 5': an unreachable screen is a finding, not a compile target. Reusing
            # the doctor-recognized `unreachable-screen` code (the same one `doctor.py`'s own
            # `reach`-based check already mints) rather than collapsing it into
            # `uncompilable-claim` — a screen with no route in and a screen with no addressable
            # subject are different defects and should not read as the same finding.
            gaps.extend(Gap(oid, "unreachable-screen",
                             f"{surface}'s navigation cannot reach this screen; no scenario compiled")
                        for oid in ids)
            continue
        hops = nav.get("routes", {}).get(source)
        if hops is None:
            gaps.extend(Gap(oid, "uncompilable-claim", "no route computed for this screen")
                        for oid in ids)
            continue
        root_path = str(nav.get("rootPath") or "/")
        if source in set(nav.get("undeclared", [])):
            # Amendment 2: reachable, but the screen's `requires:`/`params:` bullets are
            # literally absent — not "none", absent. One gap per screen (kept as designed,
            # exception to Amendment 1's per-obligation rule): every `visible(...)` bullet on
            # the screen shares the identical undeclared-precondition fact, and multiplying it
            # by obligation count would not add information. It still needs a real obligation
            # id, though — the first (sorted) obligation on this screen stands in for the
            # screen-level fact, rather than the screen's own source path.
            gaps.append(Gap(ids[0], "screen-preconditions-undeclared",
                             "reachable, but this screen declares no `requires:`/`params:` bullets"))

        by_node: dict[str, list[dict[str, Any]]] = {}
        for obligation in group:
            by_node.setdefault(str(obligation["node"]), []).append(obligation)

        target_var = _target_var(surface, "web")
        bucket = scenario_lines_by_surface.setdefault(surface, [])

        plain: dict[str, list[dict[str, Any]]] = {}
        exclusive: list[str] = []
        interactions: list[str] = []
        rest_by_node: dict[str, list[dict[str, Any]]] = {}
        for node_id, obs in sorted(by_node.items()):
            # A `states:` bullet mints its own obligation (`kind == "states"`) but its locators
            # ride every sibling obligation on the same node (`BulletKey("states", ...,
            # locator=True)`, registry.py) — the node-wide `locators.get("states")` this loop
            # used to key on is therefore true for a node's `role:`/`name:` claim too, and wrongly
            # withheld it alongside the state. Route each obligation by its own `kind` instead: a
            # state obligation either compiles into its own dedicated scenario (both a check and a
            # fixture arranged for it) or is gapped `unarranged-state` on its own id, and never
            # gates its non-state siblings.
            state_obs = [o for o in obs if o.get("kind") == "states"]
            rest = [o for o in obs if o.get("kind") != "states"]
            for obligation in state_obs:
                state_text = " ".join(str(obligation.get("requirement", "")).split())
                arranged = _arrangements([obligation])
                if obligation.get("checksDeclared") and arranged:
                    state_name = f"{_slug(source)}_{_node_slug(node_id)}_{obligation['id'].rsplit(':', 1)[-1]}"
                    bucket.extend(_arrival_scenario(root_path, source, hops, node_index,
                                                     {node_id: [obligation]}, gaps, covered,
                                                     captured, name=state_name, target_var=target_var,
                                                     screen_routes=screen_routes))
                else:
                    missing = []
                    if not obligation.get("checksDeclared"):
                        missing.append("no check declared")
                    if not arranged:
                        missing.append("no fixture arranged")
                    gaps.append(Gap(obligation["id"], "unarranged-state",
                                     f"carries `states:` ({state_text!r}); "
                                     + " and ".join(missing)))
            if not rest:
                continue
            rest_by_node[node_id] = rest
            locators = rest[0].get("locators", {})
            node_ids = sorted(o["id"] for o in rest)
            if locators.get("on"):
                interactions.append(node_id)
            elif not _page_locator_expr(locators):
                gaps.extend(Gap(oid, "uncompilable-claim",
                                 "no addressable `### <component>` owns this `visible(...)` claim")
                            for oid in node_ids)
            elif locators.get("exclusiveWith"):
                exclusive.append(node_id)
            else:
                plain[node_id] = rest

        if plain:
            bucket.extend(_arrival_scenario(root_path, source, hops, node_index, plain, gaps,
                                             covered, captured,
                                             name=f"{_slug(source)}_arrival",
                                             target_var=target_var,
                                             screen_routes=screen_routes))
        for node_id in exclusive:
            bucket.extend(_arrival_scenario(root_path, source, hops, node_index,
                                             {node_id: rest_by_node[node_id]}, gaps, covered,
                                             captured,
                                             name=f"{_slug(source)}_{_node_slug(node_id)}",
                                             target_var=target_var,
                                             screen_routes=screen_routes))
        for node_id in interactions:
            bucket.extend(_interaction_scenario(root_path, source, hops, node_index, node_id,
                                                 rest_by_node[node_id], gaps, covered, captured,
                                                 name=f"{_slug(source)}_{_node_slug(node_id)}",
                                                 target_var=target_var,
                                                 screen_routes=screen_routes))

    lines: list[str] = []
    for surface in sorted(scenario_lines_by_surface):
        scenario_lines = scenario_lines_by_surface[surface]
        if not scenario_lines:
            # Minor correction: a `web` target with nothing compiled under it is an unused
            # fixture in the plan — emit it only when at least one scenario actually landed.
            continue
        target_var = _target_var(surface, "web")
        if target_var in emitted_targets:
            lines.extend(scenario_lines)
            continue
        web_target = (f'{target_var} = target({_lit(target_var)}, driver={_lit(PLAYWRIGHT.name)}, '
                      f'base_url={_lit(web_urls.get(surface))})')
        emitted_targets.add(target_var)
        lines.extend(["", "", web_target, *scenario_lines])
    return lines


def _node_slug(node_id: str) -> str:
    fragment = node_id.rsplit("#", 1)[-1]
    return _slug(fragment)


def _walk_hops(
    hops: list[dict[str, Any]],
    node_index: dict[str, dict[str, list[str]]],
    gaps: list[Gap],
    oids: list[str],
) -> list[str]:
    """One `.click()` per hop the book's own navigation-derivation logic found (Correction 2').

    A failed hop gaps every obligation the scenario covers (Amendment 1), not one representative
    id — every one of them is blocked by the same missing hop locator, and the live-audit's
    `covers` filter has to be able to find each of them there.
    """
    lines: list[str] = []
    for hop in hops:
        target_node = str(hop.get("node", ""))
        expr = _page_locator_expr(node_index.get(target_node, {}))
        if expr is None:
            lines.append(f"    # TODO(arrange): no locator declared for {target_node!r}"
                         f" ({hop.get('label', '')!r})")
            gaps.extend(Gap(oid, "unresolved-precondition",
                             f"no locator declared for navigation hop {target_node!r}")
                        for oid in oids)
            continue
        lines.append(f"    {expr}.click()  # {_trailing_comment(str(hop.get('label', '')))}")
    return lines


def _assertion_operand(locators: dict[str, list[str]], oid: str, gaps: list[Gap]) -> str | None:
    """The concrete operand a `visible(...)` assertion is handed — never a page/body fallback.

    Finding 1: an obligation with no addressable subject of its own is not "close enough" to
    `qa.page.locator('body')` — that locator is always visible, so the assertion it is handed to
    would pass no matter what the app renders. `None` here means the same thing it means to
    `_page_locator_expr`'s other callers: this obligation becomes an `uncompilable-claim` gap,
    not a scenario line that only looks like a check.
    """
    expr = _page_locator_expr(locators)
    if expr is None:
        gaps.append(Gap(oid, "uncompilable-claim",
                         "no addressable role/name or selector locator for this obligation's "
                         "`visible(...)` assertion"))
        return None
    return expr


def _check_operand(
    row: dict[str, Any], obligation: dict[str, Any], gaps: list[Gap]
) -> str | None:
    """Where the driver is pointed for one `verify:` row.

    A check that names its own subject — `visible(locator="#name-error")` — is about *that*
    component, which is not in general the node the obligation was minted on: a refusal claim
    on a form is observed by an error span declared beside it. The packet already resolved the
    reference (`qa context`'s `locates`), so this reads the answer rather than re-deriving it;
    a check that names no subject falls back to the node's own locators, which is what every
    check did before the argument existed.
    """
    located = row.get("locates") or {}
    if not located:
        return _assertion_operand(obligation.get("locators", {}), obligation["id"], gaps)
    param = sorted(located)[0]
    target = located[param]
    node_id = str(target.get("node", ""))
    if not node_id:
        gaps.append(Gap(
            obligation["id"], "undeclared-check-locator",
            f"`{row.get('name')}` points `{param}=` at "
            f"`{row.get('args', {}).get(param)}`, which names no component or interaction this "
            f"book declares — there is nothing to point a driver at, so nothing is emitted"))
        return None
    expr = _page_locator_expr(target.get("locators", {}))
    if expr is None:
        gaps.append(Gap(
            obligation["id"], "uncompilable-claim",
            f"`{node_id}` is what `{param}=` names, and it declares no role/name pair and no "
            f"selector — so the book says what to look at and not how to address it"))
        return None
    return expr


def _check_document(row: dict[str, Any], obligation: dict[str, Any]) -> str:
    """The screen document a check observes — the one its `locator=` names, or its own.

    What a `qa.vet` registers is a photograph against the placement the book records, so the
    document has to be the one the assertion is looking at. A refusal claim authored on the
    form and observed through a table on the next screen is evidence about *that* screen, and
    vetting the screen the claim was written on would file the picture under the wrong book.
    """
    for param in sorted(row.get("locates") or {}):
        node_id = str((row["locates"][param] or {}).get("node", ""))
        if node_id:
            return node_id.split("#", 1)[0]
    return str(obligation.get("source", ""))


def _vettable(
    documents: list[str],
    screen_routes: dict[str, str],
    ids: list[str],
    gaps: list[Gap],
) -> list[str]:
    """*documents* a vet can establish as its subject, with a gap for each one it cannot.

    A `qa.vet` files every placement verdict it produces under the screen it was told to
    grade, and the only thing a reader of a rendered page has to go on to say which screen it
    is looking at is that screen's `route:`. Where the route names a family of pages, or is not
    a path at all — a framework's route *name*, a sentence — or the book states none for the
    file, or states two, there is no comparison to make, the driver
    grades whatever it was handed and reports `arrival: "unstated"`, and a verdict about a
    correspondence nobody established is a pass that means nothing.

    So the call is withheld rather than emitted with a caveat attached to its output. A
    scenario that cannot say which screen it ended on is a plan defect, and the plan is where
    it gets said — `ostler doctor` reads these gaps, and a note buried in a run's evidence
    reaches nobody deciding whether the book is compilable.
    """
    keep: list[str] = []
    for document in documents:
        route = screen_routes.get(document, "")
        if literal_route(route):
            keep.append(document)
            continue
        why = why_unreadable(route)
        gaps.extend(Gap(oid, "unidentifiable-screen",
                        f"this scenario ends on {document}, and {why} — so nothing can say the "
                        "page it photographed is that screen, and its placement verdicts are "
                        "withheld rather than reported about an unestablished subject")
                    for oid in ids)
    return keep


#: The variable a page scenario binds its observation window to, immediately before the action
#: it is making a claim about. Emitted only when some row in the scenario actually reads an
#: exchange — an unused binding in every other scenario would be noise in a file people read.
_WINDOW_VAR = "exchanges"


def _observed_exchange(obligation: dict[str, Any]) -> str | None:
    """Which HTTP exchange this obligation's response/body checks are about, if the book says.

    A browser makes many requests. `qa.http`'s scenarios have one response because the
    scenario made one call; a page scenario has however many the page chose to make, so the
    operand of an HTTP claim is a *selection* and something has to have written the selector
    down. Exactly one check in the vocabulary carries one: `http_status(path=…)`, whose
    `path=` is a URL route. `json_path(path=…)` is a *JSON* path and `omits(subject=…)` a
    field path — neither names an exchange, and reading them as one would point the driver at
    a request nobody mentioned.

    So the selector is read once per obligation and shared by its rows: an obligation is one
    claim, and a claim that says "answered 201 on `/api/widgets`, and the body carried the
    new id" is talking about one exchange throughout. An obligation whose rows name two
    different routes is not one exchange, and returns `None` — which is undetermined, not a
    default, so nothing executable is emitted for it.
    """
    routes = {
        str(row["args"]["path"])
        for row in obligation.get("checksDeclared", [])
        if row.get("name") == "http_status" and isinstance(row.get("args"), dict)
        and isinstance(row["args"].get("path"), str)
    }
    return next(iter(routes)) if len(routes) == 1 else None


def _exchange_operand(
    row: dict[str, Any], obligation: dict[str, Any], exchange: str | None,
    channel: str, gaps: list[Gap],
) -> str | None:
    """Where a page scenario is pointed for one response- or body-observing `verify:` row.

    The Playwright driver can see a response (`DriverSpec.observes`), and the harness has
    recorded every one of them since `_on_response` was added. What was missing was the
    arrangement: a selector for *which* one, and a window saying *since when*. Both are
    supplied here — the selector from the book (`_observed_exchange`), the window from
    `_WINDOW_VAR`, which the scenario binds immediately before its action.

    `channel` decides what the verifier is handed, because the two channels want different
    things from the same exchange: a `"response"` check reads the status line and the URL, a
    `"body"` check resolves a path inside the parsed payload.
    """
    if exchange is None:
        gaps.append(Gap(
            obligation["id"], "uncompilable-claim",
            f"`{row.get('name')}` observes an HTTP {channel}, which the playwright driver "
            "can see — but a browser makes many requests and nothing in this obligation "
            "says which one. Declare the exchange with an `http_status(path=\"…\")` bullet "
            "on the same claim; two different `path=` routes on one obligation are two "
            "claims, not one"))
        return None
    selection = f"{_WINDOW_VAR}.response_for({_lit(exchange)})"
    return f"{selection}.json()" if channel == "body" else selection


def _needs_window(lines: list[str]) -> bool:
    """Whether any emitted assertion reads the observation window, so it has to be opened."""
    return any(f"{_WINDOW_VAR}." in line for line in lines)


def _page_assertions(
    obligation: dict[str, Any], gaps: list[Gap]
) -> tuple[list[str], list[str]] | None:
    """One obligation's assertions and the screens they observe, or `None` if it is not whole.

    An obligation's `verify:` bullets are a conjunction: they all describe the same claim, so
    observing some of them is not observing it. A claim whose refusal is visible on the screen
    *and* answered by a 400 is not discharged by the span alone — a scenario that reported the
    span and skipped the status would file a green against an app that renders the error and
    returns 201. F16 admits three states, and "partly" is not one of them, so an obligation
    with any uncompilable row is claimed by nobody and stands as its gap.
    """
    lines: list[str] = []
    documents: list[str] = []
    whole = True
    exchange = _observed_exchange(obligation)
    for row in obligation.get("checksDeclared", []):
        channel = _observes(row.get("name"))
        if channel in {"response", "body"} and not _out_of_band(row.get("name")):
            operand = _exchange_operand(row, obligation, exchange, channel, gaps)
            if operand is None:
                whole = False
                continue
            lines.append(
                f"    qa.verify({_lit(row['name'])}, {operand}"
                f"{_kwargs(row.get('args', {}))}, "
                f"covers=[{_lit(obligation['id'])}])"
            )
            continue
        if channel != "page":
            gaps.append(_unobservable_gap(obligation["id"], row.get("name"), PLAYWRIGHT))
            whole = False
            continue
        # Per row, not per obligation: an interaction's claims are observed by whatever
        # component each check names — the refusal by an error span, the acceptance by the
        # table on the next screen — and the node's own locator is only the fallback for a
        # check that named nothing.
        operand = _check_operand(row, obligation, gaps)
        if operand is None:
            whole = False
            continue
        document = _check_document(row, obligation)
        if document and document not in documents:
            documents.append(document)
        lines.append(
            f"    qa.verify({_lit(row['name'])}, {operand}"
            f"{_kwargs(row.get('args', {}))}, "
            f"covers=[{_lit(obligation['id'])}])"
        )
    if not whole:
        return None
    return lines, documents


def _arrival_scenario(
    root_path: str,
    source: str,
    hops: list[dict[str, Any]],
    node_index: dict[str, dict[str, list[str]]],
    by_node: dict[str, list[dict[str, Any]]],
    gaps: list[Gap],
    covered: set[str],
    captured: set[tuple[str, str]],
    *,
    name: str,
    target_var: str,
    screen_routes: dict[str, str],
) -> list[str]:
    obligations = [o for obs in by_node.values() for o in obs]
    _decline_captures(obligations, gaps, captured, because=(
        "this scenario arrives at the screen and observes what is on it — nothing here performs "
        "an action that would produce a value to bind"))
    ids = sorted(o["id"] for o in obligations)
    arranged = _arrangements(obligations)
    body: list[str] = []
    if arranged:
        body.extend(
            f"    qa.fixture({_lit(row['name'])}"
            + "".join(f", {_lit(arg)}" for arg in row.get("args", []))
            + ")"
            for row in arranged
        )
    goto_index = len(body)
    body.append(f"    qa.goto({_lit(root_path)})")
    body.extend(_walk_hops(hops, node_index, gaps, ids))
    # Presence is what a role locator proves and placement is what it cannot, so a scenario
    # that renders a documented screen photographs it and hands ostler the screen it is
    # supposed to be. Arrival reaches exactly one documented state: the one it arrived at.
    body.extend(
        f"    qa.vet({_lit(document)})"
        for document in _vettable([source], screen_routes, ids, gaps)
    )
    assertions: list[str] = []
    scenario_covered: set[str] = set()
    for _node_id, obs in sorted(by_node.items()):
        for obligation in obs:
            compiled = _page_assertions(obligation, gaps)
            if compiled is None:
                assertions.append(f"    # TODO(arrange): {obligation['id']} declares an "
                                   "observation this scenario cannot make")
                continue
            assertions.extend(compiled[0])
            scenario_covered.add(str(obligation["id"]))
    if not scenario_covered:
        # Every obligation this arrival would have claimed was gapped above — no addressable
        # subject, or a check this driver cannot observe. A scenario that drives a UI and vets
        # no screen is a hole in the plan wearing a function signature, so nothing is emitted.
        return []
    if _needs_window(assertions):
        # An arrival's action is the arrival: the window opens before the navigation (but after
        # any fixture arrangement, which is not a page request), so a claim about what the
        # screen requested on the way in can only read those exchanges.
        body.insert(goto_index, f"    {_WINDOW_VAR} = qa.window()")
    covered.update(scenario_covered)
    if arranged:
        # The preconditions are the book's own words for the state each fixture leaves behind —
        # the node that owns the claim already said it, so quoting it here beats an author
        # paraphrasing it (mirrors the http builder's `_arrangements` treatment).
        precondition_lines = [
            "    preconditions=[",
            *(f"        {_lit(row['provides'] or row['name'])}," for row in arranged),
            "    ],",
        ]
    else:
        precondition_lines = [
            "    preconditions=[],  # TODO(arrange): what must hold before this scenario runs",
        ]
    lines = [
        "",
        "",
        "@scenario(",
        f"    target={target_var},",
        '    mechanism="live",',
        "    covers=[",
        *(f"        {_lit(oid)}," for oid in ids if oid in scenario_covered),
        "    ],",
        *precondition_lines,
        "    checkpoints=[],  # TODO(arrange): what an observer should see it prove",
        "    forbid=[],  # TODO: the weaker observations this scenario must not settle for",
        ")",
        f"def {name}(qa: Qa) -> None:",
        f'    """Arrive at {source} via the book\'s own navigation and check what it shows."""',
        "",
        *body,
        *assertions,
    ]
    return lines


def _interaction_scenario(
    root_path: str,
    source: str,
    hops: list[dict[str, Any]],
    node_index: dict[str, dict[str, list[str]]],
    node_id: str,
    obligations: list[dict[str, Any]],
    gaps: list[Gap],
    covered: set[str],
    captured: set[tuple[str, str]],
    *,
    name: str,
    target_var: str,
    screen_routes: dict[str, str],
) -> list[str]:
    """Arrive, trigger the interaction, then assert what the book says holds afterward.

    `on:`/`trigger:`/`does:` are carried onto the packet verbatim (Amendment 3) and read here
    exactly as free prose — `on:` names the component to act on (resolved against this screen's
    own nodes), `trigger:` is quoted as a comment rather than parsed into a specific keyboard or
    pointer action (compiling English into an action is not this commit's scope), and `does:`
    is likewise quoted rather than resolved into a cross-screen navigation: several real `does:`
    values in this fixture are prose ("navigates to its detail screen at /policies/{id}"), not a
    bare screen reference, and guessing which words name a screen is not a parse. Both choices
    are why every interaction scenario also gets an `unresolved-precondition` gap alongside the
    scaffold — this compiles a starting point for a human or a model to finish, not a passing
    scenario.
    """
    _decline_captures(obligations, gaps, captured, because=(
        "the trigger is performed here, but this builder has no declared way to read a value "
        "back out of the page and bind it under that name"))
    locators = obligations[0].get("locators", {})
    on_value = next(iter(locators.get("on", [])), None)
    trigger_value = next(iter(locators.get("trigger", [])), "")
    does_value = next(iter(locators.get("does", [])), "")
    when_value = next(iter(locators.get("when", [])), "")
    # `on:` is carried verbatim (Amendment 3) — a markdown link (`[create-policy-button]
    # (#create-policy-button)`), not a bare id, so it is resolved the same way `reach.py`
    # resolves a `requires:`/`parent:` link: pull the href out, and a same-file anchor (the
    # only shape this bullet is ever written in) is joined onto this screen's own node id.
    on_href = next(iter(extract_refs(on_value or "").links), (None, None))[1]
    on_label = (on_href or on_value or "").lstrip("#") or on_value
    on_node_id = f"{source}#{on_href.lstrip('#')}" if on_href else (f"{source}#{on_value}" if on_value else "")
    ids = sorted(o["id"] for o in obligations)
    if obligations[0].get("extendsUnresolved"):
        # `qa context` stamped this when the arm's `extends:` named a target that does not
        # exist or is not the same node type — `on:`/`trigger:`/`role:`/`name:`/`keyboard:`
        # could not be inherited, so whatever locators survived are the arm's own alone.
        gaps.extend(Gap(oid, "unresolved-extends",
                         "this arm's `extends:` target is missing or not the same node type, "
                         "so its control identity could not be inherited from the base case")
                    for oid in ids)
    arranged = _arrangements(obligations)
    body: list[str] = []
    if arranged:
        body.extend(
            f"    qa.fixture({_lit(row['name'])}"
            + "".join(f", {_lit(arg)}" for arg in row.get("args", []))
            + ")"
            for row in arranged
        )
    body.append(f"    qa.goto({_lit(root_path)})")
    body.extend(_walk_hops(hops, node_index, gaps, ids))
    on_expr = _page_locator_expr(node_index.get(on_node_id, {}))
    # An unresolved-precondition gap ordinarily stands beside a real, compiled assertion on
    # purpose (`_ARRANGEMENT_GAPS`) — the claim is genuine even when the state it observes was
    # reached by a scaffold. This one is different: with no locator for `on:`, the click below
    # falls back to `body`, which is not a scaffolded version of the interaction, it is no
    # interaction at all. The assertions that follow would then be observing whatever the page
    # already looked like on arrival, not the effect of triggering anything — a check that can
    # only fail, reading as the app's defect rather than the book's. `on_resolved` withholds
    # them, the same "undetermined precondition, no executable code" rule `_page_assertions`
    # already applies to a row it cannot address.
    on_resolved = on_expr is not None
    if on_expr is None:
        body.append(f"    # TODO(arrange): no locator declared for {on_label!r}")
        # Amendment 1: one gap per obligation this interaction scenario covers, not a single
        # id keyed by the interaction's own node — every covered obligation is blocked by the
        # same missing `on:` locator.
        gaps.extend(Gap(oid, "unresolved-precondition",
                         f"no locator declared for `on:` component {on_label!r}")
                    for oid in ids)
        on_expr = "qa.page.locator('body')"
    # Recorded before the click is appended: the observation window opens immediately
    # before the action, so what it holds afterward is evidence about *this* interaction and
    # not about whatever the page requested while arriving.
    action_index = len(body)
    body.append(f"    {on_expr}.click()  # trigger: {_trailing_comment(trigger_value)}")
    if does_value:
        body.extend(_prose_comment(does_value, label="does: "))
    # A condition under which a claim holds is part of the claim: `when:` states the field
    # values this arm's assertions depend on (e.g. `name` non-empty), and page scenarios have
    # no arrangement mechanism yet (every one hardcodes `preconditions=[]` below) — so a
    # declared `when:` is never established. Compiling the assertion anyway does not test a
    # weaker version of this arm; it tests whatever the unarranged page happens to be, under
    # this arm's name — the same shape as observing `body` for a claim about a real component.
    # Both an interaction's happy and refusal arms carry their own `when:` (own bullets win over
    # `extends:`, so a refusal arm does not inherit its base's), so this withholds both alike
    # rather than only the one whose accidental default state happens to fail.
    #
    # Only one `unresolved-precondition` gap is minted per obligation here, not one per reason:
    # when the missing `on:` locator or the unarranged `when:` already withholds the assertion,
    # that is the whole story, and stacking the generic "scaffold click" gap on top of it would
    # report the same withheld claim twice under the same kind. The generic gap belongs only to
    # the case `_ARRANGEMENT_GAPS` actually describes — a real assertion compiled and stands
    # beside it on purpose.
    if on_resolved and when_value:
        gaps.extend(Gap(oid, "unarranged-interaction-precondition",
                         f"`when:` states a precondition ({when_value!r}) this scenario does "
                         "not arrange, so its assertions would observe an unestablished state")
                    for oid in ids)
    elif on_resolved:
        # This branch only established that the trigger compiles to a scaffold click, not
        # anything about `does:` — `does:` is quoted as a comment above, never parsed or
        # resolved (see the docstring), so a node whose `does:` genuinely does not resolve to
        # a target screen needs its own check to say so, not a second, unverified clause
        # riding along on this one (a node like `open-new-widget` does end up with a
        # cross-file `qa.vet(...)` and locator, via its own check's target document — this
        # branch never looked at that, so it must not claim an opinion on it either way).
        gaps.extend(Gap(oid, "unresolved-precondition",
                         f"trigger {trigger_value!r} compiles to a scaffold click on {on_label!r}, "
                         "not a verified action")
                    for oid in ids)
    assertions: list[str] = []
    scenario_covered: set[str] = set()
    vetted: list[str] = []
    for obligation in obligations:
        if not on_resolved:
            assertions.append(f"    # TODO(arrange): {obligation['id']} declares an "
                               "observation this scenario cannot make — no locator declared "
                               "for the `on:` component the assertion's state depends on")
            continue
        if when_value:
            assertions.append(f"    # TODO(arrange): {obligation['id']} declares an "
                               "observation this scenario cannot make — `when:` states a "
                               "precondition no fixture arranges")
            continue
        compiled = _page_assertions(obligation, gaps)
        if compiled is None:
            assertions.append(f"    # TODO(arrange): {obligation['id']} declares an "
                               "observation this scenario cannot make")
            continue
        assertions.extend(compiled[0])
        vetted.extend(document for document in compiled[1] if document not in vetted)
        scenario_covered.add(str(obligation["id"]))
    if not scenario_covered:
        # Every obligation this interaction would have claimed was gapped above — no addressable
        # subject, or a check this driver cannot observe. A scenario that drives a UI and vets
        # no screen is a hole in the plan wearing a function signature, so nothing is emitted.
        return []
    if _needs_window(assertions):
        body.insert(action_index, f"    {_WINDOW_VAR} = qa.window()")
    covered.update(scenario_covered)
    if arranged:
        precondition_lines = [
            "    preconditions=[",
            *(f"        {_lit(row['provides'] or row['name'])}," for row in arranged),
            "    ],",
        ]
    else:
        precondition_lines = [
            "    preconditions=[],  # TODO(arrange): what must hold before this scenario runs",
        ]
    lines = [
        "",
        "",
        "@scenario(",
        f"    target={target_var},",
        '    mechanism="live",',
        "    covers=[",
        *(f"        {_lit(oid)}," for oid in ids if oid in scenario_covered),
        "    ],",
        *precondition_lines,
        "    checkpoints=[],  # TODO(arrange): what an observer should see it prove",
        "    forbid=[],  # TODO: the weaker observations this scenario must not settle for",
        ")",
        f"def {name}(qa: Qa) -> None:",
        f"    {_lit(f'{on_label or node_id}: {trigger_value}')}",
        "",
        *body,
        # After the trigger, not before it: the state an interaction's claims are about is the
        # one the trigger produced, and `does:` is not resolved to a target screen, so the
        # documents its own checks name are the only evidence of where the run ended up.
        *(f"    qa.vet({_lit(document)})"
          for document in _vettable(vetted, screen_routes, ids, gaps)),
        *assertions,
    ]
    return lines


def _journey_scenarios(
    context: dict[str, Any],
    flow_owed: list[dict[str, Any]],
    gaps: list[Gap],
    covered: set[str],
    navigation: dict[str, Any],
    web_urls: dict[str, str],
    api_urls: dict[str, str],
    emitted_targets: set[str],
    captured: set[tuple[str, str]],
) -> list[str]:
    """One scenario per flow: walk its `steps:` in order, then observe what the walk left.

    An ordered sequence is the claim. Until `qa context` carried a flow's `steps:` as a walk
    (`context._journey_steps`), the packet said only that a flow *linked* those nodes, and a
    compiler handed a set of links can assert a journey's end state only on arrival somewhere —
    in a world the steps never ran in. With the sequence available, the journey is what gets
    emitted: arrive where it starts, perform every step in the order the book wrote them, and
    assert the flow's own `verify:` at the end, where the walk actually put the world.

    Every step is dispatched through D1's table on its **own** `(nodeType, surface)` — the
    driver is a property of who performs the step, not of where the flow happens to end. A
    journey whose steps land on more than one `(target, surface)` pairing is not compiled:
    `@scenario(target=...)` binds exactly one target, so a two-target journey has no scenario
    shape to be emitted into. That is a statement about the harness rather than about the book,
    and it is said as such — the old `uncompilable-claim` reason ("this compiler builds no
    journey scenario") is retired here, because now one exists.

    A step this builder cannot perform stops the whole journey rather than being skipped. Every
    step after it would run in a world the journey never reached, so its claims would be
    observations of the app's accidental state under the journey's name — the same rule
    `_interaction_scenario` applies to an unresolved `on:`, applied to a sequence.
    """
    by_source: dict[str, list[dict[str, Any]]] = {}
    for obligation in flow_owed:
        by_source.setdefault(str(obligation.get("source", "book")), []).append(obligation)
    node_index = _node_locator_index(context)
    screen_routes = _screen_routes(context)
    lines: list[str] = []
    for source, obligations in sorted(by_source.items()):
        ids = sorted(str(o["id"]) for o in obligations)
        # Every obligation a flow mints rides on the same walk (`context._obligations` stamps it
        # on the shared base), so reading it off the first is reading the flow's own `steps:`.
        steps = obligations[0].get("steps") or []
        if not steps:
            gaps.extend(Gap(oid, "uncompilable-claim",
                            "this flow's claim is about what its `steps:` did, and it names no "
                            "steps to walk")
                        for oid in ids)
            continue
        unresolved = [str(step.get("href", "")) for step in steps if not step.get("ref")]
        if unresolved:
            gaps.extend(Gap(oid, "uncompilable-claim",
                            "a `steps:` entry names "
                            + ", ".join(repr(href) for href in unresolved)
                            + ", which resolves to no node this book declares; a journey walked "
                              "one step short observes a world it did not reach")
                        for oid in ids)
            continue
        pairs: list[tuple[str, str]] = []
        detail = ""
        step_kind = "uncompilable-claim"
        for step in steps:
            step_surface = str(step.get("surface") or "")
            driver = navigation.get(step_surface, {}).get("driver")
            step_target, why = _dispatch_target(str(step.get("nodeType") or ""), driver)
            if step_target is None or step_target not in _BUILT_TARGETS:
                detail = why
                step_kind = "needs-target-backend" if step_target is not None else "uncompilable-claim"
                pairs = []
                break
            pairs.append((step_target, step_surface))
        if not pairs:
            gaps.extend(Gap(oid, step_kind, detail) for oid in ids)
            continue
        if len(set(pairs)) > 1:
            gaps.extend(Gap(oid, "needs-multi-target-runtime",
                            "this journey's steps are performed by "
                            + ", ".join(f"{name} on {surf!r}" for name, surf in sorted(set(pairs)))
                            + " — `@scenario(target=...)` binds one driver to one service, so "
                              "there is no scenario shape a journey across two of them fits into")
                        for oid in ids)
            continue
        journey_target, surface = pairs[0]
        nav = navigation.get(surface, {}) if surface else {}
        if journey_target == "http":
            kind, driver_name = "api", PYTHON.name
            url = api_urls.get(surface) or nav.get("entryUrl")
        elif journey_target == "playwright":
            kind, driver_name = "web", PLAYWRIGHT.name
            url = web_urls.get(surface) or nav.get("entryUrl")
        else:
            gaps.extend(Gap(oid, "needs-target-backend",
                            f"D1's table names {journey_target!r} for every step of this "
                            "journey, and this compiler builds no journey path for it")
                        for oid in ids)
            continue
        if url is None:
            gaps.extend(Gap(oid, "undeclared-entry-url",
                            f"surface {surface!r} states no `entry-url:` on a `server` or "
                            "`runbook` node, and no --base-url was passed to fall back on")
                        for oid in ids)
            continue
        arranged = _arrangements(obligations)
        if not arranged and not any(o.get("arrangesNothing") for o in obligations):
            # A journey's claims are about the world its steps left behind, and the world its
            # steps left is the world they started in plus the walk. Nothing arranged the start,
            # so the end state would be observed against whatever the previous scenario happened
            # to leave — and the assertion that then goes red is not evidence about the app.
            # Emitting no scenario is the point: a run that says nothing about this journey is
            # honest, where a run that reports a failure nobody caused is not.
            gaps.extend(Gap(oid, "unarranged-journey",
                            "this flow arranges nothing before its walk and does not say it "
                            "needs nothing — add a `fixture:` naming the arrangement, or "
                            "`fixture: none, because ...` saying why the journey's claims hold "
                            "in whatever world it finds")
                        for oid in ids)
            continue
        scenario_covered: set[str] = set()
        if journey_target == "http":
            body = _http_journey(steps, node_index, obligations, ids, gaps, scenario_covered,
                                 captured)
        else:
            body = _web_journey(steps, node_index, obligations, ids, gaps, scenario_covered,
                                captured, nav, screen_routes)
        if not scenario_covered:
            # Every claim this journey would have made was gapped above. A scenario that walks a
            # journey and asserts nothing is a hole in the plan wearing a function signature.
            continue
        covered.update(scenario_covered)
        precondition_lines = [
            "    preconditions=[",
            *(f"        {_lit(row['provides'] or row['name'])}," for row in arranged),
            "    ],",
        ]
        target_var = _target_var(surface, kind)
        if target_var not in emitted_targets:
            lines.extend([
                "",
                f"{target_var} = target({_lit(target_var)}, driver={_lit(driver_name)}, "
                f"base_url={_lit(url)})",
            ])
            emitted_targets.add(target_var)
        lines.extend([
            "",
            "",
            "@scenario(",
            f"    target={target_var},",
            '    mechanism="live",',
            "    covers=[",
            *(f"        {_lit(oid)}," for oid in ids if oid in scenario_covered),
            "    ],",
            *precondition_lines,
            "    checkpoints=[],  # TODO(arrange): what an observer should see it prove",
            "    forbid=[],  # TODO: the weaker observations this scenario must not settle for",
            ")",
            f"def {_slug(source)}_journey(qa: Qa) -> None:",
            f'    """Walk {source}\'s steps in order, then observe what the walk left."""',
            "",
            # The flow arranges once, before its first step: a `fixture:` on the flow node is a
            # statement about the world the journey starts in, not about any one step in it.
            *(f"    qa.fixture({_lit(row['name'])}"
              + "".join(f", {_lit(arg)}" for arg in row.get("args", []))
              + ")"
              for row in arranged),
            *body,
        ])
    return lines


def _http_journey(
    steps: list[dict[str, Any]],
    node_index: dict[str, dict[str, list[str]]],
    obligations: list[dict[str, Any]],
    ids: list[str],
    gaps: list[Gap],
    covered: set[str],
    captured: set[tuple[str, str]],
) -> list[str]:
    """Perform each `endpoint` step as a request, then assert the flow's claims on the last one.

    The steps are performed, not asserted. A step's own `verify:` is its own obligation and is
    compiled where that obligation lives — restating it here would file one observation against
    two claims. What this asserts is the *flow's* own `verify:`, against the response the last
    step produced, because a journey's claim is about the world its last step left and that
    response is the only thing this scenario honestly holds at the end.

    Which makes a check naming some other `path=` a finding rather than a target: it is a claim
    about a request this journey did not end on, and pointing the driver at the response it does
    hold would answer a question nobody asked. Gapped, not re-aimed.
    """
    _decline_captures(obligations, gaps, captured, because=(
        "a journey performs its steps and asserts the flow's own claim; a step's capture is "
        "emitted where that step's own obligation is compiled, not restated here"))
    lines: list[str] = []
    observed = ""
    last_path = ""
    for index, step in enumerate(steps, start=1):
        route = _route({"locators": node_index.get(str(step.get("ref", "")), {})})
        if route is None:
            gaps.extend(Gap(oid, "uncompilable-claim",
                            f"step {index} ({step.get('href')!r}) states no `method:`/`path:` "
                            "for this journey to perform")
                        for oid in ids)
            return []
        method, path = route
        body_kw = "" if method in {"GET", "DELETE", "HEAD", "OPTIONS"} else ", json_body={}"
        if body_kw:
            # Same rule as the single-scenario emitter (`_scenario_body`): a step this journey
            # cannot build a body for is withheld entirely rather than sent with
            # `json_body={}` — a journey's own claim is about the world its *last* step left,
            # so one unbuildable step anywhere in the chain leaves nothing honest for the
            # final assertions to observe.
            gaps.extend(Gap(oid, "unarranged-request-body",
                            f"step {index} is a {method} and the book carries no request body")
                        for oid in ids)
            return []
        observed = f"observed_{index}"
        lines.append(f"    {observed} = qa.http.{method.lower()}({_lit(path)})")
        if "{" in path:
            lines.append("    # TODO(arrange): the path above still carries a template variable")
            gaps.extend(Gap(oid, "unresolved-precondition",
                            f"step {index}'s path still carries a template variable")
                        for oid in ids)
        last_path = path
    for obligation in obligations:
        oid = str(obligation["id"])
        assertions: list[str] = []
        whole = True
        for row in obligation.get("checksDeclared", []):
            named = row.get("args", {}).get("path")
            if isinstance(named, str) and named != last_path:
                note = (f"`{row.get('name')}` names `path={named}`, and this journey ended on "
                        f"`{last_path}` — a journey's claim is about the world its last step "
                        "left, so there is no response here this check is about")
                lines.append(f"    # TODO(arrange): {note}")
                gaps.append(Gap(oid, "uncompilable-claim", note))
                whole = False
                continue
            operand, note, gap_kind = _operand(str(row.get("name")), observed)
            if note:
                lines.append(f"    # TODO(arrange): {note}")
                gaps.append(Gap(oid, gap_kind, note))
                whole = False
                continue
            assertions.append(
                f"    qa.verify({_lit(row['name'])}, {operand}{_kwargs(row.get('args', {}))}, "
                f"covers=[{_lit(oid)}])"
            )
        if whole and assertions:
            lines.append("")
            lines.append(f"    # {oid}")
            lines.extend(assertions)
            covered.add(oid)
    return lines


def _web_journey(
    steps: list[dict[str, Any]],
    node_index: dict[str, dict[str, list[str]]],
    obligations: list[dict[str, Any]],
    ids: list[str],
    gaps: list[Gap],
    covered: set[str],
    captured: set[tuple[str, str]],
    nav: dict[str, Any],
    screen_routes: dict[str, str],
) -> list[str]:
    """Arrive where the journey starts, click every step in order, then observe the end.

    The arrival is the book's own navigation walk to the screen the *first step* lives on, not
    to whatever the flow's `start:` bullet names: `start:` and the first step are two spellings
    of where the journey begins, and only one of them is the node a step is performed on. Where
    they disagree the steps are the sequence, and the sequence is the claim.

    Only `interaction` steps are performed. A `screen` named as a step is a place rather than an
    action — there is nothing to do to it, and navigating there directly would abandon the walk
    that was supposed to arrive there, which is the whole defect this builder exists to remove.
    """
    _decline_captures(obligations, gaps, captured, because=(
        "a journey performs its steps and asserts the flow's own claim; a step's capture is "
        "emitted where that step's own obligation is compiled, not restated here"))
    first_source = str(steps[0].get("ref", "")).split("#")[0]
    hops = (nav.get("routes") or {}).get(first_source)
    if hops is None:
        gaps.extend(Gap(oid, "uncompilable-claim",
                        f"no route computed to {first_source!r}, where this journey's first "
                        "step lives")
                    for oid in ids)
        return []
    lines: list[str] = [f"    qa.goto({_lit(str(nav.get('rootPath') or '/'))})"]
    lines.extend(_walk_hops(hops, node_index, gaps, ids))
    # Recorded before the first step: an observation window opened here holds what the whole
    # journey requested, which is what a flow's claim about the journey needs.
    action_index = len(lines)
    for index, step in enumerate(steps, start=1):
        node_type = str(step.get("nodeType") or "")
        if node_type != "interaction":
            gaps.extend(Gap(oid, "uncompilable-claim",
                            f"step {index} names a {node_type or 'untyped'} node, which is a "
                            "place rather than an action; this builder performs only "
                            "`interaction` steps")
                        for oid in ids)
            return []
        ref = str(step.get("ref", ""))
        locators = node_index.get(ref, {})
        on_value = next(iter(locators.get("on", [])), None)
        trigger_value = next(iter(locators.get("trigger", [])), "")
        on_href = next(iter(extract_refs(on_value or "").links), (None, None))[1]
        on_label = (on_href or on_value or "").lstrip("#") or on_value
        on_node_id = f"{ref.split('#')[0]}#{on_href.lstrip('#')}" if on_href else ""
        expr = _page_locator_expr(node_index.get(on_node_id, {}))
        if expr is None:
            gaps.extend(Gap(oid, "uncompilable-claim",
                            f"step {index} acts on {on_label!r}, which declares no role/name "
                            "pair and no selector to address it by; every step after it would "
                            "run in a world this journey never reached")
                        for oid in ids)
            return []
        lines.append(f"    {expr}.click()  # step {index}: {_trailing_comment(trigger_value)}")
    assertions: list[str] = []
    vetted: list[str] = []
    for obligation in obligations:
        compiled = _page_assertions(obligation, gaps)
        if compiled is None:
            assertions.append(f"    # TODO(arrange): {obligation['id']} declares an observation "
                              "this journey cannot make")
            continue
        assertions.extend(compiled[0])
        vetted.extend(document for document in compiled[1] if document not in vetted)
        covered.add(str(obligation["id"]))
    if not covered:
        return []
    if _needs_window(assertions):
        lines.insert(action_index, f"    {_WINDOW_VAR} = qa.window()")
    return [
        *lines,
        *(f"    qa.vet({_lit(document)})"
          for document in _vettable(vetted, screen_routes, ids, gaps)),
        *assertions,
    ]

def cmd_compile_plan(
    spec_dir: Path,
    *,
    out: Path | None = None,
    story: str = "",
    run_id: str | None = None,
    base_url: str | None = None,
) -> QaOutcome:
    """Compile `spec_dir/qa-okf-context.json` into a plan skeleton.

    `base_url` is a fallback for a surface whose book states no `entry-url:`, used only when
    a caller explicitly passed one — each target's real `base_url` is read per-surface off the
    book (Phase 2h). Left `None` (the CLI's own default), a surface with nothing stated compiles
    an `undeclared-entry-url` gap instead.

    Writing over an existing plan is refused. What is on disk may be an authored plan with
    hours of arrangement in it, and this command has no way to tell that from its own last
    output — so it declines and names the path, rather than deciding on the author's behalf.
    """
    context_file = spec_dir / "qa-okf-context.json"
    try:
        packet = json.loads(context_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return QaOutcome(ok=False, message=f"error: {exc}", status="invalid",
                         data={"status": "invalid", "problems": [str(exc)]})

    story_name = story or str(packet.get("story", "") or "story")
    source, gaps = compile_plan_gaps(packet, story=story_name, run_id=run_id, base_url=base_url)

    owed = _owed(packet)
    declared = [o for o in owed if o.get("checksDeclared")]
    # `debt` reads off the same `{emitted, gap}` partition `compile_plan_gaps` already proved
    # total, rather than re-deriving "declares no check" here a second time by re-filtering
    # `checksDeclared` — `no-verify-declared` is the gap the compiler itself mints for exactly
    # that obligation, in the order it walked them, so this reads the id off the gap instead.
    owed_ids = [str(o["id"]) for o in owed]
    no_verify_ids = {gap.obligation_id for gap in gaps if gap.kind == "no-verify-declared"}
    data = {
        "owed": len(owed),
        "declared": len(declared),
        "debt": [oid for oid in owed_ids if oid in no_verify_ids],
        # Doctor-shaped, not doctor-imported: `severity`/`code`/`message`/`ref` are the field
        # names `doctor.Finding` uses, and `code` is the gap's own `kind` — the vocabulary the
        # `Gap` docstring already promises doctor reads rather than redefines. A caller that
        # wants real `Finding` objects reuses `doctor.gap_findings` on the same `Gap` list;
        # this is the shape for one that only has this command's JSON output to read.
        "gaps": [
            {"severity": "error", "code": gap.kind, "message": gap.detail, "ref": gap.obligation_id}
            for gap in gaps
        ],
    }

    if out is None:
        return QaOutcome(ok=True, message=source, status="passed", data={**data, "plan": source})
    if out.exists():
        return QaOutcome(
            ok=False,
            message=f"error: {out} already exists; move it aside or compile to stdout",
            status="invalid",
            data={**data, "problems": [f"{out} already exists"]},
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(source, encoding="utf-8")
    return QaOutcome(
        ok=True,
        message=(f"Compiled {len(declared)} of {len(owed)} owed obligations into {out}.\n"
                 f"{len(data['debt'])} owed obligation(s) declare no `verify:` and are listed "
                 f"as book debt in the file."),
        status="passed",
        data=data,
    )
