"""Compile a QA plan skeleton out of the book, without reading the implementation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any
from typing import get_args as _get_args

from ostler import acts as acts_mod
from ostler import registry
from ostler.checks import CHECK_BY_NAME
from ostler.checks import _rooted
from ostler.markdown import extract_refs
from ostler.qa import references
from ostler.qa.harness_host import load_harness_module
from ostler.routes import is_screen_name_shaped, literal_route, why_unreadable
from ostler.qa.outcome import QaOutcome
from ostler.vet import placement as placement_mod


_ARRANGEMENT_GAPS = frozenset({
    "unresolved-precondition",
    "screen-preconditions-undeclared",
    "unarranged-interaction-precondition",
    "unidentifiable-screen",
    "unparsed-capture-bullet",
    "uncaptured-declaration",
})

GAP_KINDS = frozenset({
    "uncompilable-claim",
    "unresolved-precondition",
    "unreachable-screen",
    "screen-preconditions-undeclared",
    "needs-snapshot",
    "needs-out-of-band-observation",
    "undeclared-entry-url",
    "undeclared-bundle-id",
    "unresolved-extends",
    "undeclared-check-locator",
    "unstated-claim-combiner",
    "no-verify-declared",
    "precondition-discharged-by-arrangement",
    "unarranged-state",
    "unarranged-journey",
    "unarranged-scenario",
    "unarranged-request-body",
    "unarranged-interaction-precondition",
    "unidentifiable-screen",
    "unparsed-fixture",
    "undetermined-provided-fact",
    "unparsed-capture-bullet",
    "unparsed-check-bullet",
    "uncaptured-declaration",
    "needs-target-backend",
    "needs-multi-target-runtime",
    "invalid-http-method",
    "undeclared-launch-screen",
    "unreachable-from-launch",
})

HARNESS_LIMIT_GAPS = frozenset({
    "needs-target-backend",
    "needs-multi-target-runtime",
})


@dataclass(frozen=True)
class Gap:
    """One obligation left uncompiled, and why — `compile_plan`'s structured gap report."""
    obligation_id: str
    kind: str
    detail: str


@dataclass(frozen=True)
class Plan:
    """`compile_plan_gaps` succeeded: `source` is a plan the plan format admits."""
    source: str
    gaps: list[Gap]
    files: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Refusal:
    """`compile_plan_gaps` minted no scenario: `gaps` is the whole account of why."""
    gaps: list[Gap]


Compilation = Plan | Refusal



@dataclass(frozen=True)
class DriverSpec:
    """A driver's declared observation channels — the other half of the observability relation."""
    name: str
    observes: frozenset[str]


_harness = load_harness_module("ostler_qa")
_OBSERVES: dict[str, frozenset[str]] = {
    driver.name: frozenset(driver.observes) for driver in _harness.DRIVERS
}

PYTHON = DriverSpec("python", _OBSERVES["python"])

PLAYWRIGHT = DriverSpec("playwright", _OBSERVES["playwright"])

MAESTRO = DriverSpec("maestro", _OBSERVES["maestro"])


def _observes(name: str | None) -> str | None:
    """What check *name* is handed to look at, or `None` for an unknown/missing check."""
    spec = CHECK_BY_NAME.get(name) if name else None
    return spec.observes if spec is not None else None


def _out_of_band(name: str | None) -> bool:
    """Whether *name* observes through a channel this compiler has no handle on."""
    spec = CHECK_BY_NAME.get(name) if name else None
    return spec.out_of_band if spec is not None else False


def _unobservable_gap(oid: str, name: str | None, driver: DriverSpec) -> Gap:
    """*driver* cannot serve *name* — a real gap, not a silently dropped row."""
    observes = _observes(name)
    what = f"a {observes}" if observes else "an unknown check"
    if observes is not None and observes in driver.observes:
        return Gap(oid, "uncompilable-claim",
                    f"`{name}` observes {what}, which the {driver.name} driver can see, but "
                    f"this compiler has no page-scenario arrangement for it yet")
    return Gap(oid, "uncompilable-claim",
               f"`{name}` observes {what}, not observable from the {driver.name} driver")


_HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")
_ROUTE = re.compile(rf"^\s*`?\s*({'|'.join(_HTTP_METHODS)})\s+(\S+?)\s*`?\s*$", re.I)
_IDENT = re.compile(r"[^0-9a-zA-Z]+")



def _route(obligation: dict[str, Any]) -> tuple[str, str] | None:
    """The HTTP method and path template this obligation's node is addressed by."""
    locators = obligation.get("locators", {})
    for value in locators.get("route", []):
        matched = _ROUTE.match(value)
        if matched:
            return matched.group(1).upper(), matched.group(2)
    method = _bullet_value(next(iter(locators.get("method", [])), None))
    path = _bullet_value(next(iter(locators.get("path", [])), None))
    if method and path and method.upper() in _HTTP_METHODS:
        return method.upper(), path
    return None


def _invalid_method(obligation: dict[str, Any]) -> str | None:
    """An `endpoint`'s declared `method:` value, when it is not one of the HTTP verbs `_route` (and `_ROUTE`, for the other node type's spelling) already hold every address to."""
    locators = obligation.get("locators", {})
    method = _bullet_value(next(iter(locators.get("method", [])), None))
    if method and method.upper() not in _HTTP_METHODS:
        return method
    return None


def _concrete_path(rows: list[dict[str, Any]]) -> str | None:
    """A real path from a declared check, preferred over the route's `{id}` template."""
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
    """A Python literal spelled the way the repo's formatter would spell it."""
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, list):
        return "[" + ", ".join(_lit(item) for item in value) + "]"
    return json.dumps(value)


def _kwargs(args: dict[str, Any]) -> str:
    """Render a check's declared arguments verbatim, wrapping only literals holding a reference."""
    parts = []
    for name, value in args.items():
        if isinstance(value, str) and references.find_references(value):
            parts.append(f", {name}=qa.resolve({_lit(value)})")
        else:
            parts.append(f", {name}={_lit(value)}")
    return "".join(parts)


def _trailing_comment(text: str) -> str:
    """*text*, flattened onto one line, safe to follow real code on the same line."""
    return " ".join(text.split())


def _prose_comment(text: str, *, label: str = "") -> list[str]:
    """*text* rendered as one or more `#`-prefixed lines, each four-space indented."""
    first, *rest = text.splitlines() or [""]
    lines = [f"    # {label}{first}"]
    lines.extend(f"    #   {line}" for line in rest)
    return lines


def _slug(path: str) -> str:
    stem = path.removesuffix(".md")
    ident = _IDENT.sub("_", stem).strip("_").lower()
    return ident or "book"


