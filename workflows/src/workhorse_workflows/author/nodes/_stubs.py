"""What the author's deterministic gates return under `--dry-run`.

A dry run replaces every node body with a stand-in, and an undeclared stand-in is a
**blank** instance of the return model — which for all four validators reads `ok=False`
and for both verifiers reads `holds=False`. Those are the failing branches, and each one
routes into the operator-resolution ladder: two autonomous resolutions, then an `Await`.
An `Await` blocks until a human edits the file it wrote, so a dry run that reaches one
never returns.

So these are declared, and the blueprint's `stub=` is exactly the seam for it (see
`Blueprint.node`: "Declaring one is how a workflow turns `--dry-run` from 'every branch
takes an arbitrary path' into a real smoke test of its happy path"). Two things they do
NOT fix, both recorded as findings in the progress ledger: `--dry-run --params
operator_mode=human` sends every gate to an `Await` regardless of what a stub says, and
the driver has no "a dry run never waits" escape to fall back on.
"""
from __future__ import annotations

from workhorse_workflows.author.schemas.main import Defects, VerifyReport


def clean(*_args: object, **_kwargs: object) -> Defects:
    """`validate_story`, `check_story_grounding`, `validate_coverage`,
    `validate_artifacts` — nothing wrong with what the run wrote."""
    return Defects(ok=True)


def holds(*_args: object, **_kwargs: object) -> VerifyReport:
    """`verify_reconcile`, `verify_integrity` — the graph reconciles and links up."""
    return VerifyReport(holds=True)


__all__ = ["clean", "holds"]
