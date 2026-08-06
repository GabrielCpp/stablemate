"""What the research workflow validates: agent replies, and node return values.

These are **not** payloads at state boundaries — that shape is rejected (see the plan's
"Rejected along the way"). A transition carries keyword arguments bound against the next
state's own signature, so a state's parameters are its schema and there is no model in
between. What is left needs a model for a different reason: the two places where a value
arrives from outside Python and has to be checked on the way in.

* **Agent replies.** `self.agent(prompt, returns=T)` validates a model out of whatever
  the turn produced, and the engine reads `T`'s fields to build the output keys it asks
  for. The model is the seam's argument; without it there is nothing to ask for.
* **Node returns.** A node is a plain function returning a plain typed value; `Program`
  is additionally the one `setup()` hands back as `self.ctx`.

Two rules shape all of them, and both come from how workhorse fails rather than from
how it succeeds:

* **Every field has a default.** After the resilience ladder's last rung, a node that
  could not be answered emits its declared output keys as `null` and the run advances
  (docs/GUARDRAILS.md, "Default to the next node"). Those nulls are then validated into
  the model, so a required field would turn a soft failure into a hard one — exactly
  the crash the ladder exists to prevent.
* **Unknown keys are ignored, nulls are dropped.** `_drop_nulls` lets each field's own
  default stand in for a missing answer, and `extra="ignore"` means an agent that
  wraps its reply in the old YAML-era envelope degrades to all-defaults instead of
  raising.

A defaulted `status`/`verdict` is `""`, which matches no branch — so a state that
cannot get an answer falls through to its else arm, and the else arms here are the
conservative ones (rework rather than approve, halt rather than extend).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ResearchResult(BaseModel):
    """Base for every agent reply and node return in this workflow."""

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _drop_nulls(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if v is not None}
        return data


# ── node returns ────────────────────────────────────────────────────────────


class RepoSetup(ResearchResult):
    """What `clone_repo` decided the working tree is."""

    repo_dir: str = ""


class Program(ResearchResult):
    """The run's whole configuration, and therefore `self.ctx`.

    Decided once at the top of the run by `load_program` and read at the bottom by
    `publish_results` — the residue `setup()` exists for.
    """

    repo_dir: str = ""
    program: str = ""
    program_dir: str = ""
    progress_path: str = ""
    code_root: str = ""
    result_branch: str = ""
    #: Empty on purpose: the leads then read the README's "North star" section.
    goal: str = ""

    # ── the ledger, read once here so the caps are program-scoped ────────────
    #
    # `Budget`'s counters are *this run's*. A program driven by six successive runs
    # (or by a shell loop that relaunches on every exit) would spend the whole
    # extension budget six times over, which makes `MAX_EXTENSIONS` bound nothing.
    # These three carry what the program already spent, so the guards can add.

    #: Extensions this program has already spent, over every prior run.
    extensions_spent: int = 0
    #: Lead reviews this program has already spent, over every prior run.
    lead_reviews_spent: int = 0
    #: `active`, or one of the terminal statuses a prior run banked/recorded.
    status: str = "active"


class Ledger(ResearchResult):
    """What `record_spend` wrote — the program-scoped counters, on disk."""

    path: str = ""
    extensions: int = 0
    lead_reviews: int = 0
    status: str = "active"


class PublishResult(ResearchResult):
    published: bool = False
    result_branch: str = ""
    status: str = ""


# ── agent replies ───────────────────────────────────────────────────────────


class GateSelection(ResearchResult):
    """`prompts/select-next-gate.md` — which gate to attempt, or that the program died.

    `gate_id == "none"` means the ladder is exhausted; `program_killed` means a kill
    criterion tripped, and then `gate_id` still names the gate that tripped it.
    """

    gate_id: str = ""
    gate_doc_path: str = ""
    depends_on_satisfied: bool = False
    program_killed: bool = False
    rationale: str = ""


class ImplResult(ResearchResult):
    """`prompts/implement-experiment.md` and `prompts/rework-experiment.md`."""

    status: str = ""
    spec_files: list[str] = Field(default_factory=list)
    code_files: list[str] = Field(default_factory=list)
    test_files: list[str] = Field(default_factory=list)
    commands_run: list[str] = Field(default_factory=list)
    metrics: dict[str, str] = Field(default_factory=dict)
    notes: str = ""


class FailedCriterion(ResearchResult):
    criterion: str = ""
    expected: str = ""
    observed: str = ""
    severity: str = ""


class AntiShortcutFlags(ResearchResult):
    lookup_flag: bool = False
    oracle_route_flag: bool = False
    repair_flag: bool = False
    leak_flag: bool = False


class GateCheck(ResearchResult):
    """`prompts/gate-check.md` — the verdict the whole loop branches on.

    `status` is `approved` (PASS/WEAK_PASS), `killed` (a FAIL that trips a program kill
    criterion), or `needs_rework` (any other FAIL).
    """

    status: str = ""
    verdict: str = ""
    failed_criteria: list[FailedCriterion] = Field(default_factory=list)
    anti_shortcut_flags: AntiShortcutFlags = Field(default_factory=AntiShortcutFlags)
    zero_weights_changes_output: bool = False
    notes: str = ""


class RecordResult(ResearchResult):
    """`prompts/record-result.md` — the write to PROGRESS.md and the gate doc."""

    status: str = ""
    outcome: str = ""
    progress_updated: bool = False
    result_slot_updated: bool = False
    finding_path: str = ""


class LeadReview(ResearchResult):
    """`prompts/research-lead-review.md` — was the kill real?

    `verdict` is `revive` or `new_direction`.
    """

    verdict: str = ""
    kill_was_correct: bool = False
    reason_class: str = ""
    evidence: str = ""
    apparatus_fix: str = ""
    next_direction_hint: str = ""
    confidence: str = ""


class ReviveResult(ResearchResult):
    """`prompts/revive-gate.md`."""

    status: str = ""
    gate_id: str = ""
    finding_path: str = ""
    progress_updated: bool = False
    gate_doc_rescoped: bool = False


class NewDirectionResult(ResearchResult):
    """`prompts/define-new-direction.md`."""

    status: str = ""
    supersedes_gate: str = ""
    direction_name: str = ""
    core_question: str = ""
    ruled_out: list[str] = Field(default_factory=list)
    new_gates: list[str] = Field(default_factory=list)
    readme_path: str = ""
    progress_reset: bool = False


class GoalReview(ResearchResult):
    """`prompts/lead-goal-review.md` — the ladder is exhausted; now what?

    `verdict` is `reached`, `banked`, `impossible`, or `extend`.

    `banked` is the verdict a ladder-shaped program otherwise cannot express: the
    North star is not reached, no path is ruled out, and yet the strongest result is
    already worth shipping. Without it the only way to keep a program alive is
    `extend`, so a program can defer success indefinitely and never declare anything
    — which is the failure mode the fourth verdict exists to stop. It ends the run
    clean and requires an operator to re-authorize before the program continues.
    """

    verdict: str = ""
    north_star_gap: str = ""
    evidence_or_deadends: str = ""
    #: For `banked`: the standalone result being recorded as shippable.
    banked_result: str = ""
    #: For `extend`: the evidence class no gate on the passed ladder has produced.
    #: The burden of proof `extend` carries — naming one is what distinguishes a real
    #: next gate from another lap of the same one.
    new_evidence_class: str = ""
    next_gate_title: str = ""
    next_gate_question: str = ""
    next_gate_cheapest_kill: str = ""
    next_gate_controls: list[str] = Field(default_factory=list)
    why_closer: str = ""
    confidence: str = ""


class ExtendResult(ResearchResult):
    """`prompts/extend-program.md`."""

    status: str = ""
    new_gate_id: str = ""
    new_gate_title: str = ""
    depends_on: str = ""
    gate_doc_path: str = ""
    readme_updated: bool = False
    progress_updated: bool = False
    moves_closer: str = ""


# ── a state parameter ───────────────────────────────────────────────────────


class Budget(BaseModel):
    """The loop's three counters, travelling as one parameter.

    The narrow exception to the rule at the top of this module. It is not a *payload*
    — not the data a state works on, gathered into a bag so the signature stays short.
    It is one value that happens to be composite: the three counters are always
    carried together, almost always by states that have no opinion about any of them,
    and are only ever read against the `MAX_*` caps. As three parameters they put
    `lead_reviews=0, extensions=0` on eleven signatures and every call site between
    them; as one they appear where they are spent.

    Frozen, and the bumps return a new instance. A state parameter *is* the
    checkpoint, which was written before the state ran — mutating one in place would
    advance a counter the checkpoint still records at its old value, so a resume would
    silently un-count it.

    Its JSON projection is what lands in `checkpoint.json`, one readable object under
    `params.budget`; the driver validates it back into a `Budget` on the way in.
    """

    model_config = ConfigDict(frozen=True)

    #: Re-check attempts on the gate currently in flight. Per-gate, not per-run:
    #: `implement` clears it, which is where the YAML's `reset_rework` node stood.
    reworks: int = 0
    #: Research-lead reviews of a killed gate, across the whole run.
    lead_reviews: int = 0
    #: Program self-extensions, across the whole run.
    extensions: int = 0

    def fresh_gate(self) -> Budget:
        """Entering a new gate's experiment: its rework attempts start over."""
        return self.model_copy(update={"reworks": 0})

    def reworked(self) -> Budget:
        return self.model_copy(update={"reworks": self.reworks + 1})

    def reviewed(self) -> Budget:
        return self.model_copy(update={"lead_reviews": self.lead_reviews + 1})

    def extended(self) -> Budget:
        return self.model_copy(update={"extensions": self.extensions + 1})


__all__ = [
    "AntiShortcutFlags",
    "Budget",
    "ExtendResult",
    "FailedCriterion",
    "GateCheck",
    "GateSelection",
    "GoalReview",
    "ImplResult",
    "LeadReview",
    "Ledger",
    "NewDirectionResult",
    "Program",
    "PublishResult",
    "RecordResult",
    "RepoSetup",
    "ResearchResult",
    "ReviveResult",
]
