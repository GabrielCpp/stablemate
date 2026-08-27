"""The docs flow's models: the OKF pre-gate, the context classifier, the author, the gates.

One divergence, and it is the same one `dev` and `fix_ci` already carry.
`classify-documentation-context.py` took a JSON-**encoded string** of source roots and
emitted another one, which `build-qa-okf-context.py` then decoded. Both ends existed because
a workflow var is a string; a state parameter is a value, so `source_roots` is a `list[str]`
here and the encode/decode pair disappears. Nothing on disk carried the encoded form.
"""
from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, Field

from workhorse_workflows.coder.shared.schemas._base import CoderResult, Finding
from workhorse_workflows.kit.telemetry import ProgressVerdict, progress_verdict


class OkfDetection(CoderResult):
    """`detect-okf-docs.py` — are this repo's docs managed by an OKF graph at all?

    The cheap pre-gate in front of an agent turn: most repos the coder runs against do not
    use ostler, and `document_story` has nothing to do there. Each arm is distinct — `no`
    ends the flow successfully as "not applicable", `invalid` fails it, because a graph
    that is configured and will not load is a broken repo rather than an unmanaged one.

    Python-produced, so the field carries the pessimistic default: a node that returned
    without deciding has found no book, which is the arm that costs nothing.
    """

    has_okf: Literal["yes", "no", "invalid"] = "no"
    features_root: str = ""
    reason: str = ""


class ContextClassification(CoderResult):
    """`classify-documentation-context.py` — deterministic diff mapping, or semantic review?

    `local` when every affected source root lives inside the docs repo's own git worktree,
    which is what makes a diff-to-OKF mapping possible; `semantic` when they do not, and
    then doctor plus an independent review turn is the authority instead.

    `error` is neither, and it is the reason this is a three-word vocabulary. Reading the
    worktree can *fail* — a git binary that is not there, a repository the process cannot
    open — and answering that with `semantic` silently turns the grounding gate off for
    the rest of the story while reporting a mode the flow believes. An error is reported
    as one, and the flow refuses rather than gates half a book.
    """

    mode: Literal["local", "semantic", "error"] = "semantic"
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

    Agent-produced, so `status` is required and closed: there is no blank to take a
    default arm, because a reply that does not carry one of these three words is a parse
    failure the runner answers with a retry turn.

    `nodes` is the OKF node ids the author claims to have touched. Advisory: the gate
    reads the book's own diff for the nodes this story is answerable for, and adds these
    to it rather than believing them — an author that names nothing has still edited
    whatever it edited.
    """

    status: Literal["documented", "not_required", "blocked"] = Field(
        description="`documented` when the current contracts are updated and `doctor` "
        "reports no error on the affected nodes. `not_required` needs both a precise "
        "explanation of why no observable contract changed and that every changed "
        "production file was already directly grounded — a grounding bullet you had to add "
        "makes the answer `documented`. `blocked` when the book cannot be made true of "
        "this code without a decision that is not yours.",
    )
    nodes: list[str] = Field(
        default=[],
        description="Every OKF node you edited, by exact graph identity with its section "
        "anchor preserved. Empty for `not_required`.",
    )
    notes: str = Field(
        default="",
        description="What you changed and why, in one or two sentences. Report unrelated "
        "pre-existing doctor findings here rather than rewriting unrelated books.",
    )


class DocumentationGate(CoderResult):
    """`verify-story-documentation.py` — the fail-closed conformance and grounding gate.

    Python-produced, and the default is the rework guard, so nothing but an explicit pass
    reaches the reviewer. The two counts are
    diagnostics: how many changed production units the packet saw, and how many doctor errors
    landed on a node this story actually affected.

    `failures` is `notes` in machine-readable form: one stable identity per discrete
    failure — `G:{path::symbol}` for an ungrounded reference, `E:{ref}:{line}:{code}` for a
    doctor error, `S:{slug}` for a structural refusal. `notes` is the author's rework brief
    and its prose is load-bearing; this is the half a *later* pass can be compared against,
    which is what distinguishes a rework that closed findings from one that handed the same
    ones back. Empty on `passed`.
    """

    status: Literal["passed", "invalid"] = "invalid"
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

    `kind` is intentionally closed *and required*: it lets static tests and later
    deterministic tooling tell a node-type problem from an overclaim rather than scraping
    prose, and a default would have quietly filed every finding whose kind the reviewer
    omitted under whichever word the default named.
    """

    id: str = Field(
        default="",
        description="A stable handle for this finding — `D1`, `D2` — reused when you "
        "restate it on a later pass.",
    )
    kind: Literal[
        "node-type",
        "missing-node",
        "flow-coverage",
        "overclaim",
        "bullet-granularity",
        "grounding",
        "verify-overclaim",
        "author-decision",
    ] = Field(description="What class of defect this is, so the repair can be routed.")


