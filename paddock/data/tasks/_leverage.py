"""How far a trial's QA plan used what the book documents, read statically from the plan, the book and the run log."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


BLANK = "–"

LEVERAGE_KEYS = ("entry", "deep_links", "roles", "obligations", "journeys", "sensitivity")

LEVERAGE_LABELS = {
    "entry": "entry",
    "deep_links": "deep-links",
    "roles": "roles",
    "obligations": "obligations",
    "journeys": "journeys",
    "sensitivity": "sensitivity",
}

PASSING_STATUS = "covered"


def route_matches(route: str, url: str) -> bool:
    """Whether a planned `goto` lands on a route the book documents."""
    try:
        from ostler.qa.plan import _route_matches
    except ImportError:
        planned = [part for part in urlsplit(url).path.strip("/").split("/") if part]
        documented = [part for part in urlsplit(route).path.strip("/").split("/") if part]
        if len(planned) != len(documented):
            return False
        return all(
            part.startswith((":", "{")) or other.startswith((":", "{")) or part == other
            for part, other in zip(planned, documented, strict=True)
        )
    return _route_matches(route, url)


def _values(value: Any) -> list[str]:
    if value is None:
        return []
    return [str(item) for item in (value if isinstance(value, list) else [value])]


def _route_of(node: dict[str, Any]) -> str:
    """The route a screen node documents, or `""`."""
    for value in _values(node.get("bullets", {}).get("route")):
        token = value.strip().split()[0].strip("`") if value.strip() else ""
        if token.startswith("/"):
            return token
    return ""


def _literal(node: ast.expr | None) -> Any:
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return None


def _called(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    return func.id if isinstance(func, ast.Name) else ""


def plan_scenarios(source: str) -> dict[str, dict[str, Any]]:
    """`{scenario id: {"covers": [...], "actions": [...]}}`, read statically from a `qa_plan.py`."""
    from ostler.qa.harness_host import load_harness_module

    actions = load_harness_module("ostler_qa").extract_locators(source)
    found: dict[str, dict[str, Any]] = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or _called(decorator) != "scenario":
                continue
            keywords = {kw.arg: kw.value for kw in decorator.keywords if kw.arg}
            given = _literal(keywords.get("id"))
            covers = _literal(keywords.get("covers"))
            found[given if isinstance(given, str) else node.name.replace("_", "-")] = {
                "covers": [str(item) for item in covers] if isinstance(covers, list) else [],
                "actions": actions.get(node.name, []),
            }
    return found


def _gotos(scenario: dict[str, Any]) -> list[str]:
    return [
        str(action["url"])
        for action in scenario["actions"]
        if isinstance(action, dict) and action.get("do") == "goto" and action.get("url")
    ]


def _locators(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        action["locator"]
        for action in scenario["actions"]
        if isinstance(action, dict) and isinstance(action.get("locator"), dict)
    ]


def required_flows(packet: dict[str, Any]) -> list[str]:
    """The flow nodes this story owes live evidence for."""
    return sorted({
        str(obligation["node"])
        for obligation in packet.get("obligations", []) or []
        if isinstance(obligation, dict)
        and obligation.get("kind") == "journey"
        and obligation.get("required", True)
        and obligation.get("node")
    })


def flow_starts(book: dict[str, Any]) -> dict[str, str]:
    """`{flow node id: the route its `start:` screen documents}`."""
    routes = {str(node["id"]): _route_of(node) for node in book.get("nodes", []) or []}
    starts: dict[str, str] = {}
    for edge in book.get("edges", []) or []:
        if edge.get("via") == "start" and routes.get(str(edge.get("to"))):
            starts.setdefault(str(edge["from"]), routes[str(edge["to"])])
    return starts


def entry_routes(book: dict[str, Any]) -> set[str]:
    """Every route a user may legitimately arrive at from outside in-app navigation."""
    routes = {
        _route_of(node)
        for node in book.get("nodes", []) or []
        if node.get("bullets", {}).get("entry") and _route_of(node)
    }
    return routes | set(flow_starts(book).values())


def documented_routes(book: dict[str, Any]) -> set[str]:
    return {route for node in book.get("nodes", []) or [] if (route := _route_of(node))}


def book_sensitivity(repo: Path) -> list[int] | None:
    """`[claims observed by a check that could fail, claims the book mints]`, or None."""
    try:
        from ostler import model
        from ostler.qa import sensitivity as sensitivity_mod
    except ImportError:
        return None
    try:
        rows = sensitivity_mod.report(model.load(repo))
    except Exception:  # noqa: BLE001 - a book that will not load scores `–`, not a crash
        return None
    return [sum(1 for row in rows if row.status == "sensitive"), len(rows)] if rows else None


def leverage_from(
    book: dict[str, Any] | None,
    packet: dict[str, Any] | None,
    plan_source: str | None,
    run_log: list[dict[str, Any]] | None,
    statuses: dict[str, str] | None,
    sensitivity: list[int] | None = None,
) -> dict[str, Any]:
    """The six leverage metrics, each a `[n, of]` pair, an int, or None when incomputable."""
    scenarios = plan_scenarios(plan_source) if plan_source else {}
    if run_log is not None:
        started = {
            str(record.get("scenario", ""))
            for record in run_log
            if record.get("kind") == "scenario_start"
        }
        scenarios = {name: data for name, data in scenarios.items() if name in started}

    flows = required_flows(packet) if packet else []
    starts = flow_starts(book) if book else {}
    covering: dict[str, list[dict[str, Any]]] = {flow: [] for flow in flows}
    for data in scenarios.values():
        for flow in flows:
            if any(cover.startswith(f"okf:{flow}:") for cover in data["covers"]):
                covering[flow].append(data)

    entry: list[int] | None = None
    if flows and any(starts.get(flow) for flow in flows):
        entry = [
            sum(
                1
                for flow in flows
                if (route := starts.get(flow))
                and any(
                    (gotos := _gotos(data)) and route_matches(route, gotos[0])
                    for data in covering[flow]
                )
            ),
            len(flows),
        ]

    deep_links: int | None = None
    if book and scenarios:
        elsewhere = documented_routes(book)
        arrivals = entry_routes(book)
        deep_links = sum(
            1
            for data in scenarios.values()
            for url in _gotos(data)[1:]
            if any(route_matches(route, url) for route in elsewhere)
            and not any(route_matches(route, url) for route in arrivals)
        )

    roles: list[int] | None = None
    uses = [locator for data in scenarios.values() for locator in _locators(data)]
    if uses:
        roles = [sum(1 for locator in uses if "role" in locator or "css" in locator), len(uses)]

    obligations = (
        [sum(1 for status in statuses.values() if status == PASSING_STATUS), len(statuses)]
        if statuses
        else None
    )

    journeys = (
        [
            sum(1 for flow in flows if statuses.get(f"okf:{flow}:end-state") == PASSING_STATUS),
            len(flows),
        ]
        if statuses and flows
        else None
    )

    return {
        "entry": entry,
        "deep_links": deep_links,
        "roles": roles,
        "obligations": obligations,
        "journeys": journeys,
        "sensitivity": sensitivity,
    }


def read_ndjson(path: Path) -> list[dict[str, Any]] | None:
    if not path.is_file():
        return None
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, dict) else None


def load_book(repo: Path) -> dict[str, Any] | None:
    """The feature graph as `{"nodes": [...], "edges": [...]}`, or None if it will not load."""
    try:
        from ostler import graph as graph_mod
        from ostler import model
    except ImportError:
        return None
    try:
        return graph_mod.build(model.load(repo))
    except Exception:  # noqa: BLE001 - a book that will not load scores `–`, not a crash
        return None


def leverage(witness: Path, story: str, statuses: dict[str, str] | None) -> dict[str, Any]:
    """Score one trial's artifacts."""
    spec = witness / "docs" / "specs" / story
    plan_file = spec / "qa_plan.py"
    return leverage_from(
        load_book(witness),
        read_json(spec / "qa-okf-context.json"),
        plan_file.read_text(encoding="utf-8") if plan_file.is_file() else None,
        read_ndjson(spec / "qa" / "qa-run.ndjson"),
        statuses,
        book_sensitivity(witness),
    )