def _owed(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [o for o in context.get("obligations", []) if o.get("required", True)]


def book_digest(context: dict[str, Any]) -> str:
    """A digest of *context*'s obligation id set — what a compiled plan's `book=` names."""
    ids = sorted(str(o["id"]) for o in _owed(context) if o.get("id"))
    return hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()


_DISPATCH_TABLE: dict[str, dict[str, str] | str] = {
    "interaction": {"web": "playwright", "mobile": "maestro"},
    "endpoint": {"web": "http", "mobile": "http", "http": "http"},
    "command": "cli",
}
_OBSERVED_TYPES = frozenset({"flow", "component", "screen", "field", "invocation", "method"})
_OBSERVE_ROW: dict[str, str] = {
    "web": "playwright", "mobile": "maestro", "http": "http", "cli": "cli",
}
_BUILT_TARGETS = frozenset({"playwright", "http", "cli", "maestro"})


def _dispatch_target(node_type: str, driver: str | None) -> tuple[str | None, str, str]:
    """D1's table — or `_OBSERVE_ROW`, for a type nobody performs — read once per obligation."""
    row = _OBSERVE_ROW if node_type in _OBSERVED_TYPES else _DISPATCH_TABLE.get(node_type)
    if row is None:
        if node_type == "concept":
            return None, (
                "the book links this step to a 'concept' node — a definition, not a place a "
                "claim can be observed, so D1's dispatch table (§4.1) owes it no row"
            ), "uncompilable-claim"
        return None, (
            f"the book links this step to a {node_type or 'untyped'!r} node, which D1's "
            "dispatch table (§4.1) names no row for"
        ), "uncompilable-claim"
    if isinstance(row, str):
        target = row
    else:
        if driver is None:
            return None, (
                "the surface this step's node lives on states no `driver:` on any `runbook`, so "
                "D1's dispatch table (§4.1) cannot determine what performs this step"
            ), "uncompilable-claim"
        target = row.get(driver)
        if target is None:
            return None, (
                f"D1's dispatch table (§4.1) names no target for a {node_type} step on a "
                f"{driver!r}-driven surface"
            ), "uncompilable-claim"
    if target not in _BUILT_TARGETS:
        where = "for every driver" if isinstance(row, str) else f"on a {driver!r}-driven surface"
        return target, (
            f"D1's dispatch table (§4.1) names {target!r} for a {node_type} step {where}, "
            f"but this compiler builds no {target} path yet"
        ), "needs-target-backend"
    return target, "", ""


def _gap_cli_obligations(obligations: list[dict[str, Any]], gaps: list[Gap]) -> None:
    """Command-linked obligations with no `run:` for the CLI builder to bind to."""
    for obligation in obligations:
        gaps.append(Gap(
            str(obligation["id"]), "uncompilable-claim",
            "this command's node declares no `run:` for this claim — `usage:`/`flags:`/`args:` "
            "are a prose synopsis, not a structured invocation this compiler can turn into "
            "`qa.tool(...).run(...)`",
        ))


def _cli_action(obligation: dict[str, Any]) -> list[str] | None:
    """The argument list this obligation's `run:` names, or `None` if it named none."""
    for row in obligation.get("actsDeclared") or []:
        if row.get("name") != "invoke":
            continue
        return [str(a) for a in (row.get("args", {}).get("argv") or [])]
    return None


def _cli_scenario_body(
    obligations: list[dict[str, Any]], gaps: list[Gap], covered: set[str], binary: str | None,
) -> list[str]:
    """Compile every CLI obligation's assertion half — `_scenario_body`'s counterpart for a `command` node instead of a route."""
    lines: list[str] = []
    index = 0
    for obligation in sorted(obligations, key=lambda o: tuple(o.get("docPosition") or (0, 0))):
        oid = obligation["id"]
        rows = obligation.get("checksDeclared", [])
        requirement = " ".join(str(obligation.get("requirement", "")).split())
        lines.append("")
        lines.append(f"    # {oid}")
        lines.append(f"    # {requirement}")
        index += 1
        name = f"observed_{index}"
        argv = _cli_action(obligation)
        if argv is None:
            lines.append(
                "    # TODO(arrange): this command declares no `run:` — `usage:`/`flags:`/"
                "`args:` are prose, not a concrete invocation")
            lines.append(f"    {name} = None  # TODO(arrange): what this scenario observes")
            _gap_cli_obligations([obligation], gaps)
            continue
        if binary is None:
            lines.append(
                "    # TODO(arrange): the owning `cli` node declares no `binary:`, so this "
                "compiler cannot name the executable this `run:` invokes")
            lines.append(f"    {name} = None  # TODO(arrange): what this scenario observes")
            gaps.append(Gap(
                str(oid), "uncompilable-claim",
                "the owning `cli` node declares no `binary:`, so the compiler cannot name "
                "the executable this `run:` invokes",
            ))
            continue
        call_args = ", ".join([*(_lit(a) for a in argv), "cwd=qa.scenario_id"])
        lines.append(f"    {name} = qa.tool({_lit(binary)}).run({call_args})")

        assertions: list[str] = []
        whole = True
        for row in rows:
            operand, note, kind = _operand(row["name"], name)
            if note:
                lines.append(f"    # TODO(arrange): {note}")
                gaps.append(Gap(oid, kind, note))
                whole = False
                continue
            assertions.append(
                f"    qa.verify({_lit(row['name'])}, {operand}{_kwargs(row.get('args', {}))}, "
                f"covers=[{_lit(oid)}])"
            )
        if whole:
            lines.extend(assertions)
            covered.add(oid)
    return lines


def _maestro_scenario_body(
    obligations: list[dict[str, Any]], node_index: dict[str, dict[str, list[str]]],
    gaps: list[Gap], covered: set[str], files: dict[str, str],
    screen_routes: dict[str, str], bundle_id: str, launch_screen: str,
) -> list[str]:
    """Compile every mobile obligation's own Maestro flow — `_cli_scenario_body`'s counterpart for a `mobile`-driven surface instead of a `command` node."""
    lines: list[str] = []
    index = 0
    for obligation in sorted(obligations, key=lambda o: tuple(o.get("docPosition") or (0, 0))):
        oid = str(obligation["id"])
        page = str(obligation.get("source", ""))
        if page != launch_screen:
            gaps.append(Gap(
                oid, "unreachable-from-launch",
                f"a cold `launchApp` opens on {launch_screen!r}, not {page!r}, and nothing "
                "in this obligation's own flow gets from the one to the other",
            ))
            continue
        requirement = " ".join(str(obligation.get("requirement", "")).split())
        lines.append("")
        lines.append(f"    # {oid}")
        lines.append(f"    # {requirement}")
        index += 1
        name = f"observed_{index}"

        commands: list[str] = []
        whole = True
        acts_declared = obligation.get("actsDeclared") or []
        if acts_declared:
            for row in acts_declared:
                spec = acts_mod.ACT_BY_NAME.get(str(row.get("name")))
                if spec is None or acts_mod.MOBILE not in spec.drivers:
                    gaps.append(Gap(oid, "uncompilable-claim",
                                     f"`{row.get('name')}` arranges this obligation's interaction "
                                     "and the mobile driver cannot perform it"))
                    whole = False
                    break
                locator = _maestro_act_locator(row)
                if locator is None:
                    gaps.append(Gap(oid, "uncompilable-claim",
                                     f"`{row.get('name')}` points at a subject with no `testID=` "
                                     "selector and no `name:` for the mobile driver to address"))
                    whole = False
                    break
                act_args = row.get("args", {})
                if spec.name == "press":
                    book_key = str(act_args.get("key", ""))
                    canonical_key = _maestro_press_key(book_key)
                    if canonical_key is None:
                        gaps.append(Gap(oid, "uncompilable-claim",
                                         f"`press` names key {book_key!r}, which is not one of "
                                         "Maestro's `pressKey` keys"))
                        whole = False
                        break
                    act_args = {**act_args, "key": canonical_key}
                commands.extend(_maestro_act_commands(spec.name, locator, act_args))
        else:
            on_value = next(iter(obligation.get("locators", {}).get("on", [])), None)
            if on_value is not None:
                source = str(obligation.get("source", ""))
                on_href = next(iter(extract_refs(on_value).links), (None, None))[1]
                on_label = (on_href or on_value or "").lstrip("#") or on_value
                on_node_id = f"{source}#{on_href.lstrip('#')}" if on_href else ""
                on_locator = _maestro_locator(node_index.get(on_node_id, {}))
                if on_locator is None:
                    gaps.append(Gap(oid, "uncompilable-claim",
                                     f"`on:` names {on_label!r}, which declares no `testID=` "
                                     "selector and no `name:` for the mobile driver to address"))
                    whole = False
                else:
                    commands.extend(_maestro_act_commands("click", on_locator, {}))

        assertions: list[str] = []
        python_lines: list[str] = []
        documents: list[str] = []
        if whole:
            for row in obligation.get("checksDeclared", []):
                channel = _observes(str(row.get("name")))
                if channel == "subject":
                    operand, note, kind = _operand(str(row["name"]), name)
                    if note:
                        gaps.append(Gap(oid, kind, note))
                        whole = False
                        continue
                    python_lines.append(
                        f"    qa.verify({_lit(row['name'])}, {operand}"
                        f"{_kwargs(row.get('args', {}))}, covers=[{_lit(oid)}])"
                    )
                    continue
                if channel != "page":
                    gaps.append(_unobservable_gap(oid, row.get("name"), MAESTRO))
                    whole = False
                    continue
                locator = _maestro_check_locator(row, obligation, gaps)
                if locator is None:
                    whole = False
                    continue
                assertions.extend(
                    _maestro_check_commands(str(row["name"]), locator, row.get("args", {}))
                )
                document = _check_document(row, obligation)
                if document and document not in documents:
                    documents.append(document)
                python_lines.append(
                    f"    qa.verify({_lit(row['name'])}, {name}.exit_code == 0"
                    f"{_kwargs(row.get('args', {}))}, covers=[{_lit(oid)}])"
                )
        if not whole or not (commands or assertions or python_lines):
            continue
        flow_path = f"maestro/{_slug(oid)}.yaml"
        files[flow_path] = _maestro_flow_yaml([*commands, *assertions], bundle_id)
        lines.append(f"    {name} = qa.maestro.run(qa.spec_dir / {_lit(flow_path)})")
        lines.extend(python_lines)
        if assertions:
            lines.extend(
                f"    qa.vet({_lit(document)})"
                for document in _vettable(documents, screen_routes, [oid], gaps, mobile=True)
            )
        covered.add(oid)
    return lines


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
    """Gap the captures this builder will not emit, from inside the builder that declined."""
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


def _decline_captures_by_node(
    node_ids: list[str],
    captures_by_node: dict[str, list[tuple[str, dict[str, Any]]]],
    gaps: list[Gap],
    captured: set[tuple[str, str]],
    *,
    because: str,
) -> None:
    """Gap the captures `_captures_by_node` attaches to *node_ids*, by node rather than obligation."""
    for node_id in node_ids:
        for oid, capture in captures_by_node.get(node_id, []):
            name = capture.get("name")
            if not name:
                continue
            captured.add((oid, str(name)))
            gaps.append(Gap(
                oid, "uncaptured-declaration",
                f"capture {str(name)!r} from {str(capture.get('from', ''))!r} is declared on "
                f"this node and {because}",
            ))


def _has_screens(navigation: dict[str, Any]) -> bool:
    """Condition 1: a book with zero screen nodes on every surface grows no Playwright target."""
    return any(
        int(surface_nav.get("counts", {}).get("screens", 0)) > 0
        for surface_nav in navigation.values()
    )


def _entry_url_gap(surface: str) -> tuple[str, str]:
    """The kind and detail for an obligation whose surface resolved to no address."""
    return "undeclared-entry-url", (
        f"surface {surface!r} states no `entry-url:` on a `server` or `runbook` node, "
        "and no --base-url was passed to fall back on"
    )


def _bundle_id_gap(surface: str) -> tuple[str, str]:
    """The kind and detail for a mobile obligation whose surface resolved to no bundle id."""
    return "undeclared-bundle-id", (
        f"surface {surface!r} states no `bundle-id:` on a `runbook` node"
    )


def _launch_screen_gap(surface: str) -> tuple[str, str]:
    """The kind and detail for a mobile obligation whose surface resolved to no launch screen."""
    return "undeclared-launch-screen", (
        f"surface {surface!r} states no `launch-screen:` on a `runbook` node"
    )


def _split_by_entry_url(
    obligations: list[dict[str, Any]],
    navigation: dict[str, Any],
    base_url: str | None,
    gaps: list[Gap],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Partition *obligations* on whether their surface's target `base_url` is known."""
    resolved_by_surface: dict[str, str | None] = {}
    for obligation in obligations:
        surface = str(obligation.get("surface") or "")
        if surface in resolved_by_surface:
            continue
        surface_nav = navigation.get(surface, {}) if surface else {}
        entry_url = surface_nav.get("entryUrl")
        fallback = base_url
        resolved_by_surface[surface] = entry_url or fallback

    kept: list[dict[str, Any]] = []
    for obligation in obligations:
        surface = str(obligation.get("surface") or "")
        url = resolved_by_surface[surface]
        if url is None:
            kind, detail = _entry_url_gap(surface)
            gaps.append(Gap(str(obligation["id"]), kind, detail))
            continue
        kept.append(obligation)

    resolved = {surface: url for surface, url in resolved_by_surface.items() if url is not None}
    return kept, resolved


def _target_var(surface: str, kind: str) -> str:
    """The variable (and literal target `name`) one surface's `kind` ("api"/"web") target gets."""
    return f"{_slug(surface)}_{kind}"


def _screen_routes(context: dict[str, Any]) -> dict[str, str]:
    """Each screen file's `route:`, as `qa context` read it off the book."""
    return {
        str(path): str(route)
        for path, route in (context.get("screenRoutes") or {}).items()
    }


def _node_locator_index(context: dict[str, Any]) -> dict[str, dict[str, list[str]]]:
    """Every node's own `locators`, keyed by node id — including ones with no *required* claim."""
    index: dict[str, dict[str, list[str]]] = {}
    for obligation in context.get("obligations", []):
        node_id = obligation.get("node")
        if node_id and node_id not in index:
            index[node_id] = obligation.get("locators", {})
    return index


_CODE_SPAN = re.compile(r"^\s*`?\s*(.*?)\s*`?\s*$")

_NONE_SENTINEL = "none"


def _bullet_value(raw: str | None) -> str | None:
    """*raw* as one line, stripped of a wrapping code span, with `none` read as absent."""
    if raw is None:
        return None
    match = _CODE_SPAN.match(" ".join(raw.split()))
    assert match is not None, "_CODE_SPAN matches any single line (its inner group is `.*?`)"
    value = match.group(1).strip()
    if not value or value.lower() == _NONE_SENTINEL:
        return None
    return value


try:
    from playwright._impl._api_structures import AriaRole as _AriaRole
    _MATCHABLE_ROLES: frozenset[str] | None = frozenset(_get_args(_AriaRole)) - {
        "generic", "none", "presentation",
    }
except ImportError:  # pragma: no cover - the `qa` extra is what installs playwright
    _MATCHABLE_ROLES = None


def _page_locator_expr(locators: dict[str, list[str]]) -> str | None:
    """A concrete Playwright locator expression built from a node's own book-declared locators."""
    role = _bullet_value(next(iter(locators.get("role", [])), None))
    if role is not None and (_MATCHABLE_ROLES is None or role not in _MATCHABLE_ROLES):
        role = None
    name = _bullet_value(next(iter(locators.get("name", [])), None))
    selector = _bullet_value(next(iter(locators.get("selector", [])), None))
    if role and name:
        return f"qa.by_role({_lit(role)}, name={_lit(name)})"
    if selector:
        if placement_mod.parse_scheme_selector(selector) is not None:
            return None
        return f"qa.by_css({_lit(selector)})"
    return None


def _maestro_locator(locators: dict[str, list[str]]) -> tuple[str, str] | None:
    """A `(Maestro selector key, value)` pair built from a node's own book-declared locators."""
    selector = _bullet_value(next(iter(locators.get("selector", [])), None))
    if selector:
        parsed = placement_mod.parse_scheme_selector(selector)
        if parsed is not None and parsed[0] == "testID":
            return "id", parsed[1]
    name = _bullet_value(next(iter(locators.get("name", [])), None))
    if name:
        return "text", name
    return None


def _maestro_flow_yaml(commands: list[str], bundle_id: str) -> str:
    return "\n".join([f'appId: "{bundle_id}"', "---", "- launchApp", *commands]) + "\n"


_MAESTRO_PRESS_KEYS: frozenset[str] = frozenset({
    "home", "lock", "enter", "backspace", "volume up", "volume down", "back", "power", "tab",
    "Remote Dpad Up", "Remote Dpad Down", "Remote Dpad Left", "Remote Dpad Right",
    "Remote Dpad Center", "Remote Media Play Pause", "Remote Media Stop", "Remote Media Next",
    "Remote Media Previous", "Remote Media Rewind", "Remote Media Fast Forward",
    "Remote System Navigation Up", "Remote System Navigation Down", "Remote Button A",
    "Remote Button B", "Remote Menu", "TV Input", "TV Input HDMI 1", "TV Input HDMI 2",
    "TV Input HDMI 3",
})
_MAESTRO_PRESS_KEYS_BY_NORMAL: dict[str, str] = {
    " ".join(key.casefold().split()): key for key in _MAESTRO_PRESS_KEYS
}


def _maestro_press_key(key: str) -> str | None:
    """*key*, canonicalized to Maestro's own documented spelling, or `None` if it names no `pressKey` key at all under that normalization."""
    normal = " ".join(key.casefold().split())
    return _MAESTRO_PRESS_KEYS_BY_NORMAL.get(normal)


def _maestro_act_commands(
    act_name: str, locator: tuple[str, str], args: dict[str, Any],
) -> list[str]:
    key, value = locator
    tap = ["- tapOn:", f'    {key}: "{value}"']
    if act_name == "fill":
        return [*tap, f'- inputText: "{args.get("value", "")}"']
    if act_name == "press":
        return [*tap, f'- pressKey: "{args.get("key", "")}"']
    return tap


def _maestro_check_commands(
    check_name: str, locator: tuple[str, str], args: dict[str, Any],
) -> list[str]:
    key, value = locator
    block = ["- assertVisible:", f'    {key}: "{value}"']
    if check_name == "actionable":
        block.append("    enabled: true")
    elif check_name == "inert":
        block.append("    enabled: false")
    text = args.get("text")
    if check_name == "visible" and isinstance(text, str):
        block.append(f'    text: "{text}"')
    return block


def _maestro_act_locator(row: dict[str, Any]) -> tuple[str, str] | None:
    located = (row.get("locates") or {}).get("locator") or {}
    return _maestro_locator(located.get("locators") or {})


def _maestro_check_locator(
    row: dict[str, Any], obligation: dict[str, Any], gaps: list[Gap],
) -> tuple[str, str] | None:
    """The `(id|text, value)` pair a `page`-channel check's `verify:` row addresses."""
    oid = str(obligation["id"])
    located = row.get("locates") or {}
    if not located:
        locator = _maestro_locator(obligation.get("locators", {}))
        if locator is None:
            gaps.append(Gap(oid, "uncompilable-claim",
                             f"`{row.get('name')}` declares no `locator=` and this obligation's "
                             "own node states no `testID=` selector and no `name:` to fall back "
                             "on"))
        return locator
    param = sorted(located)[0]
    target = located[param]
    node_id = str(target.get("node", ""))
    if not node_id:
        gaps.append(Gap(
            oid, "undeclared-check-locator",
            f"`{row.get('name')}` points `{param}=` at "
            f"`{row.get('args', {}).get(param)}`, which names no component or interaction this "
            "book declares — there is nothing to point a driver at, so nothing is emitted"))
        return None
    locator = _maestro_locator(target.get("locators", {}))
    if locator is None:
        gaps.append(Gap(
            oid, "uncompilable-claim",
            f"`{node_id}` is what `{param}=` names, and it declares no `testID=` selector and "
            "no `name:` — so the book says what to look at and not how to address it"))
    return locator


def _is_owed_for_dispatch(obligation: dict[str, Any]) -> bool:
    """Whether an obligation carries something a builder could act on."""
    return bool(obligation.get("checksDeclared")) or obligation.get("kind") == "states"


def _unarranged_state_gap(obligation: dict[str, Any]) -> Gap:
    """The `unarranged-state` gap for one check-less `states:` obligation."""
    state_text = " ".join(str(obligation.get("requirement", "")).split())
    missing = []
    if not obligation.get("checksDeclared"):
        missing.append("no check declared")
    if _arrangement_of([obligation]).unstated:
        missing.append("no fixture arranged")
    return Gap(obligation["id"], "unarranged-state",
               f"carries `states:` ({state_text!r}); " + " and ".join(missing))


def _unarranged_scenario_gap(obligation: dict[str, Any]) -> Gap:
    """The `unarranged-scenario` gap for a claim whose state nothing established."""
    return Gap(obligation["id"], "unarranged-scenario",
               "this claim's scenario arranges nothing before it observes and does not say it "
               "needs nothing — add a `fixture:` naming the arrangement, or "
               "`fixture: none, because ...` saying why the claim holds in whatever world the "
               "scenario finds")


def compile_plan(
    context: dict[str, Any],
    *,
    story: str,
    run_id: str | None = None,
    base_url: str | None = None,
) -> str:
    """Render a `qa_plan.py` skeleton covering every obligation the change owes live proof."""
    result = compile_plan_gaps(context, story=story, run_id=run_id, base_url=base_url)
    assert isinstance(result, Plan), (
        "compile_plan has no way to report a refusal — call compile_plan_gaps directly if "
        "the context might compile to nothing"
    )
    return result.source


def compile_plan_gaps(
    context: dict[str, Any],
    *,
    story: str,
    run_id: str | None = None,
    base_url: str | None = None,
    covered_ids: set[str] | None = None,
) -> Compilation:
    """Compile the book into a plan, or refuse and say why nothing compiled."""
    gaps: list[Gap] = []
    covered_ids = set() if covered_ids is None else covered_ids
    owed = _owed(context)
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
    undetermined_facts = [
        o for o in owed
        if any(row.get("providesUndetermined") for row in o.get("fixturesDeclared") or [])
    ]
    gaps.extend(
        Gap(o["id"], "undetermined-provided-fact",
            "this claim's arrangement provides facts whose source the book does not state: "
            + "; ".join(
                f"`{row['name']}` provides {', '.join(row['providesUndetermined'])} with neither "
                "`from:`/`read:` nor `is:`, or with both"
                for row in o.get("fixturesDeclared") or [] if row.get("providesUndetermined")))
        for o in undetermined_facts
    )
    undetermined_fact_ids = {o["id"] for o in undetermined_facts}
    owed = [o for o in owed if o["id"] not in undetermined_fact_ids]
    refused = [o for o in owed if o.get("checksUnparsed")]
    gaps.extend(
        Gap(o["id"], "unparsed-check-bullet",
            "this claim's check could not be read: "
            + "; ".join(f"`{row['value']}` {row['problem']}" for row in o["checksUnparsed"]))
        for o in refused
    )
    refused_ids = {o["id"] for o in refused}
    owed = [o for o in owed if o["id"] not in refused_ids]
    uncaptured = [o for o in owed if o.get("capturesUnparsed")]
    gaps.extend(
        Gap(o["id"], "unparsed-capture-bullet",
            "this claim's capture could not be read, so it mints no fact for a later `$name` "
            "to resolve against: "
            + "; ".join(f"`capture: {row['value']}` {row['problem']}"
                        for row in o["capturesUnparsed"]))
        for o in uncaptured
    )
    navigation = context.get("navigation", {}) if isinstance(context.get("navigation"), dict) else {}
    cli_binaries = context.get("cliBinaries", {}) if isinstance(context.get("cliBinaries"), dict) else {}
    http_owed: list[dict[str, Any]] = []
    page_owed: list[dict[str, Any]] = []
    cli_owed: list[dict[str, Any]] = []
    mobile_owed: list[dict[str, Any]] = []
    flow_owed: list[dict[str, Any]] = []
    no_verify_owed: list[dict[str, Any]] = []
    carried = [o for o in context.get("obligations", []) if isinstance(o, dict)]
    page_acts, page_acts_refused = _acts_by_node(carried)
    captures_by_node = _captures_by_node(carried)
    for obligation in owed:
        if not _is_owed_for_dispatch(obligation):
            no_verify_owed.append(obligation)
            continue
        surface = str(obligation.get("surface") or "")
        surface_nav = navigation.get(surface, {})
        driver = surface_nav.get("driver")
        node_type = str(obligation.get("nodeType") or "")
        if node_type == "flow":
            flow_owed.append(obligation)
            continue
        target, detail, kind = _dispatch_target(node_type, driver)
        if target == "playwright":
            page_owed.append(obligation)
        elif target == "http":
            http_owed.append(obligation)
        elif target == "cli":
            cli_owed.append(obligation)
        elif target == "maestro":
            mobile_owed.append(obligation)
        else:
            gaps.append(Gap(str(obligation["id"]), kind, detail))
    when_owed = [o for o in no_verify_owed if o.get("kind") == "when"]
    debt: list[dict[str, Any]] = [o for o in no_verify_owed if o.get("kind") != "when"]
    gaps.extend(
        Gap(o["id"], "no-verify-declared", "the book declares no check for this obligation to prove")
        for o in debt
    )
    gaps.extend(
        Gap(o["id"], "precondition-discharged-by-arrangement",
            "this `when:` states a condition under which the node's claims hold, not an "
            "observable claim, so no check is expected to prove it — a `when:` precondition "
            "the compiler tried and failed to arrange is reported separately as "
            "`unarranged-interaction-precondition`")
        for o in when_owed
    )
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

    emitted_targets: set[str] = set()
    captured: set[tuple[str, str]] = set()
    files: dict[str, str] = {}
    node_index = _node_locator_index(context)
    screen_routes = _screen_routes(context)
    for source, obligations in by_source.items():
        gaps.extend(_unarranged_state_gap(o) for o in obligations if not o.get("checksDeclared"))
        declared = [o for o in obligations if o.get("checksDeclared")]
        if not declared:
            continue
        arrangement = _arrangement_of(declared)
        if arrangement.unstated:
            gaps.extend(_unarranged_scenario_gap(o) for o in declared)
            continue
        scenario_covered: set[str] = set()
        body_lines = _scenario_body(declared, gaps, scenario_covered, captured)
        if not scenario_covered:
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
        arranged = arrangement.rows
        if arranged:
            lines.append("    preconditions=[")
            lines.extend(f"        {_lit(row['provides'] or row['name'])},"
                         for row in arranged)
            lines.append("    ],")
        else:
            lines.append("    preconditions=[],")
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
    gaps.extend(_unarranged_state_gap(o) for o in cli_owed if not o.get("checksDeclared"))
    _decline_captures(cli_declared, gaps, captured, because=(
        "the CLI builder does not yet capture a fact out of a tool run"))
    cli_by_source: dict[str, list[dict[str, Any]]] = {}
    for obligation in cli_declared:
        cli_by_source.setdefault(str(obligation.get("source", "book")), []).append(obligation)
    for source, cli_obligations in cli_by_source.items():
        arrangement = _arrangement_of(cli_obligations)
        if arrangement.unstated:
            gaps.extend(_unarranged_scenario_gap(o) for o in cli_obligations)
            continue
        cli_scenario_covered: set[str] = set()
        binary = cli_binaries.get(source)
        body_lines = _cli_scenario_body(cli_obligations, gaps, cli_scenario_covered, binary)
        if not cli_scenario_covered:
            continue
        covered_ids.update(cli_scenario_covered)
        surface = str(cli_obligations[0].get("surface") or "")
        target_var = _target_var(surface, "cli")
        if target_var not in emitted_targets:
            lines.append("")
            lines.append(f"{target_var} = target({_lit(target_var)}, driver={_lit(PYTHON.name)})")
            emitted_targets.add(target_var)
        lines.append("")
        lines.append("")
        lines.append("@scenario(")
        lines.append(f"    target={target_var},")
        lines.append('    mechanism="live",')
        lines.append("    covers=[")
        lines.extend(f"        {_lit(o['id'])}," for o in cli_obligations if o["id"] in cli_scenario_covered)
        lines.append("    ],")
        arranged = arrangement.rows
        if arranged:
            lines.append("    preconditions=[")
            lines.extend(f"        {_lit(row['provides'] or row['name'])}," for row in arranged)
            lines.append("    ],")
        else:
            lines.append("    preconditions=[],")
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

    mobile_declared = [o for o in mobile_owed if o.get("checksDeclared") or o.get("actsDeclared")]
    gaps.extend(_unarranged_state_gap(o) for o in mobile_owed
                if not o.get("checksDeclared") and not o.get("actsDeclared"))
    _decline_captures(mobile_declared, gaps, captured, because=(
        "the mobile builder does not yet capture a fact out of a Maestro flow run"))
    mobile_by_source: dict[str, list[dict[str, Any]]] = {}
    for obligation in mobile_declared:
        mobile_by_source.setdefault(str(obligation.get("source", "book")), []).append(obligation)
    for source, mobile_obligations in mobile_by_source.items():
        arrangement = _arrangement_of(mobile_obligations)
        if arrangement.unstated:
            gaps.extend(_unarranged_scenario_gap(o) for o in mobile_obligations)
            continue
        surface = str(mobile_obligations[0].get("surface") or "")
        bundle_id = navigation.get(surface, {}).get("bundleId") if surface else None
        if bundle_id is None:
            kind, detail = _bundle_id_gap(surface)
            gaps.extend(Gap(str(o["id"]), kind, detail) for o in mobile_obligations)
            continue
        launch_screen = navigation.get(surface, {}).get("launchScreen") if surface else None
        if launch_screen is None:
            kind, detail = _launch_screen_gap(surface)
            gaps.extend(Gap(str(o["id"]), kind, detail) for o in mobile_obligations)
            continue
        mobile_scenario_covered: set[str] = set()
        body_lines = _maestro_scenario_body(
            mobile_obligations, node_index, gaps, mobile_scenario_covered, files, screen_routes,
            bundle_id, launch_screen,
        )
        if not mobile_scenario_covered:
            continue
        covered_ids.update(mobile_scenario_covered)
        target_var = _target_var(surface, "mobile")
        if target_var not in emitted_targets:
            lines.append("")
            lines.append(
                f"{target_var} = target({_lit(target_var)}, driver={_lit(MAESTRO.name)}, "
                f"app_id={_lit(bundle_id)})"
            )
            emitted_targets.add(target_var)
        lines.append("")
        lines.append("")
        lines.append("@scenario(")
        lines.append(f"    target={target_var},")
        lines.append('    mechanism="live",')
        lines.append("    covers=[")
        lines.extend(
            f"        {_lit(o['id'])}," for o in mobile_obligations if o["id"] in mobile_scenario_covered
        )
        lines.append("    ],")
        arranged = arrangement.rows
        if arranged:
            lines.append("    preconditions=[")
            lines.extend(f"        {_lit(row['provides'] or row['name'])}," for row in arranged)
            lines.append("    ],")
        else:
            lines.append("    preconditions=[],")
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

    page_declared = [
        o for o in page_owed if _is_owed_for_dispatch(o)
    ]
    if page_declared:
        if _has_screens(navigation):
            lines.extend(
                _compile_page_scenarios(context, page_declared, gaps, covered_ids, web_urls,
                                        emitted_targets, captured,
                                        acts_by_node=page_acts,
                                        acts_refused=page_acts_refused))
        else:
            gaps.extend(
                Gap(o["id"], "unreachable-screen",
                    "the book's navigation graph has no screen nodes on any surface to walk to")
                for o in page_declared
            )

    lines.extend(_journey_scenarios(context, flow_owed, gaps, covered_ids, navigation,
                                    web_urls, api_urls, emitted_targets, captured, files,
                                    acts_by_node=page_acts, acts_refused=page_acts_refused,
                                    captures_by_node=captures_by_node))

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

    gapped_ids = {gap.obligation_id for gap in gaps}
    dropped = {str(o["id"]) for o in owed} - gapped_ids - covered_ids
    assert not dropped, (
        f"{len(dropped)} owed obligation(s) landed in neither `gaps` nor a compiled scenario: "
        f"{sorted(dropped)!r}"
    )
    unobserved = {gap.obligation_id for gap in gaps if gap.kind not in _ARRANGEMENT_GAPS}
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

    if not emitted_targets:
        return Refusal(gaps)
    return Plan("\n".join(lines).rstrip() + "\n", gaps, files=files)


def deferred_obligations(context: dict[str, Any], *, story: str) -> dict[str, Gap]:
    """Which owed obligations the reference compiler gapped without also covering."""
    covered: set[str] = set()
    result = compile_plan_gaps(context, story=story, covered_ids=covered)
    deferred: dict[str, Gap] = {}
    for gap in result.gaps:
        if gap.obligation_id in covered:
            continue
        deferred.setdefault(gap.obligation_id, gap)
    return deferred


def annotate_deferred_obligations(context: dict[str, Any], *, story: str) -> dict[str, Any]:
    """Stamp each obligation `deferred_obligations` names, in place, with why."""
    deferred = deferred_obligations(context, story=story)
    for obligation in context.get("obligations", []):
        gap = deferred.get(str(obligation.get("id")))
        if gap is not None:
            obligation["deferred"] = {"kind": gap.kind, "detail": gap.detail}
    return context


@dataclass(frozen=True)
class _Arrangement:
    """What one scenario's obligations say about the state their claims are observed in."""

    rows: list[dict[str, Any]]
    stated_none: bool

    @property
    def unstated(self) -> bool:
        """Neither an arrangement nor a stated need for none — nothing may be compiled."""
        return not self.rows and not self.stated_none


def _arrangement_of(obligations: list[dict[str, Any]]) -> _Arrangement:
    """Every fixture the obligations in one scenario declare, in order, arranged once each."""
    rows: list[dict[str, Any]] = []
    for obligation in obligations:
        rows.extend(obligation.get("fixturesDeclared", []))
    return _Arrangement(
        rows=list({(row["name"], tuple(row.get("args", []))): row for row in rows}.values()),
        stated_none=any(o.get("arrangesNothing") for o in obligations),
    )


_ACT_METHODS: dict[str, tuple[str, str | None]] = {
    "fill": ("fill", "value"),
    "click": ("click", None),
    "press": ("press", "key"),
    "select": ("select_option", "option"),
}


def _acts_by_node(
    obligations: list[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], set[str]]:
    """Every node's declared acts in book order, plus the nodes whose act bullets were refused."""
    rows_by_node: dict[str, list[tuple[tuple[int, ...], int, dict[str, Any]]]] = {}
    refused: set[str] = set()
    for obligation in obligations:
        node_id = str(obligation.get("node", ""))
        node_type = str(obligation.get("nodeType", ""))
        kind = str(obligation.get("kind", ""))
        if kind in registry.refusal_keys(node_type):
            continue
        if obligation.get("actsUnparsed"):
            refused.add(node_id)
        position = tuple(int(n) for n in obligation.get("docPosition") or (0, 0))
        for index, row in enumerate(obligation.get("actsDeclared") or []):
            rows_by_node.setdefault(node_id, []).append((position, index, row))
    ordered = {
        node_id: list({row["call"]: row
                       for _, _, row in sorted(rows, key=lambda entry: entry[:2])}.values())
        for node_id, rows in rows_by_node.items()
    }
    return ordered, refused


def _captures_by_node(
    obligations: list[dict[str, Any]],
) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    """Every node's declared captures, each tagged with its owning obligation id, in book order."""
    rows_by_node: dict[str, list[tuple[tuple[int, ...], int, str, dict[str, Any]]]] = {}
    for obligation in obligations:
        node_id = str(obligation.get("node", ""))
        node_type = str(obligation.get("nodeType", ""))
        kind = str(obligation.get("kind", ""))
        if kind in registry.refusal_keys(node_type):
            continue
        oid = str(obligation.get("id", ""))
        position = tuple(int(n) for n in obligation.get("docPosition") or (0, 0))
        for index, row in enumerate(obligation.get("capturesDeclared") or []):
            rows_by_node.setdefault(node_id, []).append((position, index, oid, row))
    return {
        node_id: [(oid, row) for _, _, oid, row in sorted(rows, key=lambda entry: entry[:2])]
        for node_id, rows in rows_by_node.items()
    }


def _performed_lines(
    rows: list[dict[str, Any]], driver: str, gaps: list[Gap], ids: list[str]
) -> tuple[list[str] | None, bool]:
    """The calls that perform *rows* in order, or `None` if any one of them cannot be performed."""
    lines: list[str] = []
    for row in rows:
        spec = acts_mod.ACT_BY_NAME.get(str(row.get("name")))
        if spec is None or driver not in spec.drivers:
            return None, False
        located = (row.get("locates") or {}).get("locator") or {}
        expr = _page_locator_expr(located.get("locators") or {})
        if expr is None:
            return None, False
        if driver == acts_mod.WEB and spec.name == "press":
            book_key = str(row.get("args", {}).get("key", ""))
            if any(ch.isspace() for ch in book_key):
                gaps.extend(Gap(oid, "uncompilable-claim",
                                f"`press` names key {book_key!r}, which contains whitespace "
                                "and so is not a Playwright key")
                            for oid in ids)
                return None, True
        method, value_param = _ACT_METHODS[spec.name]
        argument = "" if value_param is None else _lit(row.get("args", {}).get(value_param, ""))
        lines.append(f"    {expr}.{method}({argument})  # arrange: {row['call']}")
    return lines, False


def _http_body(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The request body *rows* arrange, or `None` if any one of them cannot be sent over HTTP."""
    body: dict[str, Any] = {}
    for row in rows:
        spec = acts_mod.ACT_BY_NAME.get(str(row.get("name")))
        if spec is None or acts_mod.HTTP not in spec.drivers:
            return None
        args = row.get("args", {})
        field, value = args.get("field"), args.get("value")
        if field in body and body[field] != value:
            return None
        body[field] = value
    return body


def _lit_body(fields: dict[str, Any]) -> str:
    """A `json_body=` dict literal, spelled the way `_lit` spells every value inside it."""
    return "{" + ", ".join(f"{json.dumps(k)}: {_lit(v)}" for k, v in fields.items()) + "}"


def _resolved(
    ref: references.Reference,
    produced_facts: set[tuple[str, str]],
    produced_captures: set[str],
) -> bool:
    """Whether *ref* names a fact some earlier producer in the scenario already left behind."""
    if isinstance(ref, references.NodeRef):
        return (ref.node, ref.key) in produced_facts
    return ref.name in produced_captures


def _scenario_body(obligations: list[dict[str, Any]], gaps: list[Gap], covered: set[str],
                   captured: set[tuple[str, str]]) -> list[str]:
    """Compile every obligation's assertion half."""
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
            wants_body = method not in {"GET", "DELETE", "HEAD", "OPTIONS"}
            act_rows = obligation.get("actsDeclared") or []
            fields = None if (not act_rows or obligation.get("actsUnparsed")) else _http_body(act_rows)
            if wants_body and fields is None:
                lines.append("    # TODO(arrange): the book carries no request body")
                lines.append(f"    {name} = None  # TODO(arrange): what this scenario observes")
                gaps.append(Gap(oid, "unarranged-request-body", "the book carries no request body"))
            else:
                path_expr = f"qa.resolve({_lit(path)})" if path_refs else _lit(path)
                expect = f", expect_status={status}" if status is not None else ""
                body_kw = f", json_body={_lit_body(fields)}" if wants_body and fields is not None else ""
                lines.append(f"    {name} = qa.http.{method.lower()}({path_expr}{expect}{body_kw})")
                action_emitted = True
                if "{" in path:
                    lines.append("    # TODO(arrange): the path above still carries a template variable")
                    gaps.append(Gap(oid, "unresolved-precondition", "the path still carries a template variable"))
        else:
            bad_method = _invalid_method(obligation)
            if bad_method is not None:
                lines.append(f"    # TODO(arrange): method {bad_method!r} is not a recognized HTTP verb")
                lines.append(f"    {name} = None  # TODO(arrange): what this scenario observes")
                gaps.append(Gap(oid, "invalid-http-method",
                                 f"`method: {bad_method}` is not a recognized HTTP verb"))
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
                lines.append(
                    f'    qa.capture_field({_lit(cname)}, {name}.json(), {_lit(str(_rooted(source_path)))})'
                )
                produced_captures.add(cname)
                captured.add((oid, cname))
            else:
                because = ("names a UI locator, not a response field, and this builder holds a "
                           "response")
                if source_path.startswith("$"):
                    because = "has no observed response here to read the field off of"
                lines.append(
                    f"    # TODO(arrange): capture {cname!r} from {source_path!r} {because}")
                _decline_captures([obligation], gaps, captured, because=because)

        if not action_emitted:
            continue

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
    """What the compiled call is handed, the arrangement note it still needs, and why."""
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
        return observed, "", ""
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
    *,
    acts_by_node: dict[str, list[dict[str, Any]]],
    acts_refused: set[str],
) -> list[str]:
    """Compile every screen's `visible(...)` bullets, partitioned per Amendment 3."""
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
            gaps.extend(Gap(oid, "uncompilable-claim",
                             f"surface {surface!r} has no `navigation` data to address this screen by")
                        for oid in ids)
            continue
        if source in set(nav.get("unreachable", [])):
            gaps.extend(Gap(oid, "unreachable-screen",
                             f"{surface}'s navigation cannot reach this screen; no scenario compiled")
                        for oid in ids)
            continue
        hops = nav.get("routes", {}).get(source)
        if hops is None:
            gaps.extend(Gap(oid, "uncompilable-claim", "no route computed for this screen")
                        for oid in ids)
            continue
        raw_root_path = nav.get("rootPath")
        if raw_root_path is None:
            gaps.extend(Gap(oid, "uncompilable-claim",
                             f"surface {surface!r} states no root path a page scenario can open from")
                        for oid in ids)
            continue
        root_path = str(raw_root_path)
        if source in set(nav.get("undeclared", [])):
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
            state_obs = [o for o in obs if o.get("kind") == "states"]
            rest = [o for o in obs if o.get("kind") != "states"]
            for obligation in state_obs:
                if obligation.get("checksDeclared") and _arrangement_of([obligation]).rows:
                    state_name = f"{_slug(source)}_{_node_slug(node_id)}_{obligation['id'].rsplit(':', 1)[-1]}"
                    bucket.extend(_arrival_scenario(root_path, source, hops, node_index,
                                                     {node_id: [obligation]}, gaps, covered,
                                                     captured, name=state_name, target_var=target_var,
                                                     screen_routes=screen_routes))
                else:
                    gaps.append(_unarranged_state_gap(obligation))
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
                                                 screen_routes=screen_routes,
                                                 node_acts=acts_by_node.get(node_id, []),
                                                 node_acts_refused=node_id in acts_refused))

    lines: list[str] = []
    for surface in sorted(scenario_lines_by_surface):
        scenario_lines = scenario_lines_by_surface[surface]
        if not scenario_lines:
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
    """One `.click()` per hop the book's own navigation-derivation logic found (Correction 2')."""
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
    """The concrete operand a `visible(...)` assertion is handed — never a page/body fallback."""
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
    """Where the driver is pointed for one `verify:` row."""
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
    """The screen document a check observes — the one its `locator=` names, or its own."""
    for param in sorted(row.get("locates") or {}):
        node_id = str((row["locates"][param] or {}).get("node", ""))
        if node_id:
            return node_id.split("#", 1)[0]
    return str(obligation.get("source", ""))


