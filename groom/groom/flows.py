from __future__ import annotations

from collections import defaultdict
from typing import Any

UNFINISHED = "Unfinished flow or state"


def _is_state(span: dict[str, Any]) -> bool:
    return span["attrs"].get("workhorse.span_kind") == "state"


def _is_turn(span: dict[str, Any]) -> bool:
    return span["name"] == "agent_turn"


def _is_node(span: dict[str, Any]) -> bool:
    return (
        not span["attrs"].get("workhorse.span_kind")
        and not _is_turn(span)
        and not span["name"].startswith("run:")
    )


def _depth(span: dict[str, Any]) -> int | None:
    depth = span["attrs"].get("workhorse.depth")
    return depth if isinstance(depth, int) else None


def _seconds(span: dict[str, Any]) -> float:
    millis = span.get("profile_duration_ms")
    if millis is not None:
        return float(millis) / 1000.0
    return max(0.0, span["end_ts"] - span["start_ts"])


class _Node:
    def __init__(self) -> None:
        self.span_ids: set[str] = set()
        self.node_seconds = 0.0
        self.step_seconds: list[float] = []
        self.turns: list[dict[str, Any]] = []


class _State:
    def __init__(self) -> None:
        self.span_ids: set[str] = set()
        self.nodes: dict[str, _Node] = defaultdict(_Node)


class _Flow:
    def __init__(self, kind: str, name: str, title: str = "") -> None:
        self.kind = kind
        self.name = name
        self.title = title
        self.span_ids: set[str] = set()
        self.direct: dict[str, _Node] = defaultdict(_Node)
        self.states: dict[str, _State] = defaultdict(_State)


def _node_row(name: str, acc: _Node) -> dict[str, Any]:
    turns = acc.turns
    costs = [t["profile_cost_usd"] for t in turns if t["profile_cost_usd"] is not None]
    groups = {(t["trace_id"], t["parent_id"] or t["span_id"]) for t in turns}
    orphan_groups = {
        group for group in groups if group[1] not in acc.span_ids
    }
    visits = len(acc.span_ids) + len(orphan_groups)
    seconds = sum(_seconds(t) for t in turns) if turns else acc.node_seconds
    samples = [_seconds(t) for t in turns] if turns else acc.step_seconds
    return {
        "kind": "node",
        "node": name,
        "name": name,
        "samples": len(samples),
        "longest_s": max(samples, default=0.0),
        "visits": visits,
        "time_s": seconds,
        "turns": len(turns),
        "cost_turns": len(costs),
        "cost_usd": sum(costs) if costs else None,
        "output_tokens": sum(t["profile_output_tokens"] or 0 for t in turns),
        "retries": len(turns) - len(groups),
        "children": [],
    }


