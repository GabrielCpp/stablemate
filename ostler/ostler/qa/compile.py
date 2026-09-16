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

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ostler.checks import _rooted
from ostler.markdown import extract_refs
from ostler.qa import references
from ostler.qa.outcome import QaOutcome


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
    """
    obligation_id: str
    kind: str
    detail: str

#: What each check is handed. `http_status` and `conflict_on_stale` read a response — status
#: line, headers, problem body — so the compiled call takes the response object. `json_path`
#: walks a decoded document, `visible` addresses the page. Everything else observes a subject
#: the scenario must already be holding: a record read before *and* after, a key inventory, an
#: event log. The book names that subject and not where it came from, which is exactly the
#: arrangement it does not carry, so those compile to a marker rather than to a call whose
#: operand would have to be invented.
_RESPONSE_CHECKS = frozenset({"http_status", "conflict_on_stale"})
_BODY_CHECKS = frozenset({"json_path"})
_PAGE_CHECKS = frozenset({"visible"})

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
    """The HTTP method and path template this obligation's node is addressed by."""
    for value in obligation.get("locators", {}).get("route", []):
        matched = _ROUTE.match(value)
        if matched:
            return matched.group(1).upper(), matched.group(2)
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
    booleans — `absent=false` is the book's spelling and a `NameError` in Python — so the
    two literals JSON and Python disagree about are spelled here.
    """
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, list):
        return "[" + ", ".join(_lit(item) for item in value) + "]"
    return json.dumps(value)


def _kwargs(args: dict[str, Any]) -> str:
    """Render check arguments, wrapping only the literals a reference was found in.

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


def _slug(path: str) -> str:
    stem = path.rsplit("/", 1)[-1].removesuffix(".md")
    ident = _IDENT.sub("_", stem).strip("_").lower()
    return ident or "book"