def _why_unmatchable_screen_name(route: str) -> str:
    """Why *route* is not a screen name a Maestro flow's own report could be compared against."""
    text = route.strip()
    if not text:
        return "the book states no single `route:` for it"
    return f"its `route:` (`{text}`) is not a navigator screen name a Maestro run could match"


def _vettable(
    documents: list[str],
    screen_routes: dict[str, str],
    ids: list[str],
    gaps: list[Gap],
    *,
    mobile: bool = False,
) -> list[str]:
    """*documents* a vet can establish as its subject, with a gap for each one it cannot."""
    keep: list[str] = []
    for document in documents:
        route = screen_routes.get(document, "")
        if is_screen_name_shaped(route.strip()) if mobile else literal_route(route):
            keep.append(document)
            continue
        why = _why_unmatchable_screen_name(route) if mobile else why_unreadable(route)
        gaps.extend(Gap(oid, "unidentifiable-screen",
                        f"this scenario ends on {document}, and {why} — so nothing can say the "
                        "page it photographed is that screen, and its placement verdicts are "
                        "withheld rather than reported about an unestablished subject")
                    for oid in ids)
    return keep


_WINDOW_VAR = "exchanges"


def _observed_exchange(obligation: dict[str, Any]) -> tuple[str | None, str] | None:
    """Which HTTP exchange this obligation's response/body checks are about, if the book says."""
    pairs = {
        (row["args"].get("method"), str(row["args"]["path"]))
        for row in obligation.get("checksDeclared", [])
        if row.get("name") == "http_status" and isinstance(row.get("args"), dict)
        and isinstance(row["args"].get("path"), str)
    }
    if len(pairs) != 1:
        return None
    method, path = next(iter(pairs))
    return (str(method) if isinstance(method, str) else None, path)


