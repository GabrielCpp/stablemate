"""``ostler coverage`` — join a book's ``code:`` citations against a source inventory.

The builder's stop condition used to be a value the recheck agent emitted *about its own
work*. This is the instrument that replaces it: coverage is arithmetic, not a self-report.

The join lives here rather than in a workflow script for two reasons — both the builder and a
CI check need it, and a rule this load-bearing deserves unit tests over fixtures rather than a
regex in a script node.

**The grammar is the book's, not the tool's.** A ``code:`` target is
``<path-relative-to-repo-root>::<symbol>``, where ``<symbol>`` is qualified by its owner when
it has one (``api/internal/x.go::(*FirebaseClaimsWriter).SetRoleClaims``). That is what books
already write, and it is strictly more precise than a bare name — which cannot disambiguate
two types declaring the same method in one file. When the book and the tool disagree about
grammar, the book wins; a tool that cannot parse it is the defect.

**The transitive module rule** (the one piece of judgement the join owns):

    a `module` unit is covered if it is cited directly, **or** it declares at least one symbol
    and every symbol it declares is cited.

The ``declares at least one symbol`` clause is load-bearing and easy to omit. Without it the
rule is *vacuously true for a file that declares nothing* — and it would discharge exactly the
case the module unit exists for: a Twig template with no ``{% block %}`` renders a screen and
must be cited directly. A vacuous rule marks such a file covered on the strength of having
found nothing in it, which is silence read as evidence.

The rule does **not** discharge every uncited module — that would be the "drop the module unit"
rule, rejected because a file is the real unit for a template language. A unit's shape is
language-shaped: symbols are the unit for Go/TS, the file is the unit for a template.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ostler import graph as graph_mod
from ostler.model import Graph


def _values(value: Any) -> list[str]:
    """A bullet's values. A repeated key parses to a list; a single one to a string."""
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)] if value else []


def normalize_ref(value: str) -> str:
    """Strip the decoration a `code:` bullet may carry (backticks, trailing commas)."""
    return value.strip().strip("`, ").strip()


def citations(graph: Graph, surface: str | None = None) -> dict[str, list[str]]:
    """Every ``code:`` target the book cites → the node ids citing it.

    Scoped to one book by ``surface`` (``docs/features/<surface>``). A node may carry several
    ``code:`` bullets, and several nodes may cite one target; both are kept so a caller can
    report *who* cites a unit.
    """
    out: dict[str, list[str]] = {}
    data = graph_mod.build(graph, surface=surface)
    for node in data["nodes"]:
        for raw in _values(node["bullets"].get("code")):
            ref = normalize_ref(raw)
            if ref:
                out.setdefault(ref, []).append(node["id"])
    return out


def load_inventory(path: str | Path) -> dict:
    """Read an ``inventory-source.py`` artifact, raising rather than returning empty.

    An unreadable inventory must never present as zero units: downstream, an empty unit list
    reads as "everything is covered".
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("units"), list):
        raise ValueError(f"{path}: not a source inventory (no `units` list)")
    return data


def load_waivers(path: str | Path | None) -> dict[str, str]:
    """Adjudicated non-units → the reason each was waived, keyed by ``code:`` target.

    A waiver is the agent's recorded judgement that a computed miss is not a real gap (a helper
    folded into a documented contract, a deliberate non-unit). It is committed, diffable and
    reviewable, so the verdict survives the round instead of being re-litigated every time.
    A missing file is not an error — it means nothing has been waived.
    """
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
    """The transitive module rule. See the module docstring — the non-vacuous clause is why."""
    symbols = declared.get(unit_path, set())
    if not symbols:
        return False  # declares nothing: it can only be covered by a direct citation
    return symbols <= cited


def compute(inventory: dict, cited: dict[str, list[str]],
            waivers: dict[str, str] | None = None) -> dict:
    """Join the inventory's units against the book's citations.

    Returns ``{covered, total, waived, missing[], cited, errors[]}``. ``missing`` carries each
    uncovered unit's kind/path/symbol/code so a caller can queue it or adjudicate it.
    """
    waivers = waivers or {}
    cited_refs = set(cited)
    units = inventory["units"]

    # Which symbols each module declares — the input to the transitive rule.
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
        # The inventory's own errors ride along: a blind front end must not present as a
        # complete book, and a caller gating on this needs to see the difference.
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
    """A book is complete when every unit is covered — and the instrument was not blind.

    An inventory that reported errors cannot ground a pass: zero units out of an unreadable
    tree would otherwise satisfy `covered == total` vacuously. Nor can a book with no units at
    all — an empty inventory is the shape a missing book and a finished one share, and only one
    of them is done.
    """
    return (not result["errors"]) and result["total"] > 0 and result["covered"] == result["total"]


def render(result: dict) -> str:
    """The human line, plus the misses. `--json` is the machine's face."""
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