BOOK_LEVEL_KEYS = frozenset({"sensitivity"})


def pool_leverage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Sum the metrics across trials, keeping a metric None when no trial could compute it."""
    pooled: dict[str, Any] = dict.fromkeys(LEVERAGE_KEYS)
    for row in rows:
        metrics = row.get("leverage") or {}
        for key in LEVERAGE_KEYS:
            value = metrics.get(key)
            if value is None:
                continue
            current = pooled[key]
            if isinstance(value, list):
                pair = [int(value[0]), int(value[1])]
                if current is None:
                    pooled[key] = pair
                elif key in BOOK_LEVEL_KEYS:
                    pooled[key] = max(current, pair, key=lambda seen: seen[1])
                else:
                    pooled[key] = [current[0] + pair[0], current[1] + pair[1]]
            else:
                pooled[key] = int(value) + (current or 0)
    return pooled


def leverage_line(metrics: dict[str, Any], keys: tuple[str, ...] = LEVERAGE_KEYS) -> str:
    """Print the metrics the fixture declared it can own, and say how many it left out."""
    parts = []
    for key in keys:
        value = metrics.get(key)
        if value is None:
            shown = BLANK
        elif isinstance(value, list):
            shown = f"{value[0]}/{value[1]}"
        else:
            shown = str(value)
        parts.append(f"{LEVERAGE_LABELS[key]} {shown}")
    line = "leverage: " + "  ".join(parts)
    if len(keys) < len(LEVERAGE_KEYS):
        line += f"  ({len(keys)} of {len(LEVERAGE_KEYS)} metrics)"
    return line