def _exchange_operand(
    row: dict[str, Any], obligation: dict[str, Any], exchange: tuple[str | None, str] | None,
    channel: str, gaps: list[Gap],
) -> str | None:
    """Where a page scenario is pointed for one response- or body-observing `verify:` row."""
    if exchange is None:
        gaps.append(Gap(
            obligation["id"], "uncompilable-claim",
            f"`{row.get('name')}` observes an HTTP {channel}, which the playwright driver "
            "can see — but a browser makes many requests and nothing in this obligation "
            "says which one, uniquely, by method and path. Declare the exchange with an "
            "`http_status(method=\"…\", path=\"…\")` bullet on the same claim; two different "
            "(method, path) pairs on one obligation are two claims, not one"))
        return None
    method, path = exchange
    args = f"{_lit(path)}, method={_lit(method)}" if method else _lit(path)
    selection = f"{_WINDOW_VAR}.response_for({args})"
    return f"{selection}.json()" if channel == "body" else selection


def _needs_window(lines: list[str]) -> bool:
    """Whether any emitted assertion reads the observation window, so it has to be opened."""
    return any(f"{_WINDOW_VAR}." in line for line in lines)


def _page_assertions(
    obligation: dict[str, Any], gaps: list[Gap]
) -> tuple[list[str], list[str]] | None:
    """One obligation's assertions and the screens they observe, or `None` if it is not whole."""
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
    arranged = _arrangement_of(obligations).rows
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
        return []
    if _needs_window(assertions):
        body.insert(goto_index, f"    {_WINDOW_VAR} = qa.window()")
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
    node_acts: list[dict[str, Any]],
    node_acts_refused: bool,
) -> list[str]:
    """Arrive, trigger the interaction, then assert what the book says holds afterward."""
    _decline_captures(obligations, gaps, captured, because=(
        "the trigger is performed here, but this builder has no declared way to read a value "
        "back out of the page and bind it under that name"))
    locators = obligations[0].get("locators", {})
    on_value = next(iter(locators.get("on", [])), None)
    trigger_value = next(iter(locators.get("trigger", [])), "")
    does_value = next(iter(locators.get("does", [])), "")
    when_value = next(iter(locators.get("when", [])), "")
    on_href = next(iter(extract_refs(on_value or "").links), (None, None))[1]
    on_label = (on_href or on_value or "").lstrip("#") or on_value
    on_node_id = f"{source}#{on_href.lstrip('#')}" if on_href else (f"{source}#{on_value}" if on_value else "")
    ids = sorted(o["id"] for o in obligations)
    if obligations[0].get("extendsUnresolved"):
        gaps.extend(Gap(oid, "unresolved-extends",
                         "this arm's `extends:` target is missing or not the same node type, "
                         "so its control identity could not be inherited from the base case")
                    for oid in ids)
    arranged = _arrangement_of(obligations).rows
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
    performed, _ = (
        _performed_lines(node_acts, acts_mod.WEB, gaps, ids) if node_acts else (None, False)
    )
    when_arranged = performed is not None and not node_acts_refused
    if performed:
        body.extend(performed)
    on_expr = _page_locator_expr(node_index.get(on_node_id, {}))
    on_resolved = on_expr is not None
    if on_expr is None:
        body.append(f"    # TODO(arrange): no locator declared for {on_label!r}")
        gaps.extend(Gap(oid, "unresolved-precondition",
                         f"no locator declared for `on:` component {on_label!r}")
                    for oid in ids)
        on_expr = "qa.page.locator('body')"
    action_index = len(body)
    body.append(f"    {on_expr}.click()  # trigger: {_trailing_comment(trigger_value)}")
    if does_value:
        body.extend(_prose_comment(does_value, label="does: "))
    if on_resolved and when_value and not when_arranged:
        gaps.extend(Gap(oid, "unarranged-interaction-precondition",
                         f"`when:` states a precondition ({when_value!r}) this scenario does "
                         "not arrange, so its assertions would observe an unestablished state")
                    for oid in ids)
    elif on_resolved:
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
        if when_value and not when_arranged:
            assertions.append(f"    # TODO(arrange): {obligation['id']} declares an "
                               "observation this scenario cannot make — `when:` states a "
                               "precondition nothing this scenario performs arranges")
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
        return []
    if _needs_window(assertions):
        body.insert(action_index, f"    {_WINDOW_VAR} = qa.window()")
    covered.update(scenario_covered)
    precondition_rows = [_lit(row["provides"] or row["name"]) for row in arranged]
    if when_arranged and when_value:
        precondition_rows.append(_lit(when_value))
    if precondition_rows:
        precondition_lines = [
            "    preconditions=[",
            *(f"        {row}," for row in precondition_rows),
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
    files: dict[str, str],
    *,
    acts_by_node: dict[str, list[dict[str, Any]]],
    acts_refused: set[str],
    captures_by_node: dict[str, list[tuple[str, dict[str, Any]]]],
) -> list[str]:
    """One scenario per flow: walk its `steps:` in order, then observe what the walk left."""
    by_source: dict[str, list[dict[str, Any]]] = {}
    for obligation in flow_owed:
        by_source.setdefault(str(obligation.get("source", "book")), []).append(obligation)
    node_index = _node_locator_index(context)
    screen_routes = _screen_routes(context)
    lines: list[str] = []
    for source, obligations in sorted(by_source.items()):
        ids = sorted(str(o["id"]) for o in obligations)
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
            step_nav = navigation.get(step_surface, {})
            step_target, why, why_kind = _dispatch_target(
                str(step.get("nodeType") or ""), step_nav.get("driver")
            )
            if step_target is None or step_target not in _BUILT_TARGETS:
                detail = why
                step_kind = why_kind
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
        url: str | None = ""
        if journey_target == "http":
            kind, driver_name = "api", PYTHON.name
            url = api_urls.get(surface) or nav.get("entryUrl")
        elif journey_target == "playwright":
            kind, driver_name = "web", PLAYWRIGHT.name
            url = web_urls.get(surface) or nav.get("entryUrl")
        elif journey_target == "maestro":
            kind, driver_name = "mobile", MAESTRO.name
        else:
            gaps.extend(Gap(oid, "needs-target-backend",
                            f"D1's table names {journey_target!r} for every step of this "
                            "journey, and this compiler builds no journey path for it")
                        for oid in ids)
            continue
        if journey_target != "maestro" and url is None:
            kind, detail = _entry_url_gap(surface)
            gaps.extend(Gap(oid, kind, detail) for oid in ids)
            continue
        bundle_id = nav.get("bundleId")
        if journey_target == "maestro" and bundle_id is None:
            kind, detail = _bundle_id_gap(surface)
            gaps.extend(Gap(oid, kind, detail) for oid in ids)
            continue
        launch_screen = nav.get("launchScreen")
        if journey_target == "maestro" and launch_screen is None:
            kind, detail = _launch_screen_gap(surface)
            gaps.extend(Gap(oid, kind, detail) for oid in ids)
            continue
        arrangement = _arrangement_of(obligations)
        arranged = arrangement.rows
        if arrangement.unstated:
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
                                 captured, acts_by_node=acts_by_node, acts_refused=acts_refused,
                                 captures_by_node=captures_by_node)
        elif journey_target == "maestro":
            assert bundle_id is not None, (
                "the `journey_target == \"maestro\" and bundle_id is None` branch above "
                "already gapped and skipped this journey"
            )
            assert launch_screen is not None, (
                "the `journey_target == \"maestro\" and launch_screen is None` branch above "
                "already gapped and skipped this journey"
            )
            body = _maestro_journey(steps, node_index, obligations, ids, gaps, scenario_covered,
                                    files, screen_routes, bundle_id, launch_screen)
        else:
            body = _web_journey(steps, node_index, obligations, ids, gaps, scenario_covered,
                                captured, nav, screen_routes,
                                acts_by_node=acts_by_node, acts_refused=acts_refused)
        if not scenario_covered:
            continue
        covered.update(scenario_covered)
        precondition_lines = [
            "    preconditions=[",
            *(f"        {_lit(row['provides'] or row['name'])}," for row in arranged),
            "    ],",
        ]
        target_var = _target_var(surface, kind)
        if target_var not in emitted_targets:
            if journey_target == "maestro":
                lines.extend([
                    "",
                    f"{target_var} = target({_lit(target_var)}, driver={_lit(driver_name)}, "
                    f"app_id={_lit(bundle_id)})",
                ])
            else:
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
    *,
    acts_by_node: dict[str, list[dict[str, Any]]],
    acts_refused: set[str],
    captures_by_node: dict[str, list[tuple[str, dict[str, Any]]]],
) -> list[str]:
    """Perform each `endpoint` step as a request, then assert the flow's claims on the last one."""
    _decline_captures(obligations, gaps, captured, because=(
        "a journey performs its steps and asserts the flow's own claim; a capture declared on "
        "the flow node itself names no response this scenario ever holds"))
    lines: list[str] = []
    observed = ""
    last_path = ""
    produced_captures: set[str] = set()
    for index, step in enumerate(steps, start=1):
        ref = str(step.get("ref", ""))
        remaining_refs = [str(s.get("ref", "")) for s in steps[index - 1:]]
        step_locators = node_index.get(ref, {})
        route = _route({"locators": step_locators})
        if route is None:
            bad_method = _invalid_method({"locators": step_locators})
            if bad_method is not None:
                gaps.extend(Gap(oid, "invalid-http-method",
                                f"step {index} ({step.get('href')!r}) states `method: {bad_method}`, "
                                "not a recognized HTTP verb")
                            for oid in ids)
            else:
                gaps.extend(Gap(oid, "uncompilable-claim",
                                f"step {index} ({step.get('href')!r}) states no `method:`/`path:` "
                                "for this journey to perform")
                            for oid in ids)
            _decline_captures_by_node(remaining_refs, captures_by_node, gaps, captured, because=(
                "this journey could not compile the node this step names, so it holds no "
                "response to capture the field from"))
            return []
        method, path = route
        wants_body = method not in {"GET", "DELETE", "HEAD", "OPTIONS"}
        body_kw = ""
        if wants_body:
            node_rows = acts_by_node.get(ref, [])
            fields = None if (ref in acts_refused or not node_rows) else _http_body(node_rows)
            if fields is None:
                gaps.extend(Gap(oid, "unarranged-request-body",
                                f"step {index} is a {method} and the book carries no request body")
                            for oid in ids)
                _decline_captures_by_node(remaining_refs, captures_by_node, gaps, captured,
                                          because=("this journey could not build this step's "
                                                    "request body, so it holds no response to "
                                                    "capture the field from"))
                return []
            body_kw = f", json_body={_lit_body(fields)}"
        observed = f"observed_{index}"
        lines.append(f"    {observed} = qa.http.{method.lower()}({_lit(path)}{body_kw})")
        if "{" in path:
            lines.append("    # TODO(arrange): the path above still carries a template variable")
            gaps.extend(Gap(oid, "unresolved-precondition",
                            f"step {index}'s path still carries a template variable")
                        for oid in ids)
        last_path = path
        for cap_oid, capture in captures_by_node.get(ref, []):
            cname = capture.get("name")
            if not cname:
                continue
            source_path = str(capture.get("from", ""))
            if source_path.startswith("$"):
                lines.append(
                    f'    qa.capture_field({_lit(cname)}, {observed}.json(), '
                    f'{_lit(str(_rooted(source_path)))})'
                )
                produced_captures.add(str(cname))
                captured.add((cap_oid, str(cname)))
            else:
                because = ("names a UI locator, not a response field, and this builder holds a "
                           "response")
                lines.append(
                    f"    # TODO(arrange): capture {cname!r} from {source_path!r} {because}")
                captured.add((cap_oid, str(cname)))
                gaps.append(Gap(
                    cap_oid, "uncaptured-declaration",
                    f"capture {str(cname)!r} from {source_path!r} is declared on this node and "
                    f"{because}",
                ))
    for obligation in obligations:
        oid = str(obligation["id"])
        assertions: list[str] = []
        whole = True
        for row in obligation.get("checksDeclared", []):
            named = row.get("args", {}).get("path")
            if (
                isinstance(named, str)
                and named != last_path
                and _observes(row.get("name")) == "response"
            ):
                note = (f"`{row.get('name')}` names `path={named}`, and this journey ended on "
                        f"`{last_path}` — a journey's claim is about the world its last step "
                        "left, so there is no response here this check is about")
                lines.append(f"    # TODO(arrange): {note}")
                gaps.append(Gap(oid, "uncompilable-claim", note))
                whole = False
                continue
            row_resolved = True
            for ref_found in references.find_references(json.dumps(row.get("args", {}))):
                if isinstance(ref_found, references.CaptureRef) and not _resolved(
                    ref_found, set(), produced_captures
                ):
                    gaps.append(Gap(oid, "unresolved-precondition",
                                    f"a verify argument references {ref_found!r}, not resolvable "
                                    "without running the plan"))
                    row_resolved = False
            if not row_resolved:
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
    *,
    acts_by_node: dict[str, list[dict[str, Any]]],
    acts_refused: set[str],
) -> list[str]:
    """Arrive where the journey starts, click every step in order, then observe the end."""
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
    raw_root_path = nav.get("rootPath")
    if raw_root_path is None:
        gaps.extend(Gap(oid, "uncompilable-claim",
                        "this surface states no root path a journey can open from")
                    for oid in ids)
        return []
    lines: list[str] = [f"    qa.goto({_lit(str(raw_root_path))})"]
    lines.extend(_walk_hops(hops, node_index, gaps, ids))
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
        performed, performed_gap_minted = _performed_lines(
            acts_by_node.get(ref, []), acts_mod.WEB, gaps, ids
        )
        if performed is None or ref in acts_refused:
            if not performed_gap_minted:
                gaps.extend(Gap(oid, "uncompilable-claim",
                                f"step {index} declares an arrangement this journey cannot make — "
                                "an act with no driver or no addressable subject, or a bullet the "
                                "act parser refused; every step after it would run in a world this "
                                "journey never reached")
                            for oid in ids)
            return []
        lines.extend(performed)
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