def _sum(kind: str, name: str, visits: int | None, rows: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    costs = [row["cost_usd"] for row in rows if row["cost_usd"] is not None]
    rows = sorted(rows, key=lambda row: (-row["time_s"], row["name"]))
    return {
        "kind": kind,
        "name": name,
        "visits": visits,
        "time_s": sum(row["time_s"] for row in rows),
        "turns": sum(row["turns"] for row in rows),
        "cost_turns": sum(row["cost_turns"] for row in rows),
        "cost_usd": sum(costs) if costs else None,
        "output_tokens": sum(row["output_tokens"] for row in rows),
        "retries": sum(row["retries"] for row in rows),
        "children": rows,
        **extra,
    }


def _state_row(name: str, state: _State) -> dict[str, Any]:
    nodes = [_node_row(node, acc) for node, acc in state.nodes.items()]
    if len(nodes) == 1:
        only = nodes[0]
        label = name if only["name"] == name else f"{name} › {only['name']}"
        return {**only, "kind": "state", "name": label}
    return _sum("state", name, len(state.span_ids) or None, nodes)


def _flow_row(flow: _Flow) -> dict[str, Any]:
    rows = [_node_row(node, acc) for node, acc in flow.direct.items()]
    rows += [_state_row(name, state) for name, state in flow.states.items()]
    visits = (len(flow.span_ids) or None) if flow.kind == "flow" else None
    return _sum(flow.kind, flow.name, visits, rows, title=flow.title)


def build_flows(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {span["span_id"]: span for span in spans}
    containers = {
        span["parent_id"]
        for span in spans
        if span["parent_id"] and (_is_state(span) or _is_node(span))
    }
    workflow = next((span["workflow"] for span in spans if span["workflow"]), "") or "run"
    flows: dict[tuple[str, str], _Flow] = {}

    def flow_for(kind: str, name: str, title: str = "") -> _Flow:
        found = flows.get((kind, name))
        if found is None:
            found = flows[(kind, name)] = _Flow(kind, name, title)
        return found

    def place(item: dict[str, Any]) -> tuple[_Flow, _State | None]:
        chain = [item]
        seen = {item["span_id"]}
        while True:
            parent = by_id.get(chain[-1]["parent_id"])
            if parent is None or parent["span_id"] in seen:
                break
            chain.append(parent)
            seen.add(parent["span_id"])
        ancestors = chain[1:]
        state = next((span for span in chain if _is_state(span)), None)
        above = chain[chain.index(state) + 1 :] if state is not None else ancestors
        flow_span = next((span for span in above if _is_node(span)), None)
        top = chain[-1]
        attrs = item["attrs"]
        named_flow = attrs.get("workhorse.flow")
        stopped = bool(top["parent_id"]) and top["parent_id"] not in by_id and _depth(top) != 0
        if flow_span is not None:
            flow = flow_for("flow", flow_span["node"])
            flow.span_ids.add(flow_span["span_id"])
        elif stopped and isinstance(named_flow, str):
            flow = flow_for("flow", named_flow) if named_flow else flow_for("workflow", workflow)
        elif stopped:
            flow = flow_for("unfinished", top["parent_id"], top["parent_id"])
        else:
            flow = flow_for("workflow", workflow)
        if state is not None:
            found = flow.states[state["node"]]
            found.span_ids.add(state["span_id"])
            return flow, found
        named_state = attrs.get("workhorse.state")
        if stopped and flow_span is None and isinstance(named_state, str) and named_state:
            return flow, flow.states[named_state]
        return flow, None

    for span in spans:
        if _is_turn(span):
            parent = by_id.get(span["parent_id"])
            if parent is not None and _is_node(parent) and parent["span_id"] not in containers:
                continue
            flow, state = place(span)
            target = (state.nodes if state is not None else flow.direct)[span["node"]]
            target.turns.append(span)
        elif _is_node(span) and span["span_id"] not in containers:
            flow, state = place(span)
            target = (state.nodes if state is not None else flow.direct)[span["node"]]
            target.span_ids.add(span["span_id"])
            target.node_seconds += _seconds(span)
            target.step_seconds.append(_seconds(span))
    for span in spans:
        if _is_turn(span):
            parent = by_id.get(span["parent_id"])
            if parent is not None and _is_node(parent) and parent["span_id"] not in containers:
                flow, state = place(parent)
                target = (state.nodes if state is not None else flow.direct)[parent["node"]]
                target.turns.append(span)

    rows = [_flow_row(flow) for flow in flows.values()]
    for row in rows:
        row["name"] = UNFINISHED if row["kind"] == "unfinished" else row["name"]
    return sorted(rows, key=lambda row: (-row["time_s"], row["name"], row["title"]))


def node_breakdown(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The tree's leaves merged by node name, longest first. A node reached from two states is one row, and the rows add up to the tree's total."""
    merged: dict[str, dict[str, Any]] = {}

    def walk(row: dict[str, Any]) -> None:
        if "node" not in row:
            for child in row["children"]:
                walk(child)
            return
        found = merged.get(row["node"])
        if found is None:
            merged[row["node"]] = {
                key: row[key]
                for key in (
                    "node", "visits", "time_s", "samples", "longest_s", "turns",
                    "cost_turns", "cost_usd", "output_tokens", "retries",
                )
            }
            return
        found["visits"] += row["visits"]
        found["time_s"] += row["time_s"]
        found["samples"] += row["samples"]
        found["longest_s"] = max(found["longest_s"], row["longest_s"])
        found["turns"] += row["turns"]
        found["cost_turns"] += row["cost_turns"]
        found["output_tokens"] += row["output_tokens"]
        found["retries"] += row["retries"]
        if row["cost_usd"] is not None:
            found["cost_usd"] = (found["cost_usd"] or 0.0) + row["cost_usd"]

    for row in rows:
        walk(row)
    for row in merged.values():
        row["kind"] = "agent" if row["turns"] else "step"
    return sorted(merged.values(), key=lambda row: (-row["time_s"], row["node"]))


def turn_passes(spans: list[dict[str, Any]]) -> dict[str, tuple[str, int]]:
    """Each agent turn's flow and which pass of that flow it belongs to, by span id.

    A pass is one run of the flow's node span, counted from one in the order they started. A turn outside any flow node is absent.
    """
    by_id = {span["span_id"]: span for span in spans}
    containers = {
        span["parent_id"]
        for span in spans
        if span["parent_id"] and (_is_state(span) or _is_node(span))
    }
    started = sorted(
        (span for span in spans if _is_node(span) and span["span_id"] in containers),
        key=lambda span: span["start_ts"],
    )
    ordinals: dict[str, int] = {}
    seen: dict[str, int] = {}
    for span in started:
        seen[span["node"]] = seen.get(span["node"], 0) + 1
        ordinals[span["span_id"]] = seen[span["node"]]
    found: dict[str, tuple[str, int]] = {}
    for turn in spans:
        if not _is_turn(turn):
            continue
        parent = by_id.get(turn["parent_id"])
        item = parent if parent is not None and _is_node(parent) and parent["span_id"] not in containers else turn
        chain = [item]
        visited = {item["span_id"]}
        while (above := by_id.get(chain[-1]["parent_id"])) is not None and above["span_id"] not in visited:
            chain.append(above)
            visited.add(above["span_id"])
        state = next((span for span in chain if _is_state(span)), None)
        beyond = chain[chain.index(state) + 1 :] if state is not None else chain[1:]
        flow = next((span for span in beyond if _is_node(span)), None)
        if flow is not None and flow["span_id"] in ordinals:
            found[turn["span_id"]] = (flow["node"], ordinals[flow["span_id"]])
    return found


def _work_of(span: dict[str, Any]) -> str:
    return str(span["attrs"].get("work_id") or span["attrs"].get("wf.work_id") or "")


def _numbered(spans: list[dict[str, Any]]) -> tuple[dict[str, tuple[str, int, bool]], dict[tuple[str, str, int], str]]:
    by_id = {span["span_id"]: span for span in spans}
    containers = {
        span["parent_id"]
        for span in spans
        if span["parent_id"] and (_is_state(span) or _is_node(span))
    }
    started = sorted(
        (span for span in spans if _is_node(span) and span["span_id"] in containers),
        key=lambda span: (span["start_ts"], span["end_ts"], span["span_id"]),
    )
    order = {span["span_id"]: place for place, span in enumerate(started)}
    seen_in: dict[tuple[str, str], dict[str, None]] = {}
    where: dict[str, tuple[str, str]] = {}
    for original in spans:
        item = original
        if _is_turn(item):
            parent = by_id.get(item["parent_id"])
            if parent is not None and _is_node(parent) and parent["span_id"] not in containers:
                item = parent
        elif not (_is_node(item) and item["span_id"] not in containers) and item["attrs"].get("workhorse.span_kind") != "wait":
            continue
        chain = [item]
        visited = {item["span_id"]}
        while (above := by_id.get(chain[-1]["parent_id"])) is not None and above["span_id"] not in visited:
            chain.append(above)
            visited.add(above["span_id"])
        state = next((span for span in chain if _is_state(span)), None)
        beyond = chain[chain.index(state) + 1 :] if state is not None else chain[1:]
        flow = next((span for span in beyond if _is_node(span)), None)
        if flow is not None and flow["span_id"] in order:
            where[original["span_id"]] = (_work_of(original), flow["span_id"])
            seen_in.setdefault((_work_of(original), flow["node"]), {})[flow["span_id"]] = None
    rank: dict[tuple[str, str], int] = {}
    by_container = {span["span_id"]: span for span in started}
    for (work, name), ids in seen_in.items():
        for number, container in enumerate(sorted(ids, key=lambda one: order[one]), start=1):
            rank[(work, container)] = number
    found: dict[str, tuple[str, int, bool]] = {}
    for original in spans:
        key = original["span_id"]
        if key in where:
            work, container = where[key]
            found[key] = (by_container[container]["node"], rank[(work, container)], False)
    statuses = {
        (work, by_container[container]["node"], number): str(by_container[container].get("status") or "")
        for (work, container), number in rank.items()
    }
    for original in spans:
        key = original["span_id"]
        if key in found:
            continue
        item = original
        if _is_turn(item):
            parent = by_id.get(item["parent_id"])
            if parent is not None and _is_node(parent) and parent["span_id"] not in containers:
                item = parent
        elif not (_is_node(item) and item["span_id"] not in containers) and item["attrs"].get("workhorse.span_kind") != "wait":
            continue
        chain = [item]
        visited = {item["span_id"]}
        while (above := by_id.get(chain[-1]["parent_id"])) is not None and above["span_id"] not in visited:
            chain.append(above)
            visited.add(above["span_id"])
        top = chain[-1]
        named = item["attrs"].get("workhorse.flow")
        if top["parent_id"] and top["parent_id"] not in by_id and _depth(top) != 0 and isinstance(named, str) and named:
            work = _work_of(original)
            found[key] = (named, len(seen_in.get((work, named), {})) + 1, True)
    return found, statuses


def span_passes(spans: list[dict[str, Any]]) -> dict[str, tuple[str, int, bool]]:
    """Each agent turn's and each leaf step's flow and pass, by span id, and whether that pass is still open.

    A pass is numbered from one within its work item and flow, in the order the flow's node spans started. A run with no work item numbers within the flow across the run. A span in a pass that has not ended has no stored flow span, so it takes the flow it names and the pass after the last stored one of its work item. A span outside any flow is absent.
    """
    return _numbered(spans)[0]


def pass_status(spans: list[dict[str, Any]]) -> dict[tuple[str, str, int], str]:
    """The ended status of each stored flow pass, keyed by work item, flow and pass number as ``span_passes`` counts them."""
    return _numbered(spans)[1]


def span_seconds(span: dict[str, Any]) -> float:
    """The seconds the flow tree counts for one span."""
    return _seconds(span)


def leaf_steps(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The node spans that hold no other node or state, in the order given."""
    containers = {
        span["parent_id"]
        for span in spans
        if span["parent_id"] and (_is_state(span) or _is_node(span))
    }
    return [span for span in spans if _is_node(span) and span["span_id"] not in containers]
