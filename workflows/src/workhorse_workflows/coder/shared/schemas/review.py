"""The review flow's models: three review turns, the settlement gate, the feedback inbox.

Two shapes are worth naming, because both are deliberate.

* **The YAML's whole-key `default:` becomes per-field defaults.** `code_review_result` and
  `code_reuse_result` each declared a three-key default — `{status: skipped, findings: [],
  findings_summary: "… did not run."}` — which the engine applied only when the agent
  produced no such key at all. A model's defaults are per field, so a turn that answers
  `status` but not `findings_summary` would otherwise be handed the "did not run" sentence
  as if it were its own. `status` keeps its `skipped` default, because that is a real
  routing arm and a blank has to land somewhere; the sentence is dropped rather than
  risking a false claim in the next prompt's context. Nothing branches on either result —
  both are read as prose by `review-implementation.md`.
* **`feedback.present` is a bool.** It was `"yes"`/`"no"` because a script's JSON fed a
  `type: branch`, and a branch compares strings. A node returns a typed value now.

`impl_result` is `dev`'s `ImplResult`: the apply turn and the settlement gate that
overwrites it both carry a status and notes, and it is the same key the YAML reused.
"""
from __future__ import annotations

from typing import Any

from workhorse_workflows.coder.shared.schemas._base import CoderResult


class CodeReviewResult(CoderResult):
    """`prompts/code-review.md` — the mechanical review pass over the diff.

    `status` is advisory: nothing routes on it, and `review-implementation.md` is handed the
    whole result as evidence. A blank takes `skipped`, which is what the YAML's default said.
    """

    status: str = "skipped"
    findings: list[dict[str, Any]] = []
    findings_summary: str = ""


class CodeReuseResult(CoderResult):
    """`prompts/code-reuse.md` — did the implementation rebuild what already exists?

    The post-implementation counterpart to `dev`'s pre-implementation reuse check: that one
    looked at the plan, this one looks at the diff. Also advisory, also fed to the reviewer.
    """

    status: str = "skipped"
    findings: list[dict[str, Any]] = []
    findings_summary: str = ""


class ReviewVerdict(CoderResult):
    """`prompts/review-implementation.md` — the binding verdict on the implementation.

    `status` is `approved` or `needs_changes`, and a blank takes the YAML's `default:` arm,
    which is `needs_changes`: the holistic reviewer is the gate, and a reviewer that did not
    speak is not an approval. `notes` is the brief every downstream repair turn is handed.
    """

    status: str = ""
    notes: str = ""


class ReviewContext(CoderResult):
    """`resolve-review-context.py` — where the review turns run, and what they may read.

    `docs_repo_path` is the reviewer's cwd and `affected_repo_paths` the code repos granted
    alongside it. The standalone-PR path is what the `repo` input exists for: with no
    `plan-context.json` to decode, the named repo is the whole affected set.
    """

    docs_repo_path: str = ""
    affected_repo_paths: list[str] = []


class Feedback(CoderResult):
    """`check_feedback.py` — un-consumed operator notes dropped into the story's inbox.

    The non-blocking counterpart to the operator gate: it never halts and never asks. Reading
    it is what consumes it — the node flips `STATUS: NEW` to `CONSUMED` on the way out — so
    each dropped note buys exactly one rework pass.
    """

    present: bool = False
    scope: str = "story"
    content: str = ""


class ReviewResult(CoderResult):
    """What the review flow hands back.

    The YAML's `review_done` terminal declared no outputs and the main graph's `review` node
    read none — it routed to `docs` unconditionally. This exists so the run record says how
    the flow left rather than nothing at all; no caller branches on it.
    """

    status: str = "approved"
    notes: str = ""


__all__ = [
    "CodeReuseResult",
    "CodeReviewResult",
    "Feedback",
    "ReviewContext",
    "ReviewResult",
    "ReviewVerdict",
]