def _maestro_journey(
    steps: list[dict[str, Any]],
    node_index: dict[str, dict[str, list[str]]],
    obligations: list[dict[str, Any]],
    ids: list[str],
    gaps: list[Gap],
    covered: set[str],
    files: dict[str, str],
    screen_routes: dict[str, str],
    bundle_id: str,
    launch_screen: str,
) -> list[str]:
    """Walk a flow's `interaction` steps as Maestro `tapOn` commands, then assert the flow's own claims in the same flow file."""
    commands: list[str] = []
    if steps:
        first_page = str(steps[0].get("ref", "")).split("#")[0]
        if first_page != launch_screen:
            gaps.extend(Gap(oid, "unreachable-from-launch",
                            f"a cold `launchApp` opens on {launch_screen!r}, not "
                            f"{first_page!r}, and nothing before this journey's first step "
                            "gets from the one to the other")
                        for oid in ids)
            return []
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
        on_href = next(iter(extract_refs(on_value or "").links), (None, None))[1]
        on_label = (on_href or on_value or "").lstrip("#") or on_value
        on_node_id = f"{ref.split('#')[0]}#{on_href.lstrip('#')}" if on_href else ""
        locator = _maestro_locator(node_index.get(on_node_id, {}))
        if locator is None:
            gaps.extend(Gap(oid, "uncompilable-claim",
                            f"step {index} acts on {on_label!r}, which declares no `testID=` "
                            "selector and no `name:` to address it by; every step after it "
                            "would run in a world this journey never reached")
                        for oid in ids)
            return []
        commands.extend(_maestro_act_commands("click", locator, {}))
    assertions: list[str] = []
    python_lines: list[str] = []
    page_oids: list[str] = []
    documents: list[str] = []
    result_name = "journey_result"
    for obligation in obligations:
        oid = str(obligation["id"])
        for row in obligation.get("checksDeclared", []):
            channel = _observes(str(row.get("name")))
            if channel == "subject":
                operand, note, kind = _operand(str(row["name"]), result_name)
                if note:
                    gaps.append(Gap(oid, kind, note))
                    continue
                python_lines.append(
                    f"    qa.verify({_lit(row['name'])}, {operand}"
                    f"{_kwargs(row.get('args', {}))}, covers=[{_lit(oid)}])"
                )
                covered.add(oid)
                continue
            if channel != "page":
                gaps.append(_unobservable_gap(oid, row.get("name"), MAESTRO))
                continue
            locator = _maestro_check_locator(row, obligation, gaps)
            if locator is None:
                continue
            assertions.extend(
                _maestro_check_commands(str(row["name"]), locator, row.get("args", {}))
            )
            document = _check_document(row, obligation)
            if document and document not in documents:
                documents.append(document)
            if oid not in page_oids:
                page_oids.append(oid)
            python_lines.append(
                f"    qa.verify({_lit(row['name'])}, {result_name}.exit_code == 0"
                f"{_kwargs(row.get('args', {}))}, covers=[{_lit(oid)}])"
            )
            covered.add(oid)
    if not covered:
        return []
    flow_path = f"maestro/{_slug('-'.join(ids))}.yaml"
    files[flow_path] = _maestro_flow_yaml([*commands, *assertions], bundle_id)
    lines = [f"    {result_name} = qa.maestro.run(qa.spec_dir / {_lit(flow_path)})", *python_lines]
    if page_oids:
        lines.extend(
            f"    qa.vet({_lit(document)})"
            for document in _vettable(documents, screen_routes, page_oids, gaps, mobile=True)
        )
    return lines


