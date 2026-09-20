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

**The verdict is quantified over runs; one run cannot carry it.** "The rule is not enforced
anywhere" is a statement about a set, and `take_census` observes one book — so for years the
gap between the two was paid for in prose. Half of `doctor` is gated on the `full` profile,
so a census of the tree's one `exploration` book indicted twenty-nine planning-graph codes,
and each was bought off with a recorded reason; run the same registry against any `full`
book and all twenty-nine came back as dead excuses to delete, advice which, followed, broke
the other book. Same registry, same tree, opposite answers. `merge` closes it: a `Census` of
one run stays exactly what it is, an observation, and `undeclared` and `stale` are asked of
the merge over a corpus that covers every profile. All twenty-nine entries then went away,
because those checkers do run — elsewhere.
"""

from __future__ import annotations

import ast
import inspect
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from ostler import doctor

#: `gap_findings` maps a compiler `Gap` to a `Finding`, and its only caller in the repo is
#: its own unit test. `doctor` never runs the compiler, so every kind it maps is dead *to
#: doctor* on every book and every profile — the gaps themselves are still reported by `qa
#: compile-plan`. The builders read doctor, so this is the bridge that decides whether a
#: named gap cause ever reaches a repair turn, and that it is dead is the standing debt.
_BRIDGE = "gap_findings has no product caller; gaps surface via qa compile-plan only"

#: `_check_milestone_cycles` calls its walk once per milestone, and no app in the corpus
#: declares one, so the walk is never entered. A fact about the corpus, not about the rule
#: — and the corpus is the thing this registry is judged against, so it is recorded here
#: rather than treated as a hole in `doctor`.
_NO_MILESTONES = "no book in the corpus declares a milestone, so the dependency walk has nothing to walk"

#: Codes whose checker is not called on **any** book of the corpus, each with the reason it
#: is not. A reason is a decision or a missing piece of work — never "nobody noticed", which
#: is what this registry exists to make impossible to write silently. An entry here is a
#: claim about every run in the corpus at once; a code that one profile skips and another
#: exercises does not belong, and `merge` is what makes that distinction observable.
DORMANT_UNREACHABLE: dict[str, str] = {
    "invalid-http-method": _BRIDGE,
    "milestone-cycle": _NO_MILESTONES,
    "needs-multi-target-runtime": _BRIDGE,
    "needs-out-of-band-observation": _BRIDGE,
    "needs-snapshot": _BRIDGE,
    "needs-target-backend": _BRIDGE,
    "screen-preconditions-undeclared": _BRIDGE,
    "unarranged-interaction-precondition": _BRIDGE,
    "unarranged-journey": _BRIDGE,
    "unarranged-request-body": _BRIDGE,
    "unarranged-scenario": _BRIDGE,
    "unarranged-state": _BRIDGE,
    "uncompilable-claim": _BRIDGE,
    "undeclared-bundle-id": _BRIDGE,
    "undeclared-entry-url": _BRIDGE,
    "unidentifiable-screen": _BRIDGE,
    "unresolved-extends": _BRIDGE,
    "unresolved-precondition": _BRIDGE,
}


@dataclass(frozen=True)
class Census:
    """Traced `doctor` run(s), classified — one from `take_census`, several from `merge`."""

    fired: frozenset[str]
    dormant_clean: frozenset[str]
    dormant_unreachable: frozenset[str]
    #: The profile the traced run used. Load-bearing, not decoration: half of doctor is
    #: gated on `full`, so a census taken under any other profile reports those codes
    #: unreachable and is right to — about that profile, and about no other. A merge
    #: carries the profiles it covers, joined, because that is what makes its verdict sound.
    profile: str = ""
    sites: dict[str, frozenset[str]] = field(default_factory=dict)
    #: How many runs this census observed. One is an observation; the verdict below is a
    #: claim about a set, so a reader has to be able to tell which they are holding.
    runs: int = 1

    @property
    def undeclared(self) -> frozenset[str]:
        """Unreachable codes with no recorded reason — the finding.

        Sound only on a census that covers the corpus: on a single book it names every code
        some *other* profile exercises, which is how twenty-nine planning-graph rules came
        to be written down as excused.
        """
        return self.dormant_unreachable - DORMANT_UNREACHABLE.keys()

    @property
    def stale(self) -> frozenset[str]:
        """Recorded reasons for codes that are no longer unreachable — a dead excuse."""
        return frozenset(DORMANT_UNREACHABLE) - self.dormant_unreachable


def merge(censuses: Iterable[Census]) -> Census:
    """One census over a set of runs: entered anywhere counts as entered.

    The registry's question is whether a rule is enforced *anywhere*, and that quantifier is
    the whole reason this exists rather than each caller intersecting sets by hand — a
    reader who does it by hand does it per code, and the per-code version is the bug.

    `fired` and `dormant_clean` union; `dormant_unreachable` is what is left of the defined
    sites after both, which is the only definition that cannot report a code twice. `sites`
    is taken from the runs rather than re-read, and they agree: every run reads the same
    module.
    """
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
        f"{len(census.sites)} codes defined   profile: {census.profile or '?'}   "
        f"runs: {census.runs}",
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
    if census.runs < 2:
        # Said even when the single run is `full`, because the profile is not the only way
        # one book fails to exercise a checker — `_check_unbacked_precondition` is entered
        # by exactly one app of six, and a census of either of the other five would have
        # named it a hole. The verdict needs the corpus; this run is an observation.
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
