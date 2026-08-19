"""The half of an operator gate that tries to answer the block before parking on it.

`escalation.py` is the other half: what a flow writes when it stops and asks a human. This
module is what runs first, and the two are deliberately siblings, because the choice
between them is one branch and the four lanes must not each grow their own copy of it.

**A resolver may answer, and that is a narrowing of who decides, not a widening.** The rule
it operates under is that it may only *apply* a decision somebody already made and wrote
down — a record under `paths.decisions_dir`, a convention in `AGENTS.md` or an installed
skill, an acceptance criterion in the story's own spec. What it may not do is make one. The
difference is not a matter of the resolver's confidence: a question with a written answer
costs a human nothing to be asked about and teaches them nothing when they answer it the
way the document already says; a question without one is theirs by definition, and a
resolver picking a side of it buries the question instead of surfacing it.

So `answered` means "found, quoted, applied" and every other value means "parked". The
grounding is required, published in the log, and recorded in `docs/decisions/` so the
*second* run to hit the same question does not pay for it either — which is the point of
having a place at all. A resolver that answers ungrounded has not broken a check here; it
has written a decision record nobody can trace, and that is what the audit trail is for.

What has not changed is the other half of the rule this workflow is built on: a block that
cannot be answered *parks*. It does not end the run, and it does not get answered anyway
because parking is inconvenient. `Await` is still the only other way out of here.
"""
from __future__ import annotations

from pathlib import Path

from workhorse.pyflow import Workflow

from workhorse_workflows.coder.shared import paths
from workhorse_workflows.coder.shared.schemas.dev import OperatorResolution
from workhorse_workflows.kit import find_docs_root

#: What the resolver turn is given: full tool access, no clock, and the strongest model the
#: operator's config maps a tier to. It is standing in for the person who would otherwise be
#: woken, on the most consequential branch in the lane, and it is the one turn in the flow
#: whose output nothing downstream re-checks — so it is the last place to economize.
RESOLVER_POWER = "smart"


def resolver_args(
    flow: Workflow, *, block_kind: str, notes: str, docs_path: str
) -> dict[str, str]:
    """The template arguments every `prompts/resolve-operator.md` turn takes.

    One builder rather than five near-identical dict literals, for the same reason
    `escalation()` exists: the lanes differed only in `block_kind`, so a new argument —
    `decisions_dir`, when the resolver was given a place to read decisions from and write
    them to — otherwise has to be remembered at five call sites and is silently missing
    from whichever one is forgotten.

    `docs_path` is passed rather than read off `flow` because it is not one of the engine's
    ambient parameters: each coder lane declares it as its own workflow input, so `Workflow`
    does not promise it and a helper shared across the lanes must not pretend otherwise.
    """
    return {
        "story_path": flow.ctx.story_path,
        "spec_dir": flow.ctx.spec_dir,
        "decisions_dir": str(decisions_dir(docs_path, flow.repo_dir)),
        "block_kind": block_kind,
        "block_notes": notes,
    }


def decisions_dir(docs_path: str, repo_dir: str) -> Path:
    """Where this run's standing decisions live, absolute — see `paths.decisions_dir`.

    Absolute rather than repo-relative because the only consumer is a prompt argument, and
    the agent turn reading it runs with a service repo as its cwd rather than the docs root.
    """
    return paths.decisions_dir(find_docs_root(docs_path, repo_dir))


def answered(flow: Workflow, result: OperatorResolution, block_kind: str) -> bool:
    """Did the resolver settle the block itself, and say what settled it?

    The one place the `answered` token is compared, so the vocabulary lives beside the
    prompt that emits it rather than in four flows. Anything other than `answered` — a
    refusal, a truncated turn, an empty string from a response that would not parse — is
    an escalation, which is the arm that costs a round trip rather than the arm that acts.

    The grounding is logged either way and never gates the branch. Requiring a citation to
    *honour* the answer would put this module in the business of judging whether a quote
    really determines a question, which it cannot do; publishing it puts the operator in
    that business instead, which is where the judgement belongs and where a bad citation is
    visible in the run's own log.
    """
    if result.decision != "answered":
        return False
    flow.logger.info(
        "the %s block was resolved from what is already written down — %s%s",
        block_kind,
        result.summary or "no summary given",
        (
            f" (grounded in: {'; '.join(result.grounded)}"
            + (f", recorded as {result.record}" if result.record else "")
            + ")"
            if result.grounded
            else " — WITH NO GROUNDING CITED, which the prompt requires; check this one"
        ),
        extra={"activity": True},
    )
    return True


__all__ = ["RESOLVER_POWER", "answered", "decisions_dir", "resolver_args"]
