"""The body a coder flow writes when it stops and asks a human."""
from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from workhorse.pyflow import Workflow

from workhorse_workflows.coder.shared import paths
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas._base import Finding
from workhorse_workflows.coder.shared.schemas.dev import OperatorGate, OperatorResolution
from workhorse_workflows.coder.shared.schemas.story import StoryPaths

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
    """Build the gate body for one escalation, preserving what is already on disk."""
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
    story: StoryPaths | None = None,
) -> OperatorGate:
    """The gate body for one block, from any lane."""
    ident: StoryPaths | Any = story if story is not None else flow.ctx
    return flow.call(
        compose_escalation,
        story_path=ident.story_path,
        story_slug=ident.story_slug,
        spec_dir=ident.spec_dir,
        run_dir=str(flow.run_dir),
        number=number,
        block_kind=block_kind,
        block_notes=notes,
        where=where,
        tried=list(result.tried) if result else [],
        summary=result.summary if result else "",
        findings=list(findings),
    )


def context_path(flow: Workflow, story_path: str = "") -> Path:
    """The file an `Await` writes its questions into: `<story-folder>/context.md`."""
    return paths.story_context_path(story_path or flow.ctx.story_path)


__all__ = ["compose_escalation", "context_path", "escalation"]
