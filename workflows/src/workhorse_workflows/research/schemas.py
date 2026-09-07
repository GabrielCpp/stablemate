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
    #: Program reviews (`program_review`) this program has already spent.
    program_reviews_spent: int = 0
    #: Re-charters (`recharter`) this program has already spent.
    recharters_spent: int = 0
    #: `active`, or one of the terminal statuses a prior run banked/recorded.
    status: str = "active"

    # ── the machine envelope, and the floor a measurement is trusted under ────
    #
    # An experiment that asks for more than the machine has is not a science
    # failure and not an operator's problem: it is a protocol that has to be
    # rescoped. `submit` compares the design's declared resources against these
    # and routes back to `design` when they do not fit, so the numbers have to be
    # in the program's own configuration rather than read off the host — a run
    # resumed on a bigger machine must not silently accept a job the program was
    # never sized for.

    #: The containment tier a measurement is refused below (`workhorse.job.TIERS`).
    min_containment: str = "premium"
    envelope_ram_gb: int = 0
    envelope_cpus: int = 0
    #: `none` unless the program declares a GPU it may ask for.
    envelope_gpu: str = "none"
    envelope_disk_gb: int = 0


class Ledger(ResearchResult):
    """What `record_spend` wrote — the program-scoped counters, on disk."""

    path: str = ""
    extensions: int = 0
    lead_reviews: int = 0
    program_reviews: int = 0
    recharters: int = 0
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


class Probe(ResearchResult):
    """The calibration probe an estimate is allowed to stand on.

    An estimate with no probe behind it is a feeling, and a feeling sets the overrun
    thresholds the whole mid-flight triage is derived from. `submit` refuses a job
    whose probe timed nothing.
    """

    #: Units (epochs, seeds, examples…) the full run will do.
    units_total: int = 0
    #: Units actually timed to produce `seconds` — zero means there was no probe.
    units_timed: int = 0
    #: Wall seconds those `units_timed` took.
    seconds: float = 0.0
    #: Peak RSS the probe reached, in MB.
    peak_rss_mb: float = 0.0


class Design(ResearchResult):
    """`prompts/design-experiment.md` — the scientist's half of a gate.

    Protocol, declared resources and the calibration probe. It never runs the
    experiment and never repairs code: what it produces is what the engineer then
    has to make runnable.
    """

    status: str = ""
    hypothesis: str = ""
    protocol: str = ""
    spec_files: list[str] = Field(default_factory=list)
    #: Declared resources, checked against the program's envelope before submission.
    memory_mb: int = 0
    cpus: int = 0
    gpu: str = "none"
    disk_gb: int = 0
    #: Seconds the full run is expected to take, derived from `probe`.
    estimate_s: float = 0.0
    probe: Probe = Field(default_factory=Probe)
    #: On a scientific rework: what changed in the protocol, and why. The hypothesis
    #: and the frozen target are not the scientist's to change.
    protocol_change: str = ""
    notes: str = ""


class Build(ResearchResult):
    """`prompts/build-experiment.md` — the engineer's half of a gate.

    Two commands, because shrinking a run is not something a caller can guess: the
    real measurement, and an `n=1` version of it that proves the handoff works.
    """

    status: str = ""
    #: argv, not a shell string — a measurement is not a recipe.
    command: list[str] = Field(default_factory=list)
    #: The same experiment at `n=1`, run through the real runner before submission.
    dry_run_command: list[str] = Field(default_factory=list)
    cwd: str = ""
    result_file: str = "result.json"
    code_files: list[str] = Field(default_factory=list)
    #: The engineer's escape hatch, and only where a deterministic classifier has
    #: nothing to read: `status: "tooling"` with `component` naming what is broken
    #: (workhorse, ostler, the workflow, the machine) routes to an operator. Naming
    #: the component is the price of using it — an engineer that can call any hard
    #: problem "tooling" has every reason to.
    fault_locus: str = ""
    component: str = ""
    notes: str = ""


class DryRun(ResearchResult):
    """What the `n=1` rehearsal through the real runner found.

    It runs through `workhorse.job`, not the engineer's shell, because the handoff is
    the part that breaks: a command that works when typed and dies under the runner
    has failed the only test that matters here.
    """

    ok: bool = False
    exit_code: int | None = None
    #: `repo`, `tooling` or `unknown` — decided from the traceback, not by an agent.
    fault_locus: str = ""
    stderr_tail: str = ""
    reason: str = ""


class EnvelopeCheck(ResearchResult):
    """Does the design fit the machine the program declared?"""

    fits: bool = False
    reason: str = ""


