#!/usr/bin/env python3
"""Guard the "one finding, one remedy, one ref" rule over this repo's own book.

A doctor ``Finding.ref`` is an **address**: the okf-builder drain keys a worklist row on it,
hands the row to a repair turn, and counts three attempts against it. So a ref that names a
whole node when the defect is one of its twelve ``verify:`` bullets does not merely read
vaguely — it collapses twelve distinct defects into one row with one budget, and the turn
reads whichever sibling it lands on, finds it correct, and returns with the finding standing.
Three attempts, an adjudication and an operator gate, spent on an address that could not have
worked. ``ostler.doctor`` states the same invariant itself, at ``competing-implementations``:
a shared ref "collapsed them into one worklist item and made one waiver silently accept both."

This is the property, checked over the real corpus rather than a taxonomy of which keys
repeat: **no two findings share a ``(code, ref)`` pair.** It generalises where a per-code
test does not — a new check that forgets its index is caught by the same run that catches a
regression in an old one, and no list has to be kept up to date for that to happen.

Two exemptions, both because the ambiguity is already named somewhere with a remedy:

* A finding that links its siblings through ``related`` is deliberately one finding about a
  group — ``competing-implementations`` is the example — and its shared ref is the point.
* A node whose **id is not unique in the book** cannot have an unambiguous ref, because the
  id is the ambiguity. Those are counted and printed rather than passed over in silence: the
  book states one heading anchor twice, and until that is fixed every address into it — a
  link, a coverage join, a ``qa context`` obligation id — is ambiguous too, not just a
  finding's ref.
"""

from __future__ import annotations

import collections
import sys
from pathlib import Path

from ostler import doctor
from ostler.api import Ostler
from ostler.model import Graph

#: The repo whose book this reads. The guard is about *doctor's* refs, so it wants the
#: largest real corpus available rather than a fixture: a code emitted nowhere in this book
#: is a code the check cannot speak to, and says so by simply not covering it.
REPO = Path(__file__).resolve().parent.parent

STEER = (
    "Give the finding an address that names exactly the thing to change: "
    "`refs.bullet_ref(node.id, key, index)` for a per-bullet defect (the index is 1-based "
    "over that key's occurrences, matching `registry.normative_claims` and `qa context`'s "
    "obligation ids), or a discriminator of the defect's own — see `refs.collision_ref`. "
    "When a finding really is about a group, link its siblings through `related`."
)


def duplicate_node_ids(graph: Graph) -> set[str]:
    """Node ids the book states more than once — an ambiguity no ref can resolve."""
    counts = collections.Counter(node.id for node in graph.ui_nodes)
    return {node_id for node_id, n in counts.items() if n > 1}


def _node_of(ref: str) -> str:
    """The node part of a ref: everything before the key segment doctor appends.

    A trailing bullet index is dropped, so ``…#effects#consistency:1`` and ``…#effects`` name
    the same node. A code-symbol ref carries no ``#`` and is returned whole; it matches no
    node id, which is the right answer for one. The result is only ever looked up against the
    set of duplicated ids, so a ref shape that reduces to nothing real is harmless — it finds
    no match and the finding is held to the rule.
    """
    path, _, rest = ref.partition("#")
    if not rest:
        return ref
    head = rest.split("#")[0]
    stem, colon, index = head.rpartition(":")
    if colon and index.isdigit():
        head = stem
    return f"{path}#{head}" if head else path


def ambiguous_refs(graph: Graph) -> tuple[list[str], int]:
    """Every ``(code, ref)`` shared by findings that are not linked as a group.

    Returns the problems and the count excused for sitting on a duplicated node id.
    """
    report = doctor.run(graph)
    groups: dict[tuple[str, str], list[doctor.Finding]] = collections.defaultdict(list)
    for finding in report.findings:
        groups[(finding.code, finding.ref)].append(finding)

    duplicated = duplicate_node_ids(graph)
    problems: list[str] = []
    excused = 0
    for (code, ref), findings in sorted(groups.items()):
        if len(findings) < 2 or any(f.related for f in findings):
            continue
        if _node_of(ref) in duplicated:
            excused += len(findings)
            continue
        where = ", ".join(sorted({f"{f.path}:{f.line}" for f in findings}))
        problems.append(f"{code}: {len(findings)} findings share ref {ref!r} ({where})")
    return problems, excused


def main(argv: list[str]) -> int:
    graph = Ostler(REPO).graph
    problems, excused = ambiguous_refs(graph)
    if excused:
        dups = len(duplicate_node_ids(graph))
        print(
            f"note: {excused} finding(s) excused — {dups} node id(s) are stated twice in the "
            f"book, so no ref into them can be unambiguous (`ostler graph --json` lists them)",
            file=sys.stderr,
        )
    if not problems:
        return 0
    print("\nFAIL check_finding_refs:", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    print(f"\n{STEER}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
