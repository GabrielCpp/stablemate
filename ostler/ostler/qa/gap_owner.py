"""Who owns each compile gap kind: the book's author, the tooling, or the environment.

The owner is where the fix lands, not how bad the gap is. A gap the book can repair
with an edit (a missing check, an unreadable bullet, an unarranged claim) is owned by
the book. A gap the compiler or harness cannot build yet (an unbuilt driver, a capture
no builder emits) is owned by tooling. A gap that names a missing runtime input (an
unresolved address, an unavailable checkout) is owned by the environment.

An unclassified kind is a finding in itself: the assessment must never default an
unknown gap to a passing owner.
"""

from __future__ import annotations

BOOK = "book"
TOOLING = "tooling"
ENVIRONMENT = "environment"

_BOOK_KINDS = frozenset({
    "no-verify-declared",
    "unstated-claim-combiner",
    "unparsed-check-bullet",
    "unparsed-fixture",
    "unparsed-capture-bullet",
    "undetermined-provided-fact",
    "uncompilable-claim",
    "unresolved-precondition",
    "unresolved-extends",
    "unreachable-screen",
    "unidentifiable-screen",
    "unreachable-from-launch",
    "undeclared-launch-screen",
    "undeclared-entry-url",
    "undeclared-bundle-id",
    "undeclared-check-locator",
    "screen-preconditions-undeclared",
    "unarranged-scenario",
    "unarranged-journey",
    "unarranged-state",
    "unarranged-interaction-precondition",
    "unarranged-request-body",
    "precondition-discharged-by-arrangement",
    "deletes-shared-fixture",
    "browser-fixture-off-browser",
    "fixture-launch-screen-conflict",
    "invalid-http-method",
    "unread-condition",
})

_TOOLING_KINDS = frozenset({
    "needs-target-backend",
    "needs-multi-target-runtime",
    "needs-snapshot",
    "needs-out-of-band-observation",
    "needs-trigger-action",
    "uncaptured-declaration",
    "unarrangeable-server-fault",
})

_ENVIRONMENT_KINDS = frozenset({
    "unresolved-runtime-input",
})


def gap_owner(kind: str) -> str | None:
    """The party that can fix a gap of *kind*: `book`, `tooling`, or `environment`.

    `None` when the kind is not classified — an assessment failure, never a
    default success.
    """
    if kind in _BOOK_KINDS:
        return BOOK
    if kind in _TOOLING_KINDS:
        return TOOLING
    if kind in _ENVIRONMENT_KINDS:
        return ENVIRONMENT
    return None
