"""Which of doctor's codes can fire at all, told apart from which happen not to.

A code that emits nothing is two opposite findings wearing the same face. Either the
checker ran and the tree is clean — the code is working, and its silence is the good
news — or the checker never ran, and the rule it encodes is not being enforced anywhere.
`doctor`'s own report cannot tell them apart, because both appear in it as an absence.

Neither can a reader. The obvious method is to grep `doctor.py` for its codes and
subtract the ones that fired; that method reports every dormant-clean code as a hole and
is how "33 dead rules" gets written down about a tree where most of those rules ran fine.
**A code's silence is not observable from the code's text.** Only a run says which kind
of silence it is, so this module is a run: it traces which of `doctor`'s functions are
entered while a real report is produced, and joins each code's emission site to its
enclosing function.

The gate this feeds is not "no dormant codes" — 42 of them are dormant-clean today and
that is health, not debt. It is **no unreachable code without a recorded reason**: a
checker family that stops being called must be a decision somebody made, not a thing that
happened. `DORMANT_UNREACHABLE` below is that record, and it is checked in both
directions, so a family that gets wired back up fails here too rather than leaving a stale
excuse behind.
"""

from __future__ import annotations

import ast
import inspect
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ostler import doctor

#: The planning graph — milestones, epics, seeds, stories — and the fixture machinery are
#: checked only under the `full` profile: `doctor.run` returns early for any other one
#: (`doctor.py:180`). On an `exploration` book those checkers are never entered, so every
#: code they own is unreachable *by design and by profile*, not by neglect. This is one
#: decision, and it is written once so a reader can see that it is one — thirty-six
#: separate excuses would read as thirty-six separate holes.
_PROFILE_GATED = "planning-graph and fixture checks run only under the `full` profile (doctor.py:180)"

#: Codes whose checker is not called on any real book today, each with the reason it is
#: not. A reason is a decision or a missing piece of work — never "nobody noticed", which
#: is what this registry exists to make impossible to write silently.
DORMANT_UNREACHABLE: dict[str, str] = {
    'backlog-item-in-multiple-milestones': _PROFILE_GATED,
    'cross-epic-dependency': _PROFILE_GATED,
    'cross-epic-seed': _PROFILE_GATED,
    'dangling-dependency': _PROFILE_GATED,
    'dangling-milestone-dependency': _PROFILE_GATED,
    'dangling-milestone-epic': _PROFILE_GATED,
    'dangling-seed': _PROFILE_GATED,
    'epic-in-multiple-milestones': _PROFILE_GATED,
    'epic-without-milestone': _PROFILE_GATED,
    'fixture-arg-mismatch': _PROFILE_GATED,
    'fixture-needs-cycle': _PROFILE_GATED,
    'fixture-needs-target-args': _PROFILE_GATED,
    'fixture-secret-name': _PROFILE_GATED,
    'fixture-step-kind': _PROFILE_GATED,
    'fixture-step-no-run': _PROFILE_GATED,
    'fixture-undeclared-provides': _PROFILE_GATED,
    'malformed-dependency-bullet': _PROFILE_GATED,
    'milestone-cycle': _PROFILE_GATED,
    'missing-story-file': _PROFILE_GATED,
    'orphan-seed': _PROFILE_GATED,
    'qa-fixture-bullet': _PROFILE_GATED,
    'qa-fixture-declaration': _PROFILE_GATED,
    'story-conflict': _PROFILE_GATED,
    'story-covers-no-seed': _PROFILE_GATED,
    'story-fixture-stray': _PROFILE_GATED,
    'story-id-mismatch': _PROFILE_GATED,
    'story-key-collision': _PROFILE_GATED,
    'story-section-order': _PROFILE_GATED,
    'story-status-mismatch': _PROFILE_GATED,
    'unclassified-seed': _PROFILE_GATED,
    'undeclared-story-fixture': _PROFILE_GATED,
    'unknown-book-fixture': _PROFILE_GATED,
    'unknown-story-fixture': _PROFILE_GATED,
    'unmigrated-fixture-declaration': _PROFILE_GATED,
    'unused-story-fixture': _PROFILE_GATED,
    'unwritten-story': _PROFILE_GATED,

    # `gap_findings` maps a compiler `Gap` to a `Finding`, and its only caller in the repo
    # is its own unit test. `doctor` never runs the compiler, so every kind it maps is
    # dead *to doctor* — the gaps themselves are still reported by `qa compile-plan`.
    # The builders read doctor, so this is the bridge that decides whether a named gap
    # cause ever reaches a repair turn.
    "uncompilable-claim": "gap_findings has no product caller; gaps surface via qa compile-plan only",
    "unresolved-precondition": "gap_findings has no product caller; gaps surface via qa compile-plan only",
    "screen-preconditions-undeclared": "gap_findings has no product caller; gaps surface via qa compile-plan only",
    "needs-snapshot": "gap_findings has no product caller; gaps surface via qa compile-plan only",
    "needs-out-of-band-observation": "gap_findings has no product caller; gaps surface via qa compile-plan only",
}


