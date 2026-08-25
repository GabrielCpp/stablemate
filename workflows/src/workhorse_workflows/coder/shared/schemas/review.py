"""The review flow's models: two review turns, the settlement gate, the feedback inbox.

Two shapes are worth naming, because both are deliberate.

* **The YAML's whole-key `default:` becomes per-field defaults.** `code_review_result`
  declared a three-key default — `{status: skipped, findings: [],
  findings_summary: "… did not run."}` — which the engine applied only when the agent
  produced no such key at all. A model's defaults are per field, so a turn that answers
  `status` but not `findings_summary` would otherwise be handed the "did not run" sentence
  as if it were its own. `status` keeps its `skipped` default, because that is a real
  routing arm and a blank has to land somewhere; the sentence is dropped rather than
  risking a false claim in the next prompt's context. Nothing branches on the result — it
  is read as prose by `review-implementation.md`.
* **`feedback.present` is a bool.** It was `"yes"`/`"no"` because a script's JSON fed a
  `type: branch`, and a branch compares strings. A node returns a typed value now.

`impl_result` is `dev`'s `ImplResult`: the apply turn and the settlement gate that
overwrites it both carry a status and notes, and it is the same key the YAML reused.
"""
from __future__ import annotations

from workhorse_workflows.coder.shared.schemas._base import CoderResult, Finding


class ReviewFinding(Finding):
    """A code-review finding: the base contract, plus which lens caught it and how sure it is.

    `category` exists because the reuse hunt is a lens of the review pass rather than a
    turn of its own: it was a second cold turn over the same diff, and the only thing lost
    by folding it in is the ability to tell a duplication finding from a bug at a glance.
    So the prompt tags each one — `Code Duplication` and `Missed Utility` are the two the
    binding reviewer reads back out into its own reuse section — and an untagged finding
    is a bug report, which is what the field's empty default means.
    """

    #: Which lens caught it. Free-form on purpose: nothing routes on it, `review-implementation.md`
    #: reports on it, and a model that answered with a spelling this file did not predict
    #: should not have its finding dropped for it.
    category: str = ""

    #: The 0-100 confidence the pass scored it. The prompt already drops everything under 80,
    #: so this is not a second filter — it is how sure the review was, carried with the finding
    #: instead of discarded at the parse, for a reader weighing two survivors against each other.
    score: int = 0


class CodeReviewResult(CoderResult):
    """`review/prompts/code-review.md` — the mechanical review pass over the diff.

    `status` is advisory: nothing routes on it, and `review-implementation.md` is handed the
    whole result as evidence. A blank takes `skipped`, which is what the YAML's default said.

    `findings` was `list[dict[str, Any]]` — a shape that admitted anything and so guaranteed
    nothing. It is a `Finding` now, the same contract the QA and documentation gates already
    met: a target to go to and a repair to make. That contract only binds if the prompt
    answers in it, and for a while this one did not — it emitted `repo`/`file`/`line` and
    `required_fix`, all of which `extra="ignore"` dropped on the floor, so every finding
    reached `review-implementation.md` as a bare sentence and none was ever `actionable`,
    which sent a block to the operator that a fixer could have taken. The prompt emits
    `target`/`issue`/`repair` now, and a finding missing either half is visibly not
    evidence rather than silently stripped of it.
    """

    status: str = "skipped"
    findings: list[ReviewFinding] = []
    findings_summary: str = ""


class ReviewVerdict(CoderResult):
    """`review/prompts/review-implementation.md` — the binding verdict on the implementation.

    `status` is `approved`, `needs_changes` or `blocked`, and a blank takes the YAML's
    `default:` arm, which is `needs_changes`: the holistic reviewer is the gate, and a
    reviewer that did not speak is not an approval. `blocked` is the third answer the gate
    always needed — a reviewer that cannot reach *either* verdict, because what is missing
    is outside the repository — and it goes to the operator rather than round the repair
    loop, which has nothing to act on. `notes` is the brief every downstream turn is handed.
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
    """`check_feedback` — an un-consumed operator note dropped into the run's inbox.

    The non-blocking counterpart to the operator gate: it never halts and never asks. Polling
    it is what consumes it — the oldest outstanding message is replied to on the way out — so
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
    "CodeReviewResult",
    "Feedback",
    "ReviewContext",
    "ReviewFinding",
    "ReviewResult",
    "ReviewVerdict",
]
