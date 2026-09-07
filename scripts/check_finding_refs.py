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

One exemption: a finding that links its siblings through ``related`` is deliberately one
finding about a group — ``competing-implementations`` is the example — and its shared ref is
the point.

There was a second, and its removal is the record of what it was hiding. A node whose **id was
not unique in the book** could not have an unambiguous ref, so 16 findings were excused and the
count printed. That was convergence by exception: the id was ambiguous because
``model.anchor_of`` minted it from the heading title alone, and a repeated heading — the
per-method ``#### Effects`` shape, 58 ids across this book — gave two nodes one id, unreachable
past the first. ``model.document_anchors`` issues the anchor GitHub actually renders instead,
so the case is gone rather than pardoned, and a duplicate reappearing is now this guard's
failure like any other shared ref.
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


def ambiguous_refs(graph: Graph) -> list[str]:
    """Every ``(code, ref)`` shared by findings that are not linked as a group."""
    report = doctor.run(graph)
    groups: dict[tuple[str, str], list[doctor.Finding]] = collections.defaultdict(list)
    for finding in report.findings:
        groups[(finding.code, finding.ref)].append(finding)

    problems: list[str] = []
    for (code, ref), findings in sorted(groups.items()):
        if len(findings) < 2 or any(f.related for f in findings):
            continue
        where = ", ".join(sorted({f"{f.path}:{f.line}" for f in findings}))
        problems.append(f"{code}: {len(findings)} findings share ref {ref!r} ({where})")
    return problems


def main(argv: list[str]) -> int:
    problems = ambiguous_refs(Ostler(REPO).graph)
    if not problems:
        return 0
    print("\nFAIL check_finding_refs:", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    print(f"\n{STEER}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