def cmd_compile_plan(
    spec_dir: Path,
    *,
    out: Path | None = None,
    story: str = "",
    run_id: str | None = None,
    base_url: str | None = None,
) -> QaOutcome:
    """Compile `spec_dir/qa-okf-context.json` into a plan skeleton."""
    context_file = spec_dir / "qa-okf-context.json"
    try:
        packet = json.loads(context_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return QaOutcome(ok=False, message=f"error: {exc}", status="invalid",
                         data={"status": "invalid", "problems": [str(exc)]})

    story_name = story or str(packet.get("story", "") or "story")
    result = compile_plan_gaps(packet, story=story_name, run_id=run_id, base_url=base_url)

    owed = _owed(packet)
    declared = [o for o in owed if o.get("checksDeclared")]
    owed_ids = [str(o["id"]) for o in owed]
    no_verify_ids = {gap.obligation_id for gap in result.gaps if gap.kind == "no-verify-declared"}
    data: dict[str, Any] = {
        "owed": len(owed),
        "declared": len(declared),
        "debt": [oid for oid in owed_ids if oid in no_verify_ids],
        "gaps": [
            {"severity": "error", "code": gap.kind, "message": gap.detail, "ref": gap.obligation_id}
            for gap in result.gaps
        ],
    }

    if isinstance(result, Refusal):
        by_kind: dict[str, int] = {}
        for gap in result.gaps:
            by_kind[gap.kind] = by_kind.get(gap.kind, 0) + 1
        problems = [f"{kind}: {count}" for kind, count in sorted(by_kind.items())]
        return QaOutcome(
            ok=False,
            message=(
                "no scenario compiled — nothing this book states could be turned into "
                f"executable evidence ({len(result.gaps)} gap(s))"
            ),
            status="invalid",
            data={**data, "problems": problems},
        )
    source = result.source

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
    for relpath, content in result.files.items():
        aux = out.parent / relpath
        aux.parent.mkdir(parents=True, exist_ok=True)
        aux.write_text(content, encoding="utf-8")
    return QaOutcome(
        ok=True,
        message=(f"Compiled {len(declared)} of {len(owed)} owed obligations into {out}.\n"
                 f"{len(data['debt'])} owed obligation(s) declare no `verify:` and are listed "
                 f"as book debt in the file."),
        status="passed",
        data=data,
    )
