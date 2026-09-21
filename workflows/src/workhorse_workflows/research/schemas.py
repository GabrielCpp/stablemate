"""What the research workflow validates: agent replies, and node return values."""
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




class RepoSetup(ResearchResult):
    """What `clone_repo` decided the working tree is."""

    repo_dir: str = ""


class Program(ResearchResult):
    """The run's whole configuration, and therefore `self.ctx`."""

    repo_dir: str = ""
    program: str = ""
    program_dir: str = ""
    progress_path: str = ""
    code_root: str = ""
    result_branch: str = ""
    goal: str = ""


    extensions_spent: int = 0
    lead_reviews_spent: int = 0
    program_reviews_spent: int = 0
    recharters_spent: int = 0
    status: str = "active"


    min_containment: str = "premium"
    envelope_ram_gb: int = 0
    envelope_cpus: int = 0
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




class GateSelection(ResearchResult):
    """`prompts/select-next-gate.md` — which gate to attempt, or that the program died."""

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
    """`prompts/gate-check.md` — the verdict the whole loop branches on."""

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
    """`prompts/research-lead-review.md` — was the kill real?"""

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
    prerequisite_gate_id: str = ""


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
    """`prompts/lead-goal-review.md` — the ladder is exhausted; now what?"""

    verdict: str = ""
    north_star_gap: str = ""
    evidence_or_deadends: str = ""
    banked_result: str = ""
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
    """The calibration probe an estimate is allowed to stand on."""

    units_total: int = 0
    units_timed: int = 0
    seconds: float = 0.0
    peak_rss_mb: float = 0.0


class Design(ResearchResult):
    """`prompts/design-experiment.md` — the scientist's half of a gate."""

    status: str = ""
    hypothesis: str = ""
    protocol: str = ""
    spec_files: list[str] = Field(default_factory=list)
    memory_mb: int = 0
    cpus: int = 0
    gpu: str = "none"
    disk_gb: int = 0
    estimate_s: float = 0.0
    probe: Probe = Field(default_factory=Probe)
    protocol_change: str = ""
    notes: str = ""


class Build(ResearchResult):
    """`prompts/build-experiment.md` — the engineer's half of a gate."""

    status: str = ""
    command: list[str] = Field(default_factory=list)
    dry_run_command: list[str] = Field(default_factory=list)
    cwd: str = ""
    result_file: str = "result.json"
    code_files: list[str] = Field(default_factory=list)
    fault_locus: str = ""
    component: str = ""
    notes: str = ""


class DryRun(ResearchResult):
    """What the `n=1` rehearsal through the real runner found."""

    ok: bool = False
    exit_code: int | None = None
    fault_locus: str = ""
    stderr_tail: str = ""
    reason: str = ""


class CodeReview(ResearchResult):
    """`prompts/code-review-experiment.md` — a correctness pass over the gate's diff."""

    status: str = ""
    findings: str = ""
    notes: str = ""


class EnvelopeCheck(ResearchResult):
    """Does the design fit the machine the program declared?"""

    fits: bool = False
    reason: str = ""


class Job(ResearchResult):
    """The handle `submit_job` left behind, as a state parameter can carry it."""

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
    """What the watcher found when it looked, and what to do about it."""

    action: str = ""
    wake_path: str = ""
    state: str = ""
    overrun_multiple: float = 0.0
    elapsed_s: float = 0.0
    estimate_s: float = 0.0


class Collected(ResearchResult):
    """The classification `collect_job` reached with **zero model calls**."""

    outcome: str = ""
    fault_locus: str = ""
    exit_code: int | None = None
    peak_rss_mb: float = 0.0
    wall_s: float = 0.0
    kill_reason: str = ""
    tier: str = ""
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
    """`prompts/triage-overrun.md` — the engineer, mid-flight, on a job running long."""

    decision: str = ""
    diagnosis: str = ""
    fault_locus: str = ""
    component: str = ""
    fix_hint: str = ""




class FrozenTarget(ResearchResult):
    """The README's `Frozen target` table, as numbers."""

    metric: str = ""
    dataset: str = ""
    threshold: str = ""
    threshold_value: float = 0.0
    threshold_count: int = 0
    n: int = 0
    seeds: list[int] = Field(default_factory=list)
    deadline: str = ""
    baseline_value: float = 0.0
    baseline_count: int = 0
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
    families: dict[str, list[float]] = Field(default_factory=dict)
    family_mean: dict[str, float] = Field(default_factory=dict)
    family_sd: dict[str, float] = Field(default_factory=dict)
    scalars: dict[str, float] = Field(default_factory=dict)
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
    pooled_se: float = 0.0
    per_seed_required: float = 0.0
    per_seed_se: float = 0.0
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
    """A re-chartered frozen target."""

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
    """The lead's program-level verdict on a dossier."""

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




def _one_more(grants: int, spent: int, cap: int) -> int:
    """The grant count that authorizes exactly one more spend past `spent` under `cap`."""
    return max(grants, spent - cap) + 1


class Budget(BaseModel):
    """The loop's three counters, travelling as one parameter."""

    model_config = ConfigDict(frozen=True)

    reworks: int = 0
    build_fixes: int = 0
    rescopes: int = 0
    lead_reviews: int = 0
    extensions: int = 0
    program_reviews: int = 0
    recharters: int = 0
    gate_cycles: int = 0


    lead_review_grants: int = 0
    extension_grants: int = 0
    program_review_grants: int = 0

    def fresh_gate(self) -> Budget:
        """Entering a gate: every per-gate counter starts over."""
        return self.model_copy(update={"reworks": 0, "build_fixes": 0, "rescopes": 0})

    def reworked(self) -> Budget:
        return self.model_copy(update={"reworks": self.reworks + 1})

    def built(self) -> Budget:
        return self.model_copy(update={"build_fixes": self.build_fixes + 1})

    def rescoped(self) -> Budget:
        return self.model_copy(update={"rescopes": self.rescopes + 1})

    def granted_review(self, spent: int, cap: int) -> Budget:
        """An operator answered the lead-review block: one more lap is authorized."""
        return self.model_copy(
            update={"lead_review_grants": _one_more(self.lead_review_grants, spent, cap)}
        )

    def granted_extension(self, spent: int, cap: int) -> Budget:
        """An operator answered the extension block: one more extension is authorized."""
        return self.model_copy(
            update={"extension_grants": _one_more(self.extension_grants, spent, cap)}
        )

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

    def granted_program_review(self, spent: int, cap: int) -> Budget:
        """An operator answered the program-review block: one more is authorized."""
        return self.model_copy(
            update={
                "program_review_grants": _one_more(self.program_review_grants, spent, cap)
            }
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
