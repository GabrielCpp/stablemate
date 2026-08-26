"""The review flow's models: two review turns, the settlement gate, the feedback inbox.

Two shapes are worth naming, because both are deliberate.

* **The YAML's whole-key `default:` becomes per-field defaults.** `code_review_result`
  declared a three-key default — `{status: skipped, findings: [],
  findings_summary: "… did not run."}` — which the engine applied only when the agent
  produced no such key at all. A model's defaults are per field, so a turn that answers
  `status` but not `findings_summary` would otherwise be handed the "did not run" sentence
  as if it were its own. The sentence is dropped rather than risking a false claim in the
  next prompt's context, and `status` no longer defaults at all: the reviewer produces it,
  so it is a required `Literal` and a reply that omits it is a parse failure the runner
  answers with a retry turn.
* **`feedback.present` is a bool.** It was `"yes"`/`"no"` because a script's JSON fed a
  `type: branch`, and a branch compares strings. A node returns a typed value now.

`impl_result` is `dev`'s `ImplResult`: the apply turn and the settlement gate that
overwrites it both carry a status and notes, and it is the same key the YAML reused.
"""
from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel

from workhorse_workflows.coder.shared.schemas._base import CoderResult, Finding

#: Which lens caught a finding. Closed, because the set is what the prompts teach and a
#: spelling outside it is a reviewer that did not read its own contract — see
#: `ReviewFinding`. `Code Duplication` and `Missed Utility` were two words for the one
#: thing the binding reviewer reads back out, and are one arm here.
ReviewCategory = Literal["Bug", "Standard", "Reuse"]

#: What the mechanical pass over the diff did. `findings` and `clean` are the two real
#: readings; `skipped` is a pass that had nothing to look at, and `blocked` one that could
#: not look.
CodeReviewStatus = Literal["findings", "clean", "skipped", "blocked"]

#: The binding verdict on the implementation. `blocked` is the answer for a reviewer that
#: can reach neither of the other two because what is missing is outside the repository.
ReviewStatus = Literal["approved", "needs_changes", "blocked"]


class ReviewFinding(Finding):
    """A code-review finding: the base contract, plus which lens caught it and how sure it is.

    `category` exists because the reuse hunt is a lens of the review pass rather than a
    turn of its own: it was a second cold turn over the same diff, and the only thing lost
    by folding it in is the ability to tell a duplication finding from a bug at a glance.
    So the prompt tags each one, out of the closed set `ReviewCategory` names, and
    `review-implementation.md` reads `Reuse` back out into its own reuse section.
    """

    #: Which lens caught it. The reviewer says it, so there is no default to fall back to.
    category: ReviewCategory

    #: The 0-100 confidence the pass scored it, carried with the finding rather than
    #: discarded at the parse — a reader weighing two survivors against each other wants it.
    score: int = 0


class CodeReviewResult(CoderResult):
    """`review/prompts/code-review.md` — the mechanical review pass over the diff.

    `status` is advisory: nothing routes on it, and `review-implementation.md` is handed the
    whole result as evidence.

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

    status: CodeReviewStatus
    findings: list[ReviewFinding] = []
    findings_summary: str = ""


class ReviewVerdict(CoderResult):
    """`review/prompts/review-implementation.md` — the binding verdict on the implementation.

    `status` is required: the holistic reviewer is the gate, and a reviewer that did not
    speak used to take a `needs_changes` default that the flow then had to patch a blank
    into. A reply without a verdict is a parse failure now, and the runner retries the turn
    rather than inventing one for it. `blocked` goes to the operator rather than round the
    repair loop, which has nothing to act on. `notes` is the brief every downstream turn is
    handed.
    """

    status: ReviewStatus
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
    content: str = ""


class ReviewLoop(BaseModel):
    """The three budgets one review round carries, as one state parameter rather than three.

    A bare `BaseModel` rather than a `CoderResult`: nothing returns it, no agent fills it in,
    so it wants neither the dropped nulls nor the `blocked` reading those buy.

    `session_turns` is a running count, not an input — it is seeded once from `start` and
    every apply turn spends onto it. It lived as a workflow field, which made a per-lap
    counter look like something an operator sets with `--param`.
    """

    #: Apply passes spent on this round's findings. Reset by a trip through the operator arm,
    #: which re-enters `start` with a fresh review.
    rework: int = 0

    #: Trips through the operator gate across the whole flow, resolver answers included.
    #: Never reset — it is what walks a lapping resolver toward a person.
    blocks: int = 0

    #: Turns the story's implementer conversation has spent, this flow's and the dev lane's
    #: alike, so the recycle threshold bounds the conversation rather than each lane's share.
    session_turns: int = 0

    #: All three, as span dimensions. Bare names on the model; `Review.state_labels` supplies
    #: the `review.` prefix.
    COUNT_LABELS: ClassVar[tuple[str, ...]] = ("rework", "blocks", "session_turns")


class ReviewResult(CoderResult):
    """What the review flow hands back.

    The YAML's `review_done` terminal declared no outputs and the main graph's `review` node
    read none — it routed to `docs` unconditionally. This exists so the run record says how
    the flow left rather than nothing at all; no caller branches on it, and it carries no
    status because nothing ever read the one it used to declare.
    """

    notes: str = ""


__all__ = [
    "CodeReviewResult",
    "CodeReviewStatus",
    "Feedback",
    "ReviewCategory",
    "ReviewContext",
    "ReviewFinding",
    "ReviewLoop",
    "ReviewResult",
    "ReviewStatus",
    "ReviewVerdict",
]
