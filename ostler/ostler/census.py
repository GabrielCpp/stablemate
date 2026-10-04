"""Which of doctor's codes can fire at all, told apart from which happen not to."""

from __future__ import annotations

import ast
import inspect
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any

from ostler import doctor, fragment_hosts, hidden_claims, page_size, section_hosts, server_membership, step_commands

DOCTOR_MODULES: tuple[ModuleType, ...] = (doctor, fragment_hosts, hidden_claims, page_size, section_hosts, server_membership, step_commands)

_BRIDGE = "gap_findings has no product caller; gaps surface via qa compile-plan only"

_NO_MILESTONES = "no book in the corpus declares a milestone, so the dependency walk has nothing to walk"

DORMANT_UNREACHABLE: dict[str, str] = {
    "deletes-shared-fixture": _BRIDGE,
    "invalid-http-method": _BRIDGE,
    "milestone-cycle": _NO_MILESTONES,
    "needs-absence-check": _BRIDGE,
    "needs-multi-target-runtime": _BRIDGE,
    "needs-out-of-band-observation": _BRIDGE,
    "needs-snapshot": _BRIDGE,
    "needs-target-backend": _BRIDGE,
    "needs-trigger-action": _BRIDGE,
    "precondition-discharged-by-arrangement": _BRIDGE,
    "screen-preconditions-undeclared": _BRIDGE,
    "unarranged-interaction-precondition": _BRIDGE,
    "unarranged-journey": _BRIDGE,
    "unarranged-request-body": _BRIDGE,
    "unarrangeable-server-fault": _BRIDGE,
    "unarranged-scenario": _BRIDGE,
    "unarranged-state": _BRIDGE,
    "uncompilable-claim": _BRIDGE,
    "undeclared-bundle-id": _BRIDGE,
    "undeclared-entry-url": _BRIDGE,
    "undeclared-launch-screen": _BRIDGE,
    "unidentifiable-screen": _BRIDGE,
    "unreachable-from-launch": _BRIDGE,
    "unresolved-extends": _BRIDGE,
    "unresolved-precondition": _BRIDGE,
}


@dataclass(frozen=True)
class Census:
    """Traced `doctor` run(s), classified — one from `take_census`, several from `merge`."""

    fired: frozenset[str]
    dormant_clean: frozenset[str]
    dormant_unreachable: frozenset[str]
    profile: str = ""
    sites: dict[str, frozenset[str]] = field(default_factory=dict)
    runs: int = 1

    @property
    def undeclared(self) -> frozenset[str]:
        """Unreachable codes with no recorded reason — the finding."""
        return self.dormant_unreachable - DORMANT_UNREACHABLE.keys()

    @property
    def stale(self) -> frozenset[str]:
        """Recorded reasons for codes that are no longer unreachable — a dead excuse."""
        return frozenset(DORMANT_UNREACHABLE) - self.dormant_unreachable


def merge(censuses: Iterable[Census]) -> Census:
    """One census over a set of runs: entered anywhere counts as entered."""
    runs = list(censuses)
    if not runs:
        raise ValueError("a census of no runs observes nothing and cannot carry a verdict")
    sites: dict[str, frozenset[str]] = {}
    for run in runs:
        sites.update(run.sites)
    fired = frozenset().union(*(run.fired for run in runs))
    clean = frozenset().union(*(run.dormant_clean for run in runs)) - fired
    return Census(
        fired=fired,
        dormant_clean=clean,
        dormant_unreachable=frozenset(sites) - fired - clean,
        profile="+".join(sorted({run.profile for run in runs if run.profile})),
        sites=sites,
        runs=len(runs),
    )


def code_sites(*modules: ModuleType) -> dict[str, frozenset[str]]:
    """Every `Finding(severity, code, ...)` site in *modules*, doctor's own when none is named, by the function enclosing it."""
    sites: dict[str, set[str]] = {}
    for module in modules or DOCTOR_MODULES:
        for code, where in _module_sites(module).items():
            sites.setdefault(code, set()).update(where)
    return {code: frozenset(where) for code, where in sites.items()}


