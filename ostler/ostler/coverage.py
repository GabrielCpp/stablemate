"""``ostler coverage`` — join a book's ``code:`` citations against a source inventory."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ostler import graph as graph_mod
from ostler import refs as refs_mod
from ostler.model import Graph
from ostler.qa.outcome import QaOutcome
from ostler.refs import normalize_ref, strip_digest


def _values(value: Any) -> list[str]:
    """A bullet's values."""
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)] if value else []


def citations(graph: Graph, surface: str | None = None) -> dict[str, list[str]]:
    """Every ``code:`` target the book cites → the node ids citing it."""
    out: dict[str, list[str]] = {}
    data = graph_mod.build(graph, surface=surface)
    for node in data["nodes"]:
        for ref in refs_mod.code_refs(node["bullets"].get("code")):
            out.setdefault(strip_digest(ref), []).append(node["id"])
    return out


def load_inventory(path: str | Path) -> dict:
    """Read a source-inventory artifact, raising rather than returning empty."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("units"), list):
        raise ValueError(f"{path}: not a source inventory (no `units` list)")
    return data


def load_waivers(path: str | Path | None) -> dict[str, str]:
    """Adjudicated non-units → the reason each was waived, keyed by ``code:`` target."""
    if not path:
        return {}
    file = Path(path)
    if not file.exists():
        return {}
    data = json.loads(file.read_text(encoding="utf-8"))
    waivers = data.get("waivers", data) if isinstance(data, dict) else data
    if isinstance(waivers, dict):
        return {normalize_ref(k): str(v) for k, v in waivers.items()}
    out: dict[str, str] = {}
    for entry in waivers:
        ref = normalize_ref(str(entry.get("code", "")))
        if ref:
            out[ref] = str(entry.get("reason", ""))
    return out


def _module_is_covered(unit_path: str, cited: set[str], declared: dict[str, set[str]]) -> bool:
    """The transitive module rule."""
    symbols = declared.get(unit_path, set())
    if not symbols:
        return False
    return symbols <= cited


def compute(inventory: dict, cited: dict[str, list[str]],
            waivers: dict[str, str] | None = None) -> dict:
    """Join the inventory's units against the book's citations."""
    waivers = waivers or {}
    cited_refs = set(cited)
    units = inventory["units"]

    declared: dict[str, set[str]] = {}
    for unit in units:
        if unit.get("kind") == "symbol":
            declared.setdefault(unit["path"], set()).add(unit["code"])

    covered = 0
    waived = 0
    missing: list[dict] = []
    for unit in units:
        code = unit["code"]
        if code in cited_refs:
            covered += 1
        elif code in waivers:
            covered += 1
            waived += 1
        elif unit.get("kind") == "module" and _module_is_covered(unit["path"], cited_refs, declared):
            covered += 1
        else:
            missing.append({"kind": unit.get("kind", ""), "path": unit.get("path", ""),
                            "symbol": unit.get("symbol", ""), "code": code})

    return {
        "covered": covered,
        "total": len(units),
        "waived": waived,
        "cited": len(cited_refs),
        "missing": missing,
        "errors": list(inventory.get("errors") or []),
    }


def run(graph: Graph, *, surface: str | None = None, inventory: str | Path,
        waivers: str | Path | None = None) -> dict:
    """``ostler coverage`` end to end: read the inventory, cite the book, join."""
    data = load_inventory(inventory)
    result = compute(data, citations(graph, surface), load_waivers(waivers))
    result["surface"] = surface or ""
    result["sourceRoot"] = data.get("sourceRoot", "")
    result["excludes"] = data.get("excludes", [])
    return result


def is_complete(result: dict) -> bool:
    """A book is complete when every unit is covered — and the instrument was not blind."""
    return (not result["errors"]) and result["total"] > 0 and result["covered"] == result["total"]


def render(result: dict) -> str:
    """The human line, plus the misses."""
    pct = (100 * result["covered"] // result["total"]) if result["total"] else 0
    head = (f"{result['surface'] or '(all)'}: {result['covered']}/{result['total']} units "
            f"covered ({pct}%)")
    if result["waived"]:
        head += f", {result['waived']} waived"
    lines = [head]
    for err in result["errors"]:
        lines.append(f"  inventory error: {err}")
    if not result["total"]:
        lines.append("  no units in the inventory — an empty book and a finished one look "
                     "identical here, so this is not a pass")
    for miss in result["missing"]:
        lines.append(f"  missing {miss['kind']}: {miss['code']}")
    return "\n".join(lines)


def cmd_coverage(graph: Graph, *, inventory: str | Path, surface: str | None = None,
                 waivers: str | Path | None = None) -> QaOutcome:
    """`ostler coverage` as an outcome: `ok` = complete, `data` = the join."""
    try:
        result = run(graph, surface=surface, inventory=inventory, waivers=waivers)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        message = str(exc)
        return QaOutcome(ok=False, message=message, status="invalid",
                         data={"status": "invalid", "message": message})
    return QaOutcome(ok=is_complete(result), message=render(result), data=result)
