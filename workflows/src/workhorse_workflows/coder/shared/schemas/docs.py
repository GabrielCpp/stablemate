"""The docs flow's models: the OKF pre-gate, the context classifier, the author, the gates.

One divergence, and it is the same one `dev` and `fix_ci` already carry.
`classify-documentation-context.py` took a JSON-**encoded string** of source roots and
emitted another one, which `build-qa-okf-context.py` then decoded. Both ends existed because
a workflow var is a string; a state parameter is a value, so `source_roots` is a `list[str]`
here and the encode/decode pair disappears. Nothing on disk carried the encoded form.
"""
from __future__ import annotations

from typing import ClassVar, Literal

from workhorse_workflows.coder.shared.schemas._base import CoderResult, Finding
from workhorse_workflows.kit.telemetry import progress_verdict


class OkfDetection(CoderResult):
    """`detect-okf-docs.py` — are this repo's docs managed by an OKF graph at all?

    The cheap pre-gate in front of an agent turn: most repos the coder runs against do not
    use ostler, and `document_story` has nothing to do there. `has_okf` is `yes`, `no` or
    `invalid`, and each arm is distinct — `no` ends the flow successfully as
    "not applicable", `invalid` fails it, because a graph that is configured and will not
    load is a broken repo rather than an unmanaged one.
    """

    has_okf: str = "no"
    features_root: str = ""
    reason: str = ""


class ContextClassification(CoderResult):
    """`classify-documentation-context.py` — deterministic diff mapping, or semantic review?

    `mode` is `local` when every affected source root lives inside the docs repo's own git
    worktree, which is what makes a diff-to-OKF mapping possible; `semantic` otherwise, and
    then doctor plus an independent review turn is the authority instead. Anything else fails
    the flow — the YAML's `default:` arm — because a mode nothing recognises means the
    classifier itself is broken.
    """

    mode: str = "semantic"
    source_roots: list[str] = []
    notes: str = ""


class WorktreeSnapshot(CoderResult):
    """What was already dirty in the repo when this story started.

    Each entry is `"<repo-relative path>\\0<sha256 of its bytes>"`, for every path git
    reported as modified or untracked before the story's first dev turn. The grounding gate
    subtracts these — and only while they are still byte-identical — from the changed
    production units it holds the story responsible for.

    It exists because the diff the gate reads is `HEAD..WORKTREE`, and the workflow's own
    contract is that a story ends in a commit. A story that dies before its commit — a docs
    failure, a QA give-up, a crash — leaves its production code in the tree, and every story
    selected after it then inherits symbols it never wrote and cannot document. That is a
    cascade: one abandoned story disables the docs gate for the whole rest of the repo.
    """

    entries: list[str] = []
    notes: str = ""


class DocumentationResult(CoderResult):
    """`docs/prompts/document-story.md` — the story folded into the as-built OKF book.

    `status` is `documented`, `not_required` or `blocked`, and a blank takes the YAML's
    `default:` arm, which is `blocked` — an author that did not speak has not documented
    anything. `nodes` is the OKF node ids it claims to have touched, and the grounding gate
    below checks that claim against the diff rather than taking it.
    """

    status: str = ""
    nodes: list[str] = []
    notes: str = ""


class DocumentationGate(CoderResult):
    """`verify-story-documentation.py` — the fail-closed conformance and grounding gate.

    `status` is `passed` or `invalid`; a blank takes the YAML's `default:` arm, which is the
    rework guard, so nothing but an explicit pass reaches the reviewer. The two counts are
    diagnostics: how many changed production units the packet saw, and how many doctor errors
    landed on a node this story actually affected.

    `failures` is `notes` in machine-readable form: one stable identity per discrete
    failure — `G:{path::symbol}` for an ungrounded reference, `E:{ref}:{line}:{code}` for a
    doctor error, `S:{slug}` for a structural refusal. `notes` is the author's rework brief
    and its prose is load-bearing; this is the half a *later* pass can be compared against,
    which is what distinguishes a rework that closed findings from one that handed the same
    ones back. Empty on `passed`.
    """

    status: str = ""
    notes: str = ""
    changed_code_count: int = 0
    doctor_error_count: int = 0
    failures: list[str] = []


class DocumentationObligations(CoderResult):
    """`documentation_obligations` — the grounding worklist handed to the author up front.

    `refs` is the same list the grounding gate would report if the author wrote nothing:
    each changed production reference, spelled the way the inventory spells it, that no
    node's `code:` bullet owns yet. Advisory — nothing branches on it, and an empty list
    with a `notes` reason means it could not be computed, never that the book is complete.
    """

    refs: list[str] = []
    notes: str = ""


class DocumentationFinding(Finding):
    """One semantic documentation review finding handed back to the author.

    `target`/`issue`/`repair` come from `Finding`, which is the shared evidence contract:
    a finding carrying a target and a repair is something a fixer can act on, and one
    carrying neither is what a block hands to the operator instead of round the loop again.

    `kind` is intentionally closed: it lets static tests and later deterministic tooling tell a
    node-type problem from an overclaim rather than scraping prose.
    """

    id: str = ""
    kind: Literal[
        "node-type",
        "missing-node",
        "flow-coverage",
        "overclaim",
        "bullet-granularity",
        "grounding",
        "verify-overclaim",
        "author-decision",
    ] = "overclaim"


