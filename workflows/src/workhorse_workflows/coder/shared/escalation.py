"""The body a coder flow writes when it stops and asks a human.

Every escalation in this package ends at the same two lines: an `Await` on the story's
`context.md`, and a human — or, more often, an agent babysitting the run — reading that
file through groom's outbox. What the reader used to get was one of two unhelpful things:
the producer's block summary alone (the `human`/`operator` arm, which passes `notes`), or
*nothing at all* — the auto-resolver arms passed `questions=""` on purpose, because
`Await` writes its `questions` over the file with `write_text` and would otherwise erase
the note the escalating resolver had just written there.

So the choice was between destroying the investigation and publishing no question. This
module removes it: the flow composes the whole context file itself — the resolver's note
included, verbatim — and hands that to `Await`, which `gates.format_operator_gate` then
passes through untouched because it already carries a `STATUS:` line.

The order is the order a reader needs it in: which escalation this is, what blocked, what
has already been ruled out, what would unblock it, and where everything lives. The `tried`
list is the load-bearing one — without it the answerer re-runs every dead end the resolver
already paid for, which on an unbounded-timeout resolver turn is the expensive half.

There is deliberately no cap on escalations here. A repeat is made *visible* by the
counter and left to whoever answers; a run-side backstop would turn "ask again" into
"give up", and the second escalation is often the one that gets a real answer.
"""
from __future__ import annotations

import logging

from workhorse_workflows.coder.shared import paths
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.dev import OperatorGate

#: How much of the existing `context.md` is carried into the new body. Each escalation
#: embeds the last one, so an uncapped copy grows quadratically over a story that blocks
#: five times — and the middle of a long file is exactly where the useful part is not.
#: The head keeps the first escalation and the answer it got; the tail keeps the most
#: recent, which includes the note the resolver wrote moments ago.
HISTORY_HEAD = 4000
HISTORY_TAIL = 8000


def _history(text: str) -> str:
    """The prior context file, bounded, with the elision said out loud."""
    body = text.strip()
    if len(body) <= HISTORY_HEAD + HISTORY_TAIL:
        return body
    dropped = len(body) - HISTORY_HEAD - HISTORY_TAIL
    return (
        f"{body[:HISTORY_HEAD]}\n\n"
        f"_… {dropped} characters elided — read the file itself for the whole history …_\n\n"
        f"{body[-HISTORY_TAIL:]}"
    )


def _section(title: str, body: str) -> list[str]:
    """A `### title` block, or nothing when there is nothing to put under it."""
    body = body.strip()
    return [f"### {title}", "", body, ""] if body else []


@blueprint.node
def compose_escalation(
    logger: logging.Logger,
    story_path: str = "",
    story_slug: str = "",
    spec_dir: str = "",
    run_dir: str = "",
    number: int = 0,
    block_kind: str = "",
    block_notes: str = "",
    where: str = "",
    tried: list[str] | None = None,
    summary: str = "",
) -> OperatorGate:
    """Build the gate body for one escalation, preserving what is already on disk.

    `number` is the escalation's ordinal *for this story*, taken from the counter the
    escalating flow already keeps (`plan_blocks`, `review_blocks`, `QaLoop.escalations`).
    `tried` and `summary` are the resolver's, and are empty on the `human`/`operator` arm
    where no resolver ran — the gate then says so rather than implying nothing was tried.

    The existing file is read here rather than by the caller because reading it is the
    whole reason this is a node: it is the one part of the body that is not already in the
    flow's hands.
    """
    context = paths.story_context_path(story_path)
    prior = context.read_text(encoding="utf-8") if context.exists() else ""

    story = story_slug or story_path or "(unknown story)"
    lines = [
        "STATUS: AWAITING_OPERATOR",
        "",
        "## Questions from the agent",
        "",
        f"**Escalation #{number or 1} for story `{story}`.**",
        "",
    ]
    lines += _section(
        f"What blocked — {block_kind or 'unknown'} stage{f', {where}' if where else ''}",
        block_notes or "_(the producer gave no notes)_",
    )
    lines += _section(
        "What the resolver tried and ruled out",
        "\n".join(f"- {item}" for item in (tried or []))
        or (
            "_(no auto-resolver ran — this run is in `human`/`operator` mode, so nothing "
            "has been attempted on your behalf)_"
        ),
    )
    lines += _section("What would unblock it, in the resolver's words", summary)
    lines += _section(
        "Where everything is",
        "\n".join(
            f"- {label}: `{value}`"
            for label, value in (
                ("story", story_path),
                ("spec dir", spec_dir),
                ("run dir", run_dir),
                ("this file", str(context)),
            )
            if value
        ),
    )
    history = _history(prior)
    if history:
        lines += [
            "### Earlier in this file — previous escalations, and the answers they got",
            "",
            history,
            "",
        ]
    logger.info(
        "escalation #%s for %s: %s block, %s tried",
        number or 1,
        story,
        block_kind or "unknown",
        len(tried or []),
        extra={"activity": True},
    )
    # The embedded history carries `STATUS:` lines of its own, and that is safe by
    # construction: every reader and writer in `workhorse.gates` matches the *first* one,
    # which is the line above. A quoted history therefore stays history.
    body = "\n".join(lines).rstrip() + "\n"
    return OperatorGate(body=body, number=number or 1)


__all__ = ["compose_escalation"]