class Job(ResearchResult):
    """The handle `submit_job` left behind, as a state parameter can carry it.

    A submission that never happened is still a `Job`: `error` says why, and
    `fault_locus` says whose problem it is. "This machine is too weak" and "that
    command would not start" are different repairs and route to different people.
    """

    submitted: bool = False
    error: str = ""
    fault_locus: str = ""
    job_dir: str = ""
    wake_path: str = ""
    pid: int = 0
    pgid: int = 0
    tier: str = ""
    started_at: float = 0.0
    estimate_s: float = 0.0


class JobWatch(ResearchResult):
    """What the watcher found when it looked, and what to do about it.

    `action` is `collect` (the job is over, one way or another), `triage` (it is still
    running and has crossed a new overrun threshold) or `wait` (park on `wake_path`).
    """

    action: str = ""
    wake_path: str = ""
    state: str = ""
    overrun_multiple: float = 0.0
    elapsed_s: float = 0.0
    estimate_s: float = 0.0


class Collected(ResearchResult):
    """The classification `collect_job` reached with **zero model calls**.

    `outcome` is one of `ok` (a result file and a clean exit), `crash` (no usable
    measurement), `invalid` (a result file that does not parse or is missing its core)
    or `over_resource` (killed for memory, or an exit under a cgroup ceiling). The two
    artifacts are what make this decidable: the command says what it found, the
    supervisor says what it cost, and the command cannot write the second one.
    """

    outcome: str = ""
    #: For `crash`/`invalid`: `repo`, `tooling` or `unknown`.
    fault_locus: str = ""
    exit_code: int | None = None
    peak_rss_mb: float = 0.0
    wall_s: float = 0.0
    kill_reason: str = ""
    tier: str = ""
    #: The experiment's own artifact, as a path and as its parsed core.
    result_path: str = ""
    result_status: str = ""
    metrics: dict[str, Any] = Field(default_factory=dict)
    seeds: list[Any] = Field(default_factory=list)
    controls: list[Any] = Field(default_factory=list)
    n_completed: int = 0
    n_planned: int = 0
    stderr_tail: str = ""
    reason: str = ""


class TriageResult(ResearchResult):
    """`prompts/triage-overrun.md` — the engineer, mid-flight, on a job running long.

    `decision` is `keep_going` or `kill_and_fix`. Keeping going is unbounded on
    purpose: the thresholds double, so the wakeups get rarer exactly as fast as the
    job gets less likely to be worth waiting for.
    """

    decision: str = ""
    diagnosis: str = ""
    #: Only consulted when there is no stack to classify. An engineer that can route
    #: its own hard problems to a human by calling them "tooling" has every reason to,
    #: so declaring `tooling` also requires naming `component`.
    fault_locus: str = ""
    component: str = ""
    fix_hint: str = ""


# ── the program dossier, and the verdicts that act on it ────────────────────
#
# Everything a `program_review` turn is shown is computed here, by `nodes/dossier.py`,
# with zero model calls. The prompt judges; it does not count. These models are the
# shape of that evidence, and every field is defaulted so a record the parsers could
# not read degrades to "unknown" rather than to a crash.


class FrozenTarget(ResearchResult):
    """The README's `Frozen target` table, as numbers."""

    metric: str = ""
    dataset: str = ""
    #: The raw threshold cell, e.g. `>= 0.6262 (93/147)`.
    threshold: str = ""
    #: The threshold as a fraction of `n`, when the cell names one; else 0.
    threshold_value: float = 0.0
    #: The count form (`93` of `147`) when the cell or the dataset names one.
    threshold_count: int = 0
    n: int = 0
    seeds: list[int] = Field(default_factory=list)
    deadline: str = ""
    #: The baseline the threshold is measured against, as a fraction of `n`.
    baseline_value: float = 0.0
    baseline_count: int = 0
    #: Where the baseline came from (`table`, `prose`, or empty).
    baseline_source: str = ""


class GateRow(ResearchResult):
    """One row of a progress status table."""

    gate_id: str = ""
    document: str = ""
    depends_on: str = ""
    status: str = ""
    result: str = ""
    date: str = ""


class HistoryEvent(ResearchResult):
    """One line of `history.jsonl` — what the loop did, when, to which gate."""

    date: str = ""
    event: str = ""
    gate_id: str = ""
    note: str = ""
    #: `loop` for lines the workflow wrote, `bootstrap` for lines parsed from prose.
    source: str = "loop"
    fingerprint: str = ""