class DocumentationReview(CoderResult):
    """`docs/prompts/review-story-documentation.md` — an independent read of what was written.

    Agent-produced, so `status` is required and closed, for the reason
    `DocumentationResult` gives. A `revise` verdict must carry structured findings; the
    free-form `notes` is a summary, not the repair contract.
    """

    status: Literal["approved", "revise", "blocked"] = Field(
        description="`revise` only with at least one structured finding. `blocked` only "
        "when convergence needs a product or author decision. Never approve on the promise "
        "of a later documentation update.",
    )
    findings: list[DocumentationFinding] = Field(
        default=[],
        description="The repair contract the author works from — empty on `approved`.",
    )
    notes: str = Field(
        default="",
        description="A one or two sentence summary; the findings list, not this, is what "
        "the author repairs from.",
    )


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

    #: Each verdict keeps `""` in its union: this is a threaded state parameter, so a
    #: resume arrives holding whatever the checkpoint before it wrote, and "no pass of this
    #: lane has decided anything yet" is a value the model has to be able to hold.
    gate_verdict: Literal["", "passed", "invalid"] = ""
    review_disposition: Literal["", "approved", "revise", "blocked"] = ""
    gate_progress_verdict: ProgressVerdict | Literal[""] = ""
    review_progress_verdict: ProgressVerdict | Literal[""] = ""

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
                "gate_verdict": gate.status,
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
                "review_disposition": review.status,
                "review_findings": len(ids),
                "review_progress_verdict": progress_verdict(self.review_ids or None, ids),
                "review_ids": ids,
            }
        )


class DocsLoop(BaseModel):
    """Everything one documentation pass carries into the next, as one state parameter.

    A bare `BaseModel` rather than a `CoderResult`, for the reason `ReviewLoop` gives:
    nothing returns it and no agent fills it in, so it wants neither the dropped nulls nor
    the `blocked` reading those buy.

    What it holds travelled as eight keyword arguments through nine signatures, and
    every state that merely passed them along had to name all eight — which is how
    `_blocked` came to omit one of them and reset the reviewer's budget by accident. A
    bundle makes a reset something written down (`model_copy(update=...)`) rather than
    something spelled by omission.
    """

    #: Grounding-gate failures spent on this story.
    rework: int = 0

    #: Reviewer revisions, counted separately — see `Docs._rework` for the run that forced
    #: the split. Reset when a ratified answer arrives, because the passes before it were
    #: spent arguing about a question that had no answer yet.
    review_rework: int = 0

    #: Trips through the author gate, resolver answers included. Never reset: it is what
    #: walks a lapping resolver toward a person, the same shape `ReviewLoop.blocks` has.
    blocks: int = 0

    #: The last gate's rework brief and the last review's findings, carried rather than
    #: reset: a second gate failure still shows the author what the reviewer said the first
    #: time.
    gate_notes: str = ""
    review_notes: str = ""

    #: The grounding worklist as it stands — what `start` computed, minus what each pass
    #: closed. Shrinks, which is right for an author being told what is left to do.
    obligations: tuple[str, ...] = ()

    #: Every node any pass named, accumulated rather than replaced. A repair lap that
    #: correctly concludes a finding needs no edit names nothing, and scoring the gate on
    #: that one lap read it as an author that had never spoken.
    authored_nodes: tuple[str, ...] = ()

    #: What each gate last decided, and whether the rework it forced bought anything.
    progress: DocsProgress = Field(default_factory=DocsProgress)

    #: Repair turns cut at their wall-clock budget, consecutive or not. Never reset: a turn
    #: that overran twice on one story spent an hour and a half producing no reply either
    #: time, and the second one is not a fresh start just because a gate pass came between.
    overruns: int = 0

    #: Both budgets, as span dimensions. Bare names here; `Docs.state_labels` supplies the
    #: `docs.` prefix.
    COUNT_LABELS: ClassVar[tuple[str, ...]] = (
        "rework",
        "review_rework",
        "blocks",
        "overruns",
    )


class RepairOverran(BaseModel):
    """What a repair turn cut at its wall-clock budget leaves in the checkpoint.

    A cut turn produced no reply, so there is no author status to record — and minting one
    is the defect this model exists to remove. The flow used to hand the gate a
    `DocumentationResult(status="documented")` it had written itself, which is a claim
    nobody made: downstream QA reads `documented` as an author's word that the story is in
    the book, and a turn that was stopped mid-edit has said nothing of the kind.

    So the outcome recorded is the one thing Python actually knows — that the turn ran out
    of wall clock — and the flow re-dispatches the repair rather than gating a partial book
    on a fabricated success.
    """

    status: Literal["overran"] = "overran"

    #: Which overrun this is, so a checkpoint says whether the turn is cut once or reliably.
    lap: int = 0

    notes: str = ""


#: How a documentation pass ended, as the caller reads it. Named because `Coder` and its
#: tests both hand a value in, and an alias is what keeps the four words in one place.
DocsStatus = Literal["passed", "not_applicable", "blocked", "failed"]


class DocsResult(CoderResult):
    """What the docs flow hands back: `passed`, `not_applicable` or `blocked`.

    The first two are the ones every caller accepts. `blocked` is the author's or the
    reviewer's refusal — the book cannot be made true of this code. The main pass and a
    required post-mutation recheck contain it by failing that story and taking the next one;
    the `failed story` call site still treats it as fatal.

    Everything else raises out of the flow rather than returning, so `failed` — the
    pessimistic default this Python-produced status carries — is only ever reached when the
    sub-flow produced no value at all.
    """

    status: DocsStatus = "failed"
    notes: str = ""
    authored_nodes: list[str] = []


__all__ = [
    "ContextClassification",
    "DocsLoop",
    "DocsStatus",
    "DocsProgress",
    "DocsResult",
    "DocumentationFinding",
    "DocumentationGate",
    "DocumentationResult",
    "DocumentationReview",
    "OkfDetection",
    "RepairOverran",
    "WorktreeSnapshot",
]
