"""The docs flow's models: the OKF pre-gate, the context classifier, the author, the gates.

One divergence, and it is the same one `dev` and `fix_ci` already carry.
`classify-documentation-context.py` took a JSON-**encoded string** of source roots and
emitted another one, which `build-qa-okf-context.py` then decoded. Both ends existed because
a workflow var is a string; a state parameter is a value, so `source_roots` is a `list[str]`
here and the encode/decode pair disappears. Nothing on disk carried the encoded form.
"""
from __future__ import annotations

from typing import Literal

from workhorse_workflows.coder.shared.schemas._base import CoderResult


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
    """`prompts/document-story.md` — the story folded into the as-built OKF book.

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


class DocumentationFinding(CoderResult):
    """One semantic documentation review finding handed back to the author.

    `kind` is intentionally closed: it lets static tests and later deterministic tooling tell a
    node-type problem from an overclaim rather than scraping prose.
    """

    id: str = ""
    kind: Literal[
        "node-type",
        "missing-node",
        "flow-coverage",
        "overclaim",
        "grounding",
        "verify-overclaim",
        "author-decision",
    ] = "overclaim"
    target: str = ""
    issue: str = ""
    repair: str = ""


class DocumentationReview(CoderResult):
    """`prompts/review-story-documentation.md` — an independent read of what was written.

    `status` is `approved`, `revise` or `blocked`. A blank takes `revise`, the YAML's
    `default:`, which spends a rework rather than approving or failing. A `revise` verdict
    must carry structured findings; the free-form `notes` is a summary, not the repair
    contract.
    """

    status: str = ""
    findings: list[DocumentationFinding] = []
    notes: str = ""


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


__all__ = [
    "ContextClassification",
    "DocsResult",
    "DocumentationFinding",
    "DocumentationGate",
    "DocumentationResult",
    "DocumentationReview",
    "OkfDetection",
    "WorktreeSnapshot",
]
