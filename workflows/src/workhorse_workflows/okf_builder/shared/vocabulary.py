"""The check vocabulary, rendered for a prompt.

A repair turn writes `verify:` bullets, and doctor parses them against `ostler.checks` —
one closed vocabulary with fixed argument names. Telling the prompt where the list lives is
not enough: the first live backfill produced `count(subject=…, expected=1)` (the argument is
`equals`) and `visible(locator="PDFEngine output", …)` for a Go function returning bytes,
both of which re-entered the book as fresh `unparsed-check` findings. The vocabulary is
small enough to inline, so the prompt carries it and the turn has nothing to guess.

It is rendered from `checks.CHECKS` rather than transcribed, so a check added to ostler
reaches the prompt in the same commit — a transcription would drift silently, and the drift
would look exactly like the defect above.
"""

from __future__ import annotations

from ostler import checks


def check_vocabulary() -> str:
    """Every check, its signature, and the defect it exists to exclude — one per line.

    `excludes` is included on purpose: it is the sentence that says *why* one check is not
    another, which is the judgment a repair turn is actually being asked to make.
    """
    return "\n".join(f"- `{spec.signature()}` — excludes: {spec.excludes}" for spec in checks.CHECKS)