class JobSummary(ResearchResult):
    """What one `jobs/<gate>/` directory says, per seed family."""

    gate_id: str = ""
    finished_at: str = ""
    exit_code: int = 0
    wall_s: float = 0.0
    kill_reason: str = ""
    n_completed: int = 0
    n_planned: int = 0
    seeds: list[int] = Field(default_factory=list)
    #: `<base>` -> per-seed values, for every `<base>_seed<i>` family in `metrics`.
    families: dict[str, list[float]] = Field(default_factory=dict)
    family_mean: dict[str, float] = Field(default_factory=dict)
    family_sd: dict[str, float] = Field(default_factory=dict)
    #: Scalar metrics that are not part of a seed family.
    scalars: dict[str, float] = Field(default_factory=dict)
    #: Metric names whose value was truthy and whose name reads as a flag
    #: (`*_blocked`, `*_flag`, `*_tension`, `leak*`).
    flags: list[str] = Field(default_factory=list)


class MetricPoint(ResearchResult):
    """One dated observation of the frozen metric."""

    date: str = ""
    value: float = 0.0
    count: int = 0
    n: int = 0
    gate_id: str = ""
    source: str = ""


class Resolvability(ResearchResult):
    """Can the frozen target's effect be told from seed noise on its own eval?"""

    required_effect: float = 0.0
    #: Pooled binomial SE at the baseline rate over `n`.
    pooled_se: float = 0.0
    #: Per-seed required tasks against the per-seed SE, when seeds are known.
    per_seed_required: float = 0.0
    per_seed_se: float = 0.0
    #: Observed per-seed spread, when a seed family for the metric exists.
    observed_seed_sd: float = 0.0
    ratio: float = 0.0
    resolvable: bool = False
    statement: str = ""


class Dossier(ResearchResult):
    """The computed program-level evidence one `program_review` turn is judged on."""

    today: str = ""
    program_dir: str = ""
    frozen: FrozenTarget = Field(default_factory=FrozenTarget)
    rows: list[GateRow] = Field(default_factory=list)
    superseded_rows: list[GateRow] = Field(default_factory=list)
    history: list[HistoryEvent] = Field(default_factory=list)
    jobs: list[JobSummary] = Field(default_factory=list)
    series: list[MetricPoint] = Field(default_factory=list)
    moved_last_on: str = ""
    days_since_moved: int = 0
    days_to_deadline: int = 0
    resolvability: Resolvability = Field(default_factory=Resolvability)
    counts: dict[str, int] = Field(default_factory=dict)
    #: `gate_id` -> lines changed in `code_root` since the program's last metric move.
    churn: dict[str, int] = Field(default_factory=dict)
    pending: list[str] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)
    circling: bool = False
    fingerprint: str = ""
    review_due: bool = False
    active_gate: str = ""
    unparsed: list[str] = Field(default_factory=list)


class ProbeOrder(ResearchResult):
    """A cheap, decisive measurement the lead orders before any more gate work."""

    gate_id: str = ""
    question: str = ""
    expected_cost_s: int = 0
    kill_if: str = ""


class NewTarget(ResearchResult):
    """A re-chartered frozen target. `why_resolvable` is checked in code, not trusted."""

    metric: str = ""
    dataset: str = ""
    threshold: str = ""
    threshold_count: int = 0
    n: int = 0
    seeds: list[int] = Field(default_factory=list)
    baseline: str = ""
    baseline_count: int = 0
    deadline: str = ""
    why_resolvable: str = ""


class ProgramReview(ResearchResult):
    """The lead's program-level verdict on a dossier.

    `verdict` is one of `continue`, `probe_first`, `score_from_cache`, `recharter`,
    `bank`, `stop_negative`, `operator`. The default `""` matches no arm and parks.
    """

    verdict: str = ""
    circling: bool = False
    triggers_confirmed: list[str] = Field(default_factory=list)
    reason: str = ""
    evidence: list[str] = Field(default_factory=list)
    probe: ProbeOrder = Field(default_factory=ProbeOrder)
    cache_gate_id: str = ""
    cache_dir: str = ""
    recharter: NewTarget = Field(default_factory=NewTarget)
    operator_question: str = ""
    confidence: str = ""


