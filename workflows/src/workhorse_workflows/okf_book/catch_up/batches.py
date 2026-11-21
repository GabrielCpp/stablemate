"""How the work of one book is cut into batches of a fixed number of notes, and how the owner's respect of a batch is counted."""
from __future__ import annotations

from collections.abc import Sequence

from workhorse_workflows.okf_book.catch_up.models import BatchOutcome, BatchPlan, FormatMove, ModuleCheck
from workhorse_workflows.okf_book.catch_up.register import split_note, undeclined


def ordered(notes: Sequence[str]) -> list[str]:
    """The notes kind by kind, the kinds in the order the check first printed them and the notes of a kind in the order it printed them."""
    groups: dict[str, list[str]] = {}
    for note in notes:
        groups.setdefault(split_note(note)[1], []).append(note)
    return [note for group in groups.values() for note in group]


def plan_batch(number: int, checks: Sequence[ModuleCheck], register: Sequence[str], size: int) -> BatchPlan:
    """The batch that follows what the checks say: every blocking finding, and the first *size* of the notes no register entry covers."""
    pending = undeclined([note for check in checks for note in check.noted], register)
    return BatchPlan(
        number=number,
        checks=[check.model_copy(update={"noted": []}) for check in checks if check.red],
        findings=sum(check.findings for check in checks if check.red),
        notes=ordered(pending)[: max(size, 1)],
        pending=pending,
    )


def batch_outcome(plan: BatchPlan, register: Sequence[str], move: FormatMove, laps: int) -> BatchOutcome:
    """How the owner left the batch, read from the check after it: the items listed that are gone or declined, and the notes outside the list that are gone."""
    open_after = set(undeclined(plan.after, register))
    done = plan.findings + sum(1 for note in plan.notes if note not in open_after)
    outside = sum(1 for note in set(plan.pending) - set(plan.notes) if note not in plan.after)
    return BatchOutcome(number=plan.number, asked=plan.asked, done=done, outside=outside, laps=laps, minutes=plan.minutes, calls=move.calls, journeys=move.journeys, exit_code=move.exit_code)
