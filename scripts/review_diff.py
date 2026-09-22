"""Cut a diff into reviewer-sized batches, and name what cannot fit in one."""

from __future__ import annotations

from dataclasses import dataclass

from review_verdict import Finding

CHARS_PER_TOKEN = 4


@dataclass(frozen=True)
class FileDiff:
    path: str
    text: str


@dataclass(frozen=True)
class ReviewBatches:
    batches: tuple[str, ...]
    too_large: tuple[Finding, ...]


def split_diff(diff: str) -> list[FileDiff]:
    pieces: list[FileDiff] = []
    for body in f"\n{diff}".split("\ndiff --git ")[1:]:
        header = body.split("\n", 1)[0]
        pieces.append(FileDiff(path=header.rsplit(" b/", 1)[-1], text=f"diff --git {body}\n"))
    return pieces


def _too_large(path: str, problem: str) -> Finding:
    return Finding(file=path, line=1, rule="too-large", problem=problem)


def _batches(pieces: list[FileDiff], budget_chars: int) -> list[str]:
    batches: list[str] = []
    current = ""
    for piece in pieces:
        if current and len(current) + len(piece.text) > budget_chars:
            batches.append(current)
            current = ""
        current += piece.text
    if current:
        batches.append(current)
    return batches


def pack(pieces: list[FileDiff], budget_tokens: int, max_batches: int) -> ReviewBatches:
    budget_chars = budget_tokens * CHARS_PER_TOKEN
    oversized = [piece for piece in pieces if len(piece.text) > budget_chars]
    if oversized:
        return ReviewBatches(
            batches=(),
            too_large=tuple(
                _too_large(
                    piece.path,
                    f"its diff is about {len(piece.text) // CHARS_PER_TOKEN} tokens, over the"
                    f" {budget_tokens}-token review budget. Split the change so each file's diff fits.",
                )
                for piece in oversized
            ),
        )
    batches = _batches(pieces, budget_chars)
    if len(batches) > max_batches:
        problem = (
            f"the change needs {len(batches)} review batches, over the cap of {max_batches}."
            " Land it in smaller commits."
        )
        return ReviewBatches(batches=(), too_large=(_too_large(pieces[0].path, problem),))
    return ReviewBatches(batches=tuple(batches), too_large=())