@dataclass(frozen=True)
class Census:
    """One traced `doctor` run, classified."""

    fired: frozenset[str]
    dormant_clean: frozenset[str]
    dormant_unreachable: frozenset[str]
    #: The profile the traced run used. Load-bearing, not decoration: half of doctor is
    #: gated on `full`, so a census taken under any other profile reports those codes
    #: unreachable and is right to — about that profile, and about no other.
    profile: str = ""
    sites: dict[str, frozenset[str]] = field(default_factory=dict)

    @property
    def undeclared(self) -> frozenset[str]:
        """Unreachable codes with no recorded reason — the finding."""
        return self.dormant_unreachable - DORMANT_UNREACHABLE.keys()

    @property
    def stale(self) -> frozenset[str]:
        """Recorded reasons for codes that are no longer unreachable — a dead excuse."""
        return frozenset(DORMANT_UNREACHABLE) - self.dormant_unreachable


def code_sites(module: Any = doctor) -> dict[str, frozenset[str]]:
    """Every `Finding(severity, code, ...)` site in *module*, by the function enclosing it.

    Read off the AST rather than by importing and introspecting, for the same reason the
    okf-builder drift tripwire does: a code passed through a variable is invisible to
    either method, and forcing each one to be spelled as a literal is what makes a new
    code a decision somebody takes on purpose.
    """
    tree = ast.parse(inspect.getsource(module))

    #: Every function in the module by qualified name, which is what makes the join sound.
    #: A bare `__name__` is not an identity: `doctor` has three nested helpers all called
    #: `visit`, so keying on the name made entering any one of them mark all three entered
    #: — and `milestone-cycle`, which only the milestone `visit` can emit, was reported
    #: reachable on a book with no milestones in it because the *fixture* `visit` had run.
    #: `co_qualname` carries the enclosing scope, so the two sides agree on which function
    #: they mean rather than only on what it is called.
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
        # Innermost wins: a nested `visit` inside a checker is the frame the tracer sees,
        # not its parent, so the join has to agree with what `sys.settrace` reports.
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
    return {code: frozenset(where) for code, where in sites.items()}


def take_census(run: Callable[[], object], module: Any = doctor) -> Census:
    """Run *run* with *module*'s function entries traced, and classify every code in it.

    `sys.settrace` is used rather than a coverage tool because the question is narrower
    than coverage and the answer must be available wherever `ostler` runs: only `"call"`
    events in one file are recorded, and the local tracer is declined, so the traced run
    costs one dict lookup per call into that module and nothing elsewhere.
    """
    filename = inspect.getsourcefile(module)
    entered: set[str] = set()

    def tracer(frame: Any, event: str, _arg: Any) -> None:
        if event == "call" and frame.f_code.co_filename == filename:
            entered.add(frame.f_code.co_qualname)
        return None

    previous = sys.gettrace()
    sys.settrace(tracer)
    try:
        report = run()
    finally:
        sys.settrace(previous)

    sites = code_sites(module)
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
        f"{len(census.sites)} codes defined   profile: {census.profile or '?'}",
        f"  {len(census.fired):3} fired",
        f"  {len(census.dormant_clean):3} dormant-clean        the checker ran, the tree has no violation",
        f"  {len(census.dormant_unreachable):3} dormant-unreachable  the checker was never entered",
        "",
    ]
    if census.undeclared:
        lines.append("UNREACHABLE WITH NO RECORDED REASON:")
        # `sites` is absent on a `Census` built by hand rather than by `take_census`,
        # and a reporting function that raises instead of reporting is worse than one
        # that says it does not know where the code lives.
        lines += [f"   {code:38} {', '.join(sorted(census.sites.get(code, ()))) or '?'}"
                  for code in sorted(census.undeclared)]
        lines.append("")
    if census.stale:
        lines.append("RECORDED AS UNREACHABLE BUT NOW REACHABLE (delete the entry):")
        lines += [f"   {code}" for code in sorted(census.stale)]
        lines.append("")
    if census.profile and census.profile != "full":
        lines.append(
            f"note: this run used the `{census.profile}` profile, so the planning-graph and "
            "fixture checkers were skipped wholesale — their codes are unreachable here and "
            "say nothing about a `full`-profile book.",
        )
        lines.append("")
    lines.append("unreachable, by recorded reason:")
    for code in sorted(census.dormant_unreachable & DORMANT_UNREACHABLE.keys()):
        lines.append(f"   {code:38} {DORMANT_UNREACHABLE[code]}")
    return "\n".join(lines)