def _owed(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [o for o in context.get("obligations", []) if o.get("required", True)]


def _is_page_obligation(obligation: dict[str, Any]) -> bool:
    return any(row.get("name") in _PAGE_CHECKS for row in obligation.get("checksDeclared", []))


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


def _page_locator_expr(locators: dict[str, list[str]]) -> str | None:
    """A concrete Playwright locator expression built from a node's own book-declared locators.

    `_verify_visible` (the harness's `visible` check implementation) calls `observed.is_visible()`
    when `observed` has that method, and otherwise falls back to `bool(observed)` — which is
    always `True` for a Playwright `Page`. Handing it the bare `page` object (as the older,
    HTTP-oriented `_operand` does for every `_PAGE_CHECKS` row) is a check that can never fail;
    this builds a real `Locator` instead, from `role`/`name` (preferred — the same identity a
    person clicking through the screen would use) or `selector` (the escape hatch a `role:`-less
    component's book entry gives it).
    """
    role = next(iter(locators.get("role", [])), None)
    name = next(iter(locators.get("name", [])), None)
    selector = next(iter(locators.get("selector", [])), None)
    if role and name:
        return f"qa.by_role({_lit(role)}, name={_lit(name)})"
    if role:
        return f"qa.by_role({_lit(role)})"
    if selector:
        return f"qa.by_css({_lit(selector)})"
    return None


def compile_plan(
    context: dict[str, Any],
    *,
    story: str,
    run_id: str | None = None,
    base_url: str = "http://localhost:8000",
) -> str:
    """Render a `qa_plan.py` skeleton covering every obligation the change owes live proof.

    The plan is not expected to pass as emitted — a POST whose body the book never wrote
    cannot be. It is expected to *validate*: `ostler qa validate` reports zero uncovered
    obligations against it exactly when the book declared a check for everything it owes.
    """
    source, _gaps = compile_plan_gaps(context, story=story, run_id=run_id, base_url=base_url)
    return source


def compile_plan_gaps(
    context: dict[str, Any],
    *,
    story: str,
    run_id: str | None = None,
    base_url: str = "http://localhost:8000",
) -> tuple[str, list[Gap]]:
    """`compile_plan`'s source, plus the structured gap report it compiled alongside it.

    Same rendering, same TODO markers in the source — this is the one place that also
    hands back *why* each conditional TODO fired, as `(obligation id, gap kind, detail)`,
    for a caller (`doctor`) that wants to map book debt to obligations without re-parsing
    the compiled Python.
    """
    gaps: list[Gap] = []
    owed = _owed(context)
    # Page-checked obligations (a screen's `visible(...)` bullets) are compiled by navigating
    # there, not by the HTTP-verb-and-path machinery below (`_route`/`_ROUTE`) — split them out
    # up front so the `by_source` grouping and its `target=api` scenarios never see them.
    http_owed = [o for o in owed if not _is_page_obligation(o)]
    page_owed = [o for o in owed if _is_page_obligation(o)]
    lines: list[str] = [
        "# Compiled from the book by `ostler qa compile-plan`. Every `covers=` below is the",
        "# obligation the book itself attributed the check to. Fill the TODO markers from the",
        "# story, the fixtures and the flows — not from the implementation, which is the thing",
        "# under test and cannot also be the specification it is tested against.",
        "",
        "from ostler_qa import Qa, plan, scenario, target",
        "",
        "",
        f"plan(run_id={_lit(run_id or f'qa-{story}')}, story={_lit(story)})",
        "",
        f'api = target("api", driver="python", base_url={_lit(base_url)})',
        "",
    ]

    by_source: dict[str, list[dict[str, Any]]] = {}
    for obligation in http_owed:
        by_source.setdefault(str(obligation.get("source", "book")), []).append(obligation)

    debt: list[dict[str, Any]] = []
    for source, obligations in by_source.items():
        declared = [o for o in obligations if o.get("checksDeclared")]
        debt.extend(o for o in obligations if not o.get("checksDeclared"))
        # A scenario claiming an id its body never asserts is refused by `qa validate`, and
        # rightly: the claim would read as covered in every report while nothing observed it.
        # An obligation with no declared check is book debt, listed below rather than claimed.
        if not declared:
            continue
        lines.append("")
        lines.append("")
        lines.append("@scenario(")
        lines.append("    target=api,")
        lines.append('    mechanism="live",')
        lines.append("    covers=[")
        lines.extend(f"        {_lit(o['id'])}," for o in declared)
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
        lines.extend(_scenario_body(declared, gaps))

    page_declared = [o for o in page_owed if o.get("checksDeclared")]
    debt.extend(o for o in page_owed if not o.get("checksDeclared"))
    navigation = context.get("navigation", {}) if isinstance(context.get("navigation"), dict) else {}
    if page_declared and _has_screens(navigation):
        lines.extend(_compile_page_scenarios(context, page_declared, gaps, base_url))

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

    return "\n".join(lines).rstrip() + "\n", gaps


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


def _scenario_body(obligations: list[dict[str, Any]], gaps: list[Gap]) -> list[str]:
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
        if route is not None:
            method, template = route
            path = _concrete_path(rows) or template
            status = _expect_status(rows)
            path_refs = references.find_references(path)
            for ref in path_refs:
                if not _resolved(ref, produced_facts, produced_captures):
                    gaps.append(Gap(oid, "unresolved-precondition",
                                     f"the path references {ref!r}, not resolvable without running the plan"))
            # A route path is almost never a whole reference — `/orgs/@seeded-acme.id/projects`
            # embeds one mid-string. `Http` takes plain literals now (Fix 2), so a path that
            # found a reference is wrapped in the harness's one explicit substitution call;
            # every other path is left a bare literal `Http` never touches for resolution.
            path_expr = f"qa.resolve({_lit(path)})" if path_refs else _lit(path)
            body = "" if method in {"GET", "DELETE", "HEAD", "OPTIONS"} else ", json_body={}"
            todo = ""
            if body != "":
                todo = "  # TODO(arrange): the book carries no request body"
                gaps.append(Gap(oid, "unresolved-precondition", "the book carries no request body"))
            expect = f", expect_status={status}" if status is not None else ""
            lines.append(f"    {name} = qa.http.{method.lower()}({path_expr}{body}{expect}){todo}")
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
            if source_path.startswith("$") and route is not None:
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
            else:
                # A UI-locator capture has no response here to read — the book says what to
                # capture and not where the page action that would produce it lives. A `$.`-
                # rooted capture with no route is the same shape: nothing was observed to read
                # a field off of. Both get the same scaffolding as an arrangement gap: a TODO
                # and a gap, no credit.
                if source_path.startswith("$"):
                    note = f"capture {cname!r} from {source_path!r} has no observed response to read"
                else:
                    note = f"capture {cname!r} from {source_path!r} names a UI locator, not a response field"
                lines.append(f"    # TODO(arrange): {note}")
                gaps.append(Gap(oid, "uncompilable-claim", note))

        for row in rows:
            for ref in references.find_references(json.dumps(row.get("args", {}))):
                if not _resolved(ref, produced_facts, produced_captures):
                    gaps.append(Gap(oid, "unresolved-precondition",
                                     f"a verify argument references {ref!r}, not resolvable without running the plan"))
            operand, note = _operand(row["name"], name)
            if note:
                lines.append(f"    # TODO(arrange): {note}")
                gaps.append(Gap(oid, "uncompilable-claim", note))
            lines.append(
                f"    qa.verify({_lit(row['name'])}, {operand}{_kwargs(row.get('args', {}))}, covers=[{_lit(oid)}])"
            )
    return lines


def _operand(check: str, observed: str) -> tuple[str, str]:
    """What the compiled call is handed, and the arrangement note it still needs."""
    if check in _RESPONSE_CHECKS:
        return observed, ""
    if check in _BODY_CHECKS:
        return f"{observed}.json()", ""
    if check in _PAGE_CHECKS:
        return "qa.page", ""
    # A subject check compares observations the book never says how to take — `persists`
    # wants the record from before the process died and the one read after it came back.
    return observed, f"`{check}` observes a subject, not a response — hand it the pair"


def _compile_page_scenarios(
    context: dict[str, Any],
    page_declared: list[dict[str, Any]],
    gaps: list[Gap],
    base_url: str,
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
    lines: list[str] = ["", "", 'web = target("web", driver="playwright", base_url=' + _lit(base_url) + ")"]
    node_index = _node_locator_index(context)
    by_screen: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for obligation in page_declared:
        key = (str(obligation.get("surface", "")), str(obligation.get("source", "")))
        by_screen.setdefault(key, []).append(obligation)

    navigation = context.get("navigation", {}) if isinstance(context.get("navigation"), dict) else {}
    for (surface, source), group in sorted(by_screen.items()):
        nav = navigation.get(surface) if surface else None
        if nav is None:
            gaps.append(Gap(source, "uncompilable-claim",
                             f"surface {surface!r} has no `navigation` data to address this screen by"))
            continue
        if source in set(nav.get("unreachable", [])):
            # Correction 5': an unreachable screen is a finding, not a compile target. Reusing
            # the doctor-recognized `unreachable-screen` code (the same one `doctor.py`'s own
            # `reach`-based check already mints) rather than collapsing it into
            # `uncompilable-claim` — a screen with no route in and a screen with no addressable
            # subject are different defects and should not read as the same finding.
            gaps.append(Gap(source, "unreachable-screen",
                             f"{surface}'s navigation cannot reach this screen; no scenario compiled"))
            continue
        hops = nav.get("routes", {}).get(source)
        if hops is None:
            gaps.append(Gap(source, "uncompilable-claim", "no route computed for this screen"))
            continue
        if source in set(nav.get("undeclared", [])):
            # Amendment 2: reachable, but the screen's `requires:`/`params:` bullets are
            # literally absent — not "none", absent. One gap per screen, not per obligation:
            # every `visible(...)` bullet on the screen shares the same undeclared-precondition
            # fact, and a live-audit gate already renders one line per gap (see the coordinator
            # note this report answers) — multiplying this by obligation count would not add
            # information.
            gaps.append(Gap(source, "screen-preconditions-undeclared",
                             "reachable, but this screen declares no `requires:`/`params:` bullets"))

        by_node: dict[str, list[dict[str, Any]]] = {}
        for obligation in group:
            by_node.setdefault(str(obligation["node"]), []).append(obligation)

        plain: dict[str, list[dict[str, Any]]] = {}
        exclusive: list[str] = []
        interactions: list[str] = []
        for node_id, obs in sorted(by_node.items()):
            locators = obs[0].get("locators", {})
            if locators.get("on"):
                interactions.append(node_id)
            elif locators.get("states"):
                states_text = "; ".join(locators["states"])
                gaps.append(Gap(node_id, "unresolved-precondition",
                                 f"carries `states:` ({states_text!r}); no scenario compiled "
                                 "for a state-scoped arrangement"))
            elif "#" not in node_id and not _page_locator_expr(locators):
                gaps.append(Gap(node_id, "uncompilable-claim",
                                 "no addressable `### <component>` owns this `visible(...)` claim"))
            elif locators.get("exclusiveWith"):
                exclusive.append(node_id)
            else:
                plain[node_id] = obs

        if plain:
            lines.extend(_arrival_scenario(surface, source, hops, node_index, plain, gaps,
                                            name=f"{_slug(source)}_arrival"))
        for node_id in exclusive:
            lines.extend(_arrival_scenario(surface, source, hops, node_index,
                                            {node_id: by_node[node_id]}, gaps,
                                            name=f"{_slug(source)}_{_node_slug(node_id)}"))
        for node_id in interactions:
            lines.extend(_interaction_scenario(surface, source, hops, node_index, node_id,
                                                by_node[node_id], gaps,
                                                name=f"{_slug(source)}_{_node_slug(node_id)}"))
    return lines


def _node_slug(node_id: str) -> str:
    fragment = node_id.rsplit("#", 1)[-1]
    return _slug(fragment)


def _walk_hops(
    hops: list[dict[str, Any]],
    node_index: dict[str, dict[str, list[str]]],
    gaps: list[Gap],
    oid: str,
) -> list[str]:
    """One `.click()` per hop the book's own navigation-derivation logic found (Correction 2')."""
    lines: list[str] = []
    for hop in hops:
        target_node = str(hop.get("node", ""))
        expr = _page_locator_expr(node_index.get(target_node, {}))
        if expr is None:
            lines.append(f"    # TODO(arrange): no locator declared for {target_node!r}"
                         f" ({hop.get('label', '')!r})")
            gaps.append(Gap(oid, "unresolved-precondition",
                             f"no locator declared for navigation hop {target_node!r}"))
            continue
        lines.append(f"    {expr}.click()  # {hop.get('label', '')}")
    return lines


def _arrival_scenario(
    surface: str,
    source: str,
    hops: list[dict[str, Any]],
    node_index: dict[str, dict[str, list[str]]],
    by_node: dict[str, list[dict[str, Any]]],
    gaps: list[Gap],
    *,
    name: str,
) -> list[str]:
    obligations = [o for obs in by_node.values() for o in obs]
    ids = sorted(o["id"] for o in obligations)
    lines = [
        "",
        "",
        "@scenario(",
        "    target=web,",
        '    mechanism="live",',
        "    covers=[",
        *(f"        {_lit(oid)}," for oid in ids),
        "    ],",
        "    preconditions=[],  # TODO(arrange): what must hold before this scenario runs",
        "    checkpoints=[],  # TODO(arrange): what an observer should see it prove",
        "    forbid=[],  # TODO: the weaker observations this scenario must not settle for",
        ")",
        f"def {name}(qa: Qa) -> None:",
        f'    """Arrive at {source} via the book\'s own navigation and check what it shows."""',
        "",
        f"    qa.goto({_lit(surface)})  # TODO(arrange): the app's root URL for this surface",
    ]
    lines.extend(_walk_hops(hops, node_index, gaps, ids[0] if ids else source))
    for node_id, obs in sorted(by_node.items()):
        operand = _page_locator_expr(obs[0].get("locators", {})) or "qa.page.locator('body')"
        for obligation in obs:
            for row in obligation.get("checksDeclared", []):
                if row.get("name") not in _PAGE_CHECKS:
                    continue
                lines.append(
                    f"    qa.verify({_lit(row['name'])}, {operand}{_kwargs(row.get('args', {}))}, "
                    f"covers=[{_lit(obligation['id'])}])"
                )
    return lines


def _interaction_scenario(
    surface: str,
    source: str,
    hops: list[dict[str, Any]],
    node_index: dict[str, dict[str, list[str]]],
    node_id: str,
    obligations: list[dict[str, Any]],
    gaps: list[Gap],
    *,
    name: str,
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
    locators = obligations[0].get("locators", {})
    on_value = next(iter(locators.get("on", [])), None)
    trigger_value = next(iter(locators.get("trigger", [])), "")
    does_value = next(iter(locators.get("does", [])), "")
    # `on:` is carried verbatim (Amendment 3) — a markdown link (`[create-policy-button]
    # (#create-policy-button)`), not a bare id, so it is resolved the same way `reach.py`
    # resolves a `requires:`/`parent:` link: pull the href out, and a same-file anchor (the
    # only shape this bullet is ever written in) is joined onto this screen's own node id.
    on_href = next(iter(extract_refs(on_value or "").links), (None, None))[1]
    on_label = (on_href or on_value or "").lstrip("#") or on_value
    on_node_id = f"{source}#{on_href.lstrip('#')}" if on_href else (f"{source}#{on_value}" if on_value else "")
    ids = sorted(o["id"] for o in obligations)
    lines = [
        "",
        "",
        "@scenario(",
        "    target=web,",
        '    mechanism="live",',
        "    covers=[",
        *(f"        {_lit(oid)}," for oid in ids),
        "    ],",
        "    preconditions=[],  # TODO(arrange): what must hold before this scenario runs",
        "    checkpoints=[],  # TODO(arrange): what an observer should see it prove",
        "    forbid=[],  # TODO: the weaker observations this scenario must not settle for",
        ")",
        f"def {name}(qa: Qa) -> None:",
        f'    """{on_label or node_id}: {trigger_value}"""',
        "",
        f"    qa.goto({_lit(surface)})  # TODO(arrange): the app's root URL for this surface",
    ]
    lines.extend(_walk_hops(hops, node_index, gaps, ids[0] if ids else source))
    on_expr = _page_locator_expr(node_index.get(on_node_id, {}))
    if on_expr is None:
        lines.append(f"    # TODO(arrange): no locator declared for {on_label!r}")
        gaps.append(Gap(node_id, "unresolved-precondition",
                         f"no locator declared for `on:` component {on_label!r}"))
        on_expr = "qa.page.locator('body')"
    lines.append(f"    {on_expr}.click()  # trigger: {trigger_value}")
    if does_value:
        lines.append(f"    # does: {does_value}")
    gaps.append(Gap(node_id, "unresolved-precondition",
                     f"trigger {trigger_value!r} compiles to a scaffold click on {on_label!r}, "
                     "not a verified action, and `does:` is not resolved to a target screen"))
    operand = "qa.page.locator('body')"
    for obligation in obligations:
        for row in obligation.get("checksDeclared", []):
            if row.get("name") not in _PAGE_CHECKS:
                continue
            lines.append(
                f"    qa.verify({_lit(row['name'])}, {operand}{_kwargs(row.get('args', {}))}, "
                f"covers=[{_lit(obligation['id'])}])"
            )
    return lines


def cmd_compile_plan(
    spec_dir: Path,
    *,
    out: Path | None = None,
    story: str = "",
    run_id: str | None = None,
    base_url: str = "http://localhost:8000",
) -> QaOutcome:
    """Compile `spec_dir/qa-okf-context.json` into a plan skeleton.

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
    data = {
        "owed": len(owed),
        "declared": len(declared),
        "debt": [o["id"] for o in owed if not o.get("checksDeclared")],
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
