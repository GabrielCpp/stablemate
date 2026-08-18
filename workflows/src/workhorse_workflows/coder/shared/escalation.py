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
from collections.abc import Sequence

from workhorse.pyflow import Workflow

from workhorse_workflows.coder.shared import paths
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas._base import Finding
from workhorse_workflows.coder.shared.schemas.dev import OperatorGate, OperatorResolution

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
    findings: list[Finding] | None = None,
) -> OperatorGate:
    """Build the gate body for one escalation, preserving what is already on disk.

    `number` is the escalation's ordinal *for this story*, taken from the counter the
    escalating flow already keeps (`plan_blocks`, `review_blocks`, `QaLoop.escalations`).
    `tried` and `summary` are the resolver's, and are empty on the `human`/`operator` arm
    where no resolver ran — the gate then says so rather than implying nothing was tried.

    `findings` is the producing node's own structured evidence, when it had any. A block
    that reaches this function *with* findings is one nobody could route — every finding a
    fixer could act on has already been sent to that fixer — so what is left is either
    evidence with no owner or a defect the lane could not repair with it. Either way the
    operator needs to see the specifics rather than re-derive them from prose.

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
    lines += _section(
        "What the node found",
        "\n".join(
            f"- `{finding.target or '(no target given)'}` — {finding.issue or '(no issue given)'}"
            + (f" → {finding.repair}" if finding.repair else "")
            for finding in (findings or [])
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


def escalation(
    flow: Workflow,
    *,
    block_kind: str,
    where: str,
    notes: str,
    number: int = 1,
    result: OperatorResolution | None = None,
    findings: Sequence[Finding] = (),
) -> OperatorGate:
    """The gate body for one block, from any lane.

    Four flows had a private `_escalation` differing only in the two strings `block_kind`
    and `where` and in which counter they read for `number`. That was tolerable while
    blocking was something three specific gates did; it is not once *every* node can say
    "not possible", because a fifth copy is then a copy per node rather than per lane.

    So the two strings are parameters and the story identity comes off the flow, which is
    the part that was never lane-specific: every coder flow carries the same `ctx` and
    parks on the same `context.md` beside the same story.
    """
    return flow.call(
        compose_escalation,
        story_path=flow.ctx.story_path,
        story_slug=flow.ctx.story_slug,
        spec_dir=flow.ctx.spec_dir,
        run_dir=str(flow.run_dir),
        number=number,
        block_kind=block_kind,
        block_notes=notes,
        where=where,
        tried=list(result.tried) if result else [],
        summary=result.summary if result else "",
        findings=list(findings),
    )


__all__ = ["compose_escalation", "escalation"]