def _module_sites(module: ModuleType) -> dict[str, set[str]]:
    tree = ast.parse(inspect.getsource(module))

    funcs: list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, str]] = []

    def collect(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                qualname = f"{prefix}{child.name}"
                funcs.append((child, qualname))
                collect(child, f"{qualname}.<locals>.")
            elif isinstance(child, ast.ClassDef):
                collect(child, f"{prefix}{child.name}.")
            else:
                collect(child, prefix)

    collect(tree, "")

    def enclosing(line: int) -> str:
        best: tuple[ast.FunctionDef | ast.AsyncFunctionDef, str] | None = None
        for func, qualname in funcs:
            if func.lineno <= line <= (func.end_lineno or func.lineno):
                if best is None or func.lineno > best[0].lineno:
                    best = (func, qualname)
        return best[1] if best is not None else "<module>"

    sites: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        if node.func.id != "Finding" or len(node.args) < 2:
            continue
        code = node.args[1]
        if isinstance(code, ast.Constant) and isinstance(code.value, str):
            sites.setdefault(code.value, set()).add(enclosing(node.lineno))
    return sites


def take_census(run: Callable[[], object], *modules: ModuleType) -> Census:
    """Run *run* with the function entries of *modules*, doctor's own when none is named, traced, and classify every code in them."""
    filenames = {inspect.getsourcefile(module) for module in modules or DOCTOR_MODULES}
    entered: set[str] = set()

    def tracer(frame: Any, event: str, _arg: Any) -> None:
        if event == "call" and frame.f_code.co_filename in filenames:
            entered.add(frame.f_code.co_qualname)
        return None

    previous = sys.gettrace()
    sys.settrace(tracer)
    try:
        report = run()
    finally:
        sys.settrace(previous)

    sites = code_sites(*modules)
    fired = {finding.code for finding in getattr(report, "findings", [])}
    clean, unreachable = set(), set()
    for code, where in sites.items():
        if code in fired:
            continue
        (clean if where & entered else unreachable).add(code)
    return Census(
        fired=frozenset(fired & sites.keys()),
        dormant_clean=frozenset(clean),
        dormant_unreachable=frozenset(unreachable),
        profile=str(getattr(report, "profile", "") or ""),
        sites=sites,
    )


def render(census: Census) -> str:
    """The census as a report, ordered so the finding is not buried under the health."""
    lines = [
        f"{len(census.sites)} codes defined   profile: {census.profile or '?'}   "
        f"runs: {census.runs}",
        f"  {len(census.fired):3} fired",
        f"  {len(census.dormant_clean):3} dormant-clean        the checker ran, the tree has no violation",
        f"  {len(census.dormant_unreachable):3} dormant-unreachable  the checker was never entered",
        "",
    ]
    if census.undeclared:
        lines.append("UNREACHABLE WITH NO RECORDED REASON:")
        lines += [f"   {code:38} {', '.join(sorted(census.sites.get(code, ()))) or '?'}"
                  for code in sorted(census.undeclared)]
        lines.append("")
    if census.stale:
        lines.append("RECORDED AS UNREACHABLE BUT NOW REACHABLE (delete the entry):")
        lines += [f"   {code}" for code in sorted(census.stale)]
        lines.append("")
    if census.runs < 2:
        lines.append(
            f"note: this census observed one book, under the `{census.profile or '?'}` "
            "profile. A code unreachable here may be exercised by another book or another "
            "profile — the two sections above are sound only over the whole corpus, which "
            "is what `test_census_corpus.py` takes them over.",
        )
        lines.append("")
    lines.append("unreachable, by recorded reason:")
    for code in sorted(census.dormant_unreachable & DORMANT_UNREACHABLE.keys()):
        lines.append(f"   {code:38} {DORMANT_UNREACHABLE[code]}")
    return "\n".join(lines)