class DocumentationReview(CoderResult):
    """`docs/prompts/review-story-documentation.md` — an independent read of what was written.

    `status` is `approved`, `revise` or `blocked`. A blank takes `revise`, the YAML's
    `default:`, which spends a rework rather than approving or failing. A `revise` verdict
    must carry structured findings; the free-form `notes` is a summary, not the repair
    contract.
    """

    status: str = ""
    findings: list[DocumentationFinding] = []
    notes: str = ""


class DocsProgress(CoderResult):
    """What each gate last decided, and whether the rework it forced was worth spending.

    The docs flow's counterpart to `QaLoop`'s recorded verdicts, and it exists for the same
    reason: the budget counters are a cost, not a diagnosis. `docs.rework=3` says a story
    was expensive; `docs.rework=3` beside `docs.gate_progress_verdict=stalled` says the
    author was handed the same brief three times and never acted on it, while `churned`
    says it closed each brief and the budget was simply too small. Those want opposite
    interventions, and nothing in the flow could tell them apart before this.

    Nothing branches on any field here — it is a state parameter, which is what makes it
    checkpointed, and being checkpointed is the whole point: comparing this pass to the one
    before it requires the previous pass's findings to survive a resume.

    The two lanes are kept apart because they are disjoint. `review` only runs when the
    gate passed, so a pass produces grounding failures *or* review findings, never both;
    comparing a gate-failure pass against a reviewer-revise pass would score every switch
    between lanes as nonsense.
    """

    gate_verdict: str = ""  #: passed | invalid
    review_disposition: str = ""  #: approved | revise | blocked
    gate_progress_verdict: str = ""  #: see `kit.telemetry.progress_verdict`
    review_progress_verdict: str = ""  #: idem, over the semantic lane

    gate_failures: int = 0
    review_findings: int = 0

    #: The identities the last *failing* pass of each lane left open — the baseline the next
    #: pass is judged against. Empty means the lane has never failed, which is distinct from
    #: a lane that failed with nothing outstanding (impossible by construction: a failing
    #: gate names at least one failure, and a `revise` carrying no findings is rejected).
    gate_ids: list[str] = []
    review_ids: list[str] = []

    #: Consecutive repair laps that have run on the story's session chain, so `repair` can
    #: end a conversation that has grown longer than it is worth. Reset to 0 whenever the
    #: chain is, which is what makes it *consecutive* rather than a total. It lives here
    #: because it must survive a resume: a counter kept anywhere else would restart at 0
    #: mid-loop and give a stale chain a fresh budget.
    chain_laps: int = 0

    #: Closed vocabularies, so the label cardinality they add is bounded. Every name ends in
    #: a suffix `groom profile` recognises as a verdict dimension.
    VERDICT_LABELS: ClassVar[tuple[str, ...]] = (
        "gate_verdict",
        "review_disposition",
        "gate_progress_verdict",
        "review_progress_verdict",
    )

    #: Reported as attempt dimensions beside the budgets. Both are counts of what a pass
    #: left outstanding, never a signed delta — `groom profile` classifies an attempt
    #: dimension with `str.isdigit`, so a negative value would silently render nowhere.
    COUNT_LABELS: ClassVar[tuple[str, ...]] = ("gate_failures", "review_findings")

    def after_gate(self, gate: DocumentationGate) -> DocsProgress:
        """Record what the deterministic grounding gate just decided.

        A `passed` gate clears the lane: no failures, no baseline, and `cleared` as the
        verdict. The verdict is forgotten together with the findings it summarised, the same
        invariant `QaLoop.cleared()` keeps — leaving one behind would let a later span claim
        a failure that had already been closed.
        """
        ids = list(gate.failures)
        return self.model_copy(
            update={
                "gate_verdict": gate.status or "invalid",
                "gate_failures": len(ids),
                "gate_progress_verdict": progress_verdict(self.gate_ids or None, ids),
                "gate_ids": ids,
            }
        )

    def after_review(self, review: DocumentationReview) -> DocsProgress:
        """Record what the semantic reviewer just decided.

        Only a `revise` leaves findings outstanding: `approved` and `blocked` both end the
        flow, so neither leaves a worklist for a next pass to be judged against.
        """
        ids = [finding.id for finding in review.findings] if review.status == "revise" else []
        return self.model_copy(
            update={
                "review_disposition": review.status or "revise",
                "review_findings": len(ids),
                "review_progress_verdict": progress_verdict(self.review_ids or None, ids),
                "review_ids": ids,
            }
        )


class DocsResult(CoderResult):
    """What the docs flow hands back: `passed`, `not_applicable` or `blocked`.

    The first two are the ones every caller accepts. `blocked` is the author's or the
    reviewer's refusal — the book cannot be made true of this code. The main pass and a
    required post-mutation recheck contain it by failing that story and taking the next one;
    the `failed story` call site still treats it as fatal.

    Everything else still raises out of the flow rather than returning, because the YAML's
    `documentation_failed` was a `type: fail` — so `failed`, the `default:` the four call
    sites declared, is only ever reached when the sub-flow produced no value at all.
    """

    status: str = "failed"
    notes: str = ""
    authored_nodes: list[str] = []


__all__ = [
    "ContextClassification",
    "DocsProgress",
    "DocsResult",
    "DocumentationFinding",
    "DocumentationGate",
    "DocumentationResult",
    "DocumentationReview",
    "OkfDetection",
    "WorktreeSnapshot",
]