class RecharterResult(ResearchResult):
    """What `program-recharter` wrote into the program folder."""

    status: str = ""
    new_target: NewTarget = Field(default_factory=NewTarget)
    probe_doc_path: str = ""
    cache_doc_path: str = ""
    readme_path: str = ""
    progress_updated: bool = False
    reason: str = ""


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

    #: Scientific reworks on the gate currently in flight — the experiment measured
    #: something and missed. Per-gate, not per-run: `start` clears it.
    reworks: int = 0
    #: Engineering repairs on the gate currently in flight — the experiment produced
    #: no measurement. A different failure with a different fix, so a different count.
    build_fixes: int = 0
    #: Rescopes after a design asked for more than the machine has. Per-gate.
    rescopes: int = 0
    #: Research-lead reviews of a killed gate, across the whole run.
    lead_reviews: int = 0
    #: Program self-extensions, across the whole run.
    extensions: int = 0
    #: Program-level reviews (`program_review`), across the whole run.
    program_reviews: int = 0
    #: Re-charters applied (`recharter`), across the whole run.
    recharters: int = 0
    #: Gates concluded (pass or kill) since the last periodic program review.
    gate_cycles: int = 0

    # ── what an operator authorized, after a cap was hit ─────────────────────
    #
    # A cap that is hit escalates to an operator rather than ending the run, and the
    # operator's answer *is* the authorization to keep going. Without somewhere to
    # record that, the resume re-enters the capped state, re-reads the same count and
    # blocks again — a loop with a human in it, which is worse than the give-up it
    # replaced. Each grant raises the ceiling by one, so the next block is a real one.

    #: Extra lead reviews an operator has authorized past `MAX_LEAD_REVIEWS`.
    lead_review_grants: int = 0
    #: Extra extensions an operator has authorized past `MAX_EXTENSIONS`.
    extension_grants: int = 0
    #: Extra program reviews an operator has authorized past `MAX_PROGRAM_REVIEWS`.
    program_review_grants: int = 0

    def fresh_gate(self) -> Budget:
        """Entering a gate: every per-gate counter starts over.

        `start` is where this happens, and it has to be: both a rework and a rescope
        route back to `design`, so clearing there would reset the counters being spent.
        """
        return self.model_copy(update={"reworks": 0, "build_fixes": 0, "rescopes": 0})

    def reworked(self) -> Budget:
        return self.model_copy(update={"reworks": self.reworks + 1})

    def built(self) -> Budget:
        return self.model_copy(update={"build_fixes": self.build_fixes + 1})

    def rescoped(self) -> Budget:
        return self.model_copy(update={"rescopes": self.rescopes + 1})

    def granted_review(self) -> Budget:
        """An operator answered the lead-review block: one more lap is authorized."""
        return self.model_copy(update={"lead_review_grants": self.lead_review_grants + 1})

    def granted_extension(self) -> Budget:
        """An operator answered the extension block: one more extension is authorized."""
        return self.model_copy(update={"extension_grants": self.extension_grants + 1})

    def reviewed(self) -> Budget:
        return self.model_copy(update={"lead_reviews": self.lead_reviews + 1})

    def extended(self) -> Budget:
        return self.model_copy(update={"extensions": self.extensions + 1})

    def cycled(self) -> Budget:
        """A gate concluded: one more cycle toward the next periodic program review."""
        return self.model_copy(update={"gate_cycles": self.gate_cycles + 1})

    def program_reviewed(self) -> Budget:
        """A program review ran: count it, and the periodic clock starts over."""
        return self.model_copy(
            update={"program_reviews": self.program_reviews + 1, "gate_cycles": 0}
        )

    def rechartered(self) -> Budget:
        return self.model_copy(update={"recharters": self.recharters + 1})

    def granted_program_review(self) -> Budget:
        """An operator answered the program-review block: one more is authorized."""
        return self.model_copy(
            update={"program_review_grants": self.program_review_grants + 1}
        )


__all__ = [
    "AntiShortcutFlags",
    "Budget",
    "Build",
    "Collected",
    "Design",
    "Dossier",
    "DryRun",
    "EnvelopeCheck",
    "ExtendResult",
    "FailedCriterion",
    "FrozenTarget",
    "GateCheck",
    "GateRow",
    "GateSelection",
    "GoalReview",
    "HistoryEvent",
    "Job",
    "JobSummary",
    "JobWatch",
    "LeadReview",
    "Ledger",
    "MetricPoint",
    "NewDirectionResult",
    "NewTarget",
    "Probe",
    "ProbeOrder",
    "Program",
    "ProgramReview",
    "PublishResult",
    "RecharterResult",
    "RecordResult",
    "RepoSetup",
    "ResearchResult",
    "Resolvability",
    "ReviveResult",
    "TriageResult",
]
